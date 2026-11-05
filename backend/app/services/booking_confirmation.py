"""Confirm a booking when its charge succeeds (US3.1, task 3.1.4)."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.payment import Payment
from app.models.reservation import Reservation

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
PAYMENT_SUCCEEDED = "succeeded"
_CENT = Decimal("0.01")


class ConfirmationError(Exception):
    """Base class. Routers map each subclass to an HTTP error."""


class ReservationNotFound(ConfirmationError):  # -> 404
    pass


class NotPayable(ConfirmationError):  # -> 409
    pass


class AmountMismatch(ConfirmationError):  # -> 409
    def __init__(self, expected: Decimal, charged: Decimal):
        super().__init__(f"Charged {charged} but the reservation total is {expected}.")
        self.expected = expected
        self.charged = charged


class DuplicatePayment(ConfirmationError):  # -> 409
    pass


@dataclass
class Confirmation:
    reservation: Reservation
    payment: Payment
    already_confirmed: bool  # True when this charge had already been applied


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(_CENT)


def confirm_booking(
    db: Session,
    *,
    reservation_id: str,
    amount,
    payment_method: str,
    transaction_id: str,
    now: datetime | None = None,
    _retried: bool = False,
) -> Confirmation:
    if not transaction_id:
        raise ValueError("transaction_id is required to confirm a booking.")
    now = now or datetime.now(timezone.utc)

    # FOR UPDATE locks the row on PostgreSQL, so a confirmation and a cancel
    # (2.2.1) on the same reservation happen one after the other.
    reservation = db.execute(
        select(Reservation).where(Reservation.id == reservation_id).with_for_update()
    ).scalar_one_or_none()
    if reservation is None:
        raise ReservationNotFound(reservation_id)

    payment = db.execute(
        select(Payment).where(Payment.transaction_id == transaction_id)
    ).scalar_one_or_none()
    if payment is not None and payment.reservation_id != reservation_id:
        db.rollback()
        raise DuplicatePayment("This charge belongs to a different reservation.")

    # Same charge reported again (webhook retry): nothing more to do.
    if (
        payment is not None
        and payment.status == PAYMENT_SUCCEEDED
        and reservation.status == STATUS_CONFIRMED
    ):
        db.rollback()
        return Confirmation(reservation, payment, already_confirmed=True)

    if reservation.status == STATUS_CONFIRMED:
        db.rollback()
        raise DuplicatePayment("This reservation is already paid by another charge.")
    if reservation.status != STATUS_PENDING:
        db.rollback()
        raise NotPayable(f"A {reservation.status} reservation can't be paid.")

    expected, charged = _money(reservation.total_price), _money(amount)
    if charged != expected:
        db.rollback()
        raise AmountMismatch(expected, charged)

    if payment is None:
        payment = Payment(reservation_id=reservation_id, transaction_id=transaction_id)
        db.add(payment)
    payment.amount = charged
    payment.payment_method = payment_method
    payment.status = PAYMENT_SUCCEEDED
    payment.paid_at = now
    reservation.status = STATUS_CONFIRMED

    try:
        db.commit()
    except IntegrityError:
        # Two copies of the same charge raced; the retry sees the winner.
        db.rollback()
        if _retried:
            raise
        return confirm_booking(
            db, reservation_id=reservation_id, amount=amount,
            payment_method=payment_method, transaction_id=transaction_id,
            now=now, _retried=True,
        )
    db.refresh(reservation)
    db.refresh(payment)
    return Confirmation(reservation, payment, already_confirmed=False)