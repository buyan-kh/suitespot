"""Cancel a reservation and apply the tiered refund rules (US3.3, task 3.3.3).

Cancelling flips the reservation's status to "cancelled". The availability rule
(app.services.availability) already treats "cancelled" as free, so the room
opens up again for those dates with no extra work. If the reservation was paid,
the policy refund is recorded in the payment ledger as a negative payment.
"""

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.payment import Payment
from app.models.reservation import Reservation
from app.services.availability import FREE_STATUSES
from app.services.cancellation_policy import cancellation_refund

STATUS_CANCELLED = FREE_STATUSES[0]  # "cancelled"
CANCELLABLE_STATUSES = ("pending", "confirmed")
PAYMENT_SUCCEEDED = "succeeded"
REFUND_PAYMENT_METHOD = "refund"


class CancellationError(Exception):
    """Base class. Routers map each subclass to an HTTP error."""


class ReservationNotFound(CancellationError):  # -> 404
    pass


class NotCancellable(CancellationError):  # -> 409
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def cancel_reservation(
    db: Session,
    *,
    reservation_id: str,
    user_id: str,
    today: date | None = None,
) -> Reservation:
    """Cancel one of the user's own reservations and return it.

    Raises ReservationNotFound if it doesn't exist or belongs to someone else
    (the two look identical, so a guest can't probe for other people's ids), and
    NotCancellable if the stay has already started or the status can't change.
    Cancelling an already-cancelled reservation succeeds and changes nothing,
    so a double click or a retry is harmless.
    """
    today = today or datetime.now(timezone.utc).date()

    # FOR UPDATE locks the row on PostgreSQL, so a cancel and a payment
    # confirmation (3.1.4) on the same reservation happen one after the other.
    reservation = db.execute(
        select(Reservation)
        .options(selectinload(Reservation.payments))
        .where(Reservation.id == reservation_id, Reservation.user_id == user_id)
        .with_for_update()
    ).scalar_one_or_none()
    if reservation is None:
        raise ReservationNotFound(reservation_id)

    if reservation.status == STATUS_CANCELLED:
        db.rollback()  # nothing to change; release the lock
        return reservation

    if reservation.status not in CANCELLABLE_STATUSES:
        db.rollback()
        raise NotCancellable("This reservation can no longer be cancelled.")
    if reservation.check_in_date < today:
        db.rollback()
        raise NotCancellable("A stay that has already started can't be cancelled.")

    if reservation.status == "confirmed":
        _record_refund(db, reservation, today=today)

    reservation.status = STATUS_CANCELLED
    db.commit()
    db.refresh(reservation)
    return reservation


def _record_refund(db: Session, reservation: Reservation, *, today: date) -> None:
    """Record the policy refund as a negative payment ledger entry.

    The project does not have a live payment-provider adapter yet.  Keeping the
    refund in the existing payment ledger makes the result durable and keeps
    ``amount_paid`` correct for later reads: a $150 refund is represented as a
    succeeded payment of -$150 next to the original $300 charge.
    """
    quote = cancellation_refund(
        reservation.total_price,
        reservation.check_in_date,
        today=today,
    )
    if quote.refund_amount <= 0:
        return

    paid = [
        payment
        for payment in reservation.payments
        if payment.status == PAYMENT_SUCCEEDED and payment.amount is not None
    ]
    if not paid:
        return

    refund_transaction_id = f"refund:{reservation.id}"
    existing = db.execute(
        select(Payment).where(Payment.transaction_id == refund_transaction_id)
    ).scalar_one_or_none()
    if existing is not None:
        return

    paid_amount = sum((payment.amount for payment in paid), 0)
    refund_amount = min(quote.refund_amount, paid_amount)
    if refund_amount <= 0:
        return

    db.add(
        Payment(
            reservation_id=reservation.id,
            amount=-refund_amount,
            payment_method=REFUND_PAYMENT_METHOD,
            transaction_id=refund_transaction_id,
            status=PAYMENT_SUCCEEDED,
            paid_at=datetime.now(timezone.utc),
        )
    )
