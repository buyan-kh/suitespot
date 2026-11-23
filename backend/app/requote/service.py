"""Re-quote a reservation for new dates, a new room or a new guest count (2.3.2).

Read-only: nothing is written. The new stay is priced like a new booking, at
the room's current nightly rate through stay_total() (the same function
place_hold uses), so a quote always equals what a fresh hold would store.

It refuses whatever modify (2.3.1) refuses, with the same errors, including the
US2.4 rule: no stays at two different hotels on the same nights.

Change fees (US3.6) are not included yet; when they arrive they belong in
_quote() next to `proposed_total`.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Hotel, Payment, Reservation, Room
from app.services.availability import FREE_STATUSES
from app.services.booking_availability import HOLD_MINUTES, STATUS_PENDING, OverlappingStay
from app.services.pricing import money, stay_total
from app.services.stay_overlap import find_overlapping_stay

CHANGEABLE_STATUSES = ("pending", "confirmed")
PAYMENT_SUCCEEDED = "succeeded"


class RequoteError(Exception):
    """Base class. The router maps each subclass to an HTTP error."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class ReservationNotFound(RequoteError):  # -> 404
    pass


class NotChangeable(RequoteError):  # -> 409
    pass


class InvalidChange(RequoteError):  # -> 422
    pass


class RoomNotFound(RequoteError):  # -> 404
    pass


class RoomUnavailable(RequoteError):  # -> 409
    pass


@dataclass
class Stay:
    room_id: str
    check_in: date
    check_out: date
    num_guests: int
    total: Decimal

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


@dataclass
class Quote:
    current: Stay
    proposed: Stay
    difference: Decimal  # proposed.total - current.total
    amount_paid: Decimal  # succeeded payments only
    balance_due: Decimal  # what the guest would still owe
    refund_due: Decimal  # what the guest would get back
    changed: bool  # False when the request matches the booking exactly


def _hold_expired(reservation: Reservation, now: datetime) -> bool:
    """An unpaid hold past HOLD_MINUTES. place_hold and modify cancel these before
    checking (release_expired_holds); the quote is read-only, so it just skips them."""
    if reservation.status != STATUS_PENDING or reservation.created_at is None:
        return False
    created = reservation.created_at
    if created.tzinfo is None:  # SQLite returns naive datetimes; they are UTC
        created = created.replace(tzinfo=timezone.utc)
    return now - created >= timedelta(minutes=HOLD_MINUTES)


def _overlaps_another_stay(
    db: Session, *, room_id: str, check_in: date, check_out: date, skip_id: str,
    now: datetime,
) -> bool:
    """Same half-open [check_in, check_out) rule as availability.is_room_available,
    but the reservation being changed does not count against itself, and expired
    holds don't count (filtered in Python: tz-aware comparison in SQLite is unreliable)."""
    others = db.scalars(
        select(Reservation).where(
            Reservation.room_id == room_id,
            Reservation.id != skip_id,
            Reservation.status.not_in(FREE_STATUSES),
            Reservation.check_in_date < check_out,
            Reservation.check_out_date > check_in,
        )
    ).all()
    return any(not _hold_expired(r, now) for r in others)


def _amount_paid(db: Session, reservation_id: str) -> Decimal:
    amounts = db.scalars(
        select(Payment.amount).where(
            Payment.reservation_id == reservation_id,
            Payment.status == PAYMENT_SUCCEEDED,
        )
    ).all()
    return money(sum((Decimal(str(a)) for a in amounts), Decimal("0")))


def quote_change(
    db: Session,
    *,
    reservation_id: str,
    user_id: str,
    room_id: str | None = None,
    check_in: date | None = None,
    check_out: date | None = None,
    num_guests: int | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> Quote:
    """Quote a change. Any field left as None keeps the booking's current value."""
    now = now or datetime.now(timezone.utc)
    today = today or now.date()

    # Someone else's reservation gets the same answer as a missing one.
    reservation = db.execute(
        select(Reservation).where(
            Reservation.id == reservation_id, Reservation.user_id == user_id
        )
    ).scalar_one_or_none()
    if reservation is None:
        raise ReservationNotFound("reservation_id", "Reservation not found.")

    # An expired unpaid hold is cancelled by modify before it looks; say the same.
    status_now = "cancelled" if _hold_expired(reservation, now) else reservation.status
    if status_now not in CHANGEABLE_STATUSES:
        raise NotChangeable(
            "reservation_id", f"A {status_now} reservation can't be changed."
        )
    if reservation.check_in_date < today:
        raise NotChangeable(
            "reservation_id", "A stay that has already started can't be changed."
        )

    new_room_id = room_id or reservation.room_id
    new_in = check_in or reservation.check_in_date
    new_out = check_out or reservation.check_out_date
    new_guests = reservation.num_guests if num_guests is None else num_guests

    if new_out <= new_in:
        raise InvalidChange("check_out", "Check-out must be after check-in.")
    if new_in < today:
        raise InvalidChange("check_in", "Check-in cannot be in the past.")
    if new_guests < 1:
        raise InvalidChange("num_guests", "Number of guests must be at least 1.")

    room = db.get(Room, new_room_id)
    hotel = db.get(Hotel, room.hotel_id) if room is not None else None
    if room is None or hotel is None or not hotel.is_active or not room.is_available:
        raise RoomNotFound("room_id", "Room not found.")
    if new_guests > room.max_guests:
        raise InvalidChange(
            "num_guests", f"This room sleeps at most {room.max_guests} guests."
        )

    # US2.4, checked at the same point as modify so both report the same error.
    # Modify releases expired holds first; the quote is read-only, so it skips one
    # instead. (If that expired hold hides a second clash, the quote misses it until
    # the hold is released by the next booking or modify; modify still refuses.)
    conflict = find_overlapping_stay(
        db, user_id=user_id, hotel_id=room.hotel_id, check_in=new_in,
        check_out=new_out, exclude_reservation_id=reservation.id,
    )
    if conflict is not None and not _hold_expired(
        db.get(Reservation, conflict.reservation_id), now
    ):
        raise OverlappingStay(conflict)

    if _overlaps_another_stay(
        db, room_id=room.id, check_in=new_in, check_out=new_out, skip_id=reservation.id,
        now=now,
    ):
        raise RoomUnavailable(
            "room_id", "This room is not available for those dates."
        )

    current = Stay(
        room_id=reservation.room_id,
        check_in=reservation.check_in_date,
        check_out=reservation.check_out_date,
        num_guests=reservation.num_guests,
        total=money(reservation.total_price),
    )
    changed = (room.id, new_in, new_out, new_guests) != (
        current.room_id, current.check_in, current.check_out, current.num_guests
    )
    # Nothing to change: keep the price the guest already has, even if the
    # room's rate moved since they booked.
    proposed_total = (
        stay_total(room.price_per_night, (new_out - new_in).days) if changed else current.total
    )
    proposed = Stay(room.id, new_in, new_out, new_guests, proposed_total)

    paid = _amount_paid(db, reservation.id)
    zero = Decimal("0.00")
    return Quote(
        current=current,
        proposed=proposed,
        difference=money(proposed.total - current.total),
        amount_paid=paid,
        balance_due=max(money(proposed.total - paid), zero),
        refund_due=max(money(paid - proposed.total), zero),
        changed=changed,
    )
