"""Re-quote a reservation for new dates, a new room or a new guest count (2.3.2).

Read-only: nothing is written. The new stay is priced like a new booking, at
the room's current nightly rate through stay_total() (the same function
place_hold uses), so a quote always equals what a fresh hold would store.

Change fees (US3.6) are not included yet; when they arrive they belong in
_quote() next to `proposed_total`.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Hotel, Payment, Reservation, Room
from app.services.availability import FREE_STATUSES
from app.services.pricing import money, stay_total

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


def _overlaps_another_stay(
    db: Session, *, room_id: str, check_in: date, check_out: date, skip_id: str
) -> bool:
    """Same half-open [check_in, check_out) rule as availability.is_room_available,
    but the reservation being changed does not count against itself."""
    return db.scalar(
        select(
            exists().where(
                Reservation.room_id == room_id,
                Reservation.id != skip_id,
                Reservation.status.not_in(FREE_STATUSES),
                Reservation.check_in_date < check_out,
                Reservation.check_out_date > check_in,
            )
        )
    )


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
) -> Quote:
    """Quote a change. Any field left as None keeps the booking's current value."""
    today = today or datetime.now(timezone.utc).date()

    # Someone else's reservation gets the same answer as a missing one.
    reservation = db.execute(
        select(Reservation).where(
            Reservation.id == reservation_id, Reservation.user_id == user_id
        )
    ).scalar_one_or_none()
    if reservation is None:
        raise ReservationNotFound("reservation_id", "Reservation not found.")

    if reservation.status not in CHANGEABLE_STATUSES:
        raise NotChangeable(
            "reservation_id", f"A {reservation.status} reservation can't be changed."
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

    if _overlaps_another_stay(
        db, room_id=room.id, check_in=new_in, check_out=new_out, skip_id=reservation.id
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
