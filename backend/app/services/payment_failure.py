"""Record a failed card charge and decide whether the guest can retry (US3.1, task 3.1.5).

The charge endpoint (3.1.2) calls record_failed_payment when the payment
provider reports a decline or error, and retry_status before offering a Retry
button. A successful retry goes through confirm_booking (3.1.4) as usual.

Rules:
- A failure keeps the hold. The guest can retry until the original
  HOLD_MINUTES hold runs out; a failure does not extend it.
- After MAX_FAILED_ATTEMPTS failures on one hold, the hold is released
  (status "cancelled") so the room is not stuck behind repeated declines.
- A failure never undoes a charge that already succeeded.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.payment import Payment
from app.models.reservation import Reservation
from app.services.availability import FREE_STATUSES
from app.services.booking_availability import HOLD_MINUTES
from app.services.pricing import money

MAX_FAILED_ATTEMPTS = 3

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = FREE_STATUSES[0]  # "cancelled"
PAYMENT_PENDING = "pending"
PAYMENT_FAILED = "failed"
PAYMENT_SUCCEEDED = "succeeded"


class PaymentFailureError(Exception):
    """Base class. Routers map each subclass to an HTTP error."""


class ReservationNotFound(PaymentFailureError):  # -> 404
    pass


class DuplicatePayment(PaymentFailureError):  # -> 409
    pass


@dataclass
class FailedPayment:
    reservation: Reservation
    payment: Payment
    attempts_left: int  # retries still allowed on this hold
    hold_released: bool  # True when this failure used up the last attempt
    already_recorded: bool  # True when this exact failure was reported before


@dataclass
class RetryStatus:
    allowed: bool
    attempts_left: int
    reason: str | None  # None, "not_payable", "hold_expired" or "too_many_attempts"
    hold_expires_at: datetime | None


def _utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _failed_count(db: Session, reservation_id: str) -> int:
    return db.execute(
        select(func.count()).select_from(Payment).where(
            Payment.reservation_id == reservation_id,
            Payment.status == PAYMENT_FAILED,
        )
    ).scalar_one()


def _attempts_left(db: Session, reservation: Reservation) -> int:
    if reservation.status != STATUS_PENDING:
        return 0
    return max(0, MAX_FAILED_ATTEMPTS - _failed_count(db, reservation.id))


def record_failed_payment(
    db: Session,
    *,
    reservation_id: str,
    amount,
    payment_method: str,
    transaction_id: str,
    _retried: bool = False,
) -> FailedPayment:
    if not transaction_id:
        raise ValueError("transaction_id is required to record a failed payment.")

    # FOR UPDATE locks the row on PostgreSQL, so a failure, a success (3.1.4)
    # and a cancel (2.2.1) on the same reservation happen one after the other.
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

    # Same failure reported again, or a failure arriving after the same charge
    # already succeeded (webhooks can come out of order): change nothing.
    if payment is not None and payment.status in (PAYMENT_FAILED, PAYMENT_SUCCEEDED):
        attempts_left = _attempts_left(db, reservation)
        db.rollback()
        return FailedPayment(reservation, payment, attempts_left,
                             hold_released=False, already_recorded=True)

    if payment is None:
        payment = Payment(reservation_id=reservation_id, transaction_id=transaction_id)
        db.add(payment)
    payment.amount = money(amount)
    payment.payment_method = payment_method
    payment.status = PAYMENT_FAILED
    payment.paid_at = None

    # Only a pending hold counts attempts. A failure on a confirmed, cancelled
    # or completed reservation is kept for the record and changes nothing else.
    hold_released = False
    if reservation.status == STATUS_PENDING:
        db.flush()
        if _failed_count(db, reservation_id) >= MAX_FAILED_ATTEMPTS:
            reservation.status = STATUS_CANCELLED  # frees the room
            hold_released = True

    try:
        db.commit()
    except IntegrityError:
        # Two copies of the same failure raced; the retry sees the winner.
        db.rollback()
        if _retried:
            raise
        return record_failed_payment(
            db, reservation_id=reservation_id, amount=amount,
            payment_method=payment_method, transaction_id=transaction_id,
            _retried=True,
        )
    db.refresh(reservation)
    db.refresh(payment)
    return FailedPayment(
        reservation, payment, _attempts_left(db, reservation),
        hold_released=hold_released, already_recorded=False,
    )


def retry_status(
    db: Session,
    *,
    reservation_id: str,
    now: datetime | None = None,
) -> RetryStatus:
    """Can the guest try another card on this reservation right now?"""
    now = now or datetime.now(timezone.utc)
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationNotFound(reservation_id)

    expires_at = (
        _utc(reservation.created_at) + timedelta(minutes=HOLD_MINUTES)
        if reservation.created_at else None
    )
    attempts_left = _attempts_left(db, reservation)

    if reservation.status != STATUS_PENDING:
        failed = _failed_count(db, reservation_id)
        reason = (
            "too_many_attempts"
            if reservation.status == STATUS_CANCELLED and failed >= MAX_FAILED_ATTEMPTS
            else "not_payable"
        )
        return RetryStatus(False, 0, reason, expires_at)
    if attempts_left == 0:
        return RetryStatus(False, 0, "too_many_attempts", expires_at)
    if expires_at is not None and now >= expires_at:
        return RetryStatus(False, attempts_left, "hold_expired", expires_at)
    return RetryStatus(True, attempts_left, None, expires_at)
