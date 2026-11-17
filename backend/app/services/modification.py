"""Change the dates, room or party size of a reservation (US2.3, task 2.3.1).

The guest keeps the same reservation (same id) and asks for different dates, a
different room, or a different number of guests. We re-check that the new room
is free for the new dates, then update the reservation and re-quote its total.

The availability rule lives in app.services.availability and is reused as is, so
search, booking and modifying can't disagree. To ask "is this room free, not
counting this reservation itself?" we briefly mark the reservation cancelled
inside the same locked transaction, ask the rule, then put the status back. The
reservation can therefore move onto dates that overlap its own old dates (for
example extending a stay by a night) without conflicting with itself.

Money is NOT handled here. The new total and the difference are reported so the
price re-quote (2.3.2) and the charge/refund work (3.1 / 3.3) can act on them.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hotel import Hotel
from app.models.reservation import Reservation
from app.models.room import Room
from app.services.availability import FREE_STATUSES, is_room_available
from app.services.booking_availability import (
    InvalidStay,
    RoomNotFound,
    RoomUnavailable,
    release_expired_holds,
)
from app.services.pricing import money, stay_total

MODIFIABLE_STATUSES = ("pending", "confirmed")
STATUS_CANCELLED = FREE_STATUSES[0]


class ModificationError(Exception):
    """Base class. Routers map each subclass to an HTTP error."""


class ReservationNotFound(ModificationError):  # -> 404
    pass


class NotModifiable(ModificationError):  # -> 409
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class Modification:
    reservation: Reservation
    old_total: Decimal
    new_total: Decimal
    changed: bool  # False when the request asked for what the reservation already is

    @property
    def difference(self) -> Decimal:
        return self.new_total - self.old_total


def modify_reservation(
    db: Session,
    *,
    reservation_id: str,
    user_id: str,
    room_id: str | None = None,
    check_in: date | None = None,
    check_out: date | None = None,
    num_guests: int | None = None,
    now: datetime | None = None,
) -> Modification:
    """Apply the changes to one of the user's own reservations and return the result.

    Anything left as None keeps its current value. Raises ReservationNotFound,
    NotModifiable, InvalidStay, RoomNotFound or RoomUnavailable; in every case
    nothing has been changed.
    """
    now = now or datetime.now(timezone.utc)
    today = now.date()

    # Same housekeeping as place_hold: stale unpaid holds must not block the room,
    # and an expired hold of ours is correctly refused below as cancelled.
    release_expired_holds(db, now=now)

    # FOR UPDATE locks the row on PostgreSQL, so a modify, a cancel (2.2.1) and a
    # payment confirmation (3.1.4) on the same reservation happen one at a time.
    reservation = db.execute(
        select(Reservation)
        .where(Reservation.id == reservation_id, Reservation.user_id == user_id)
        .with_for_update()
    ).scalar_one_or_none()
    if reservation is None:
        raise ReservationNotFound(reservation_id)
    if reservation.status not in MODIFIABLE_STATUSES:
        db.rollback()
        raise NotModifiable(f"A {reservation.status} reservation can't be changed.")
    if reservation.check_in_date < today:
        db.rollback()
        raise NotModifiable("A stay that has already started can't be changed.")

    new_room_id = room_id or reservation.room_id
    new_in = check_in or reservation.check_in_date
    new_out = check_out or reservation.check_out_date
    new_guests = num_guests if num_guests is not None else reservation.num_guests
    old_total = money(reservation.total_price)

    if (new_room_id, new_in, new_out, new_guests) == (
        reservation.room_id, reservation.check_in_date,
        reservation.check_out_date, reservation.num_guests,
    ):
        db.rollback()  # nothing to change; release the lock
        return Modification(reservation, old_total, old_total, changed=False)

    if new_out <= new_in:
        db.rollback()
        raise InvalidStay("check_out", "Check-out must be after check-in.")
    if new_in < today:
        db.rollback()
        raise InvalidStay("check_in", "Check-in cannot be in the past.")
    if new_guests < 1:
        db.rollback()
        raise InvalidStay("num_guests", "Number of guests must be at least 1.")

    # Lock the room we are moving to, like place_hold, so two guests can't both
    # take the last free dates at the same moment.
    room = db.execute(
        select(Room).where(Room.id == new_room_id).with_for_update()
    ).scalar_one_or_none()
    hotel = db.get(Hotel, room.hotel_id) if room is not None else None
    if room is None or hotel is None or not hotel.is_active:
        db.rollback()
        raise RoomNotFound(f"Room {new_room_id} does not exist.")
    if new_guests > room.max_guests:
        db.rollback()
        raise InvalidStay("num_guests", f"This room sleeps at most {room.max_guests} guests.")

    original_status = reservation.status
    reservation.status = STATUS_CANCELLED  # so the rule doesn't count us against ourselves
    db.flush()
    if not is_room_available(db, room.id, new_in, new_out):
        db.rollback()  # discards the temporary status and releases the locks
        raise RoomUnavailable("That room is not available for the new dates.")
    reservation.status = original_status

    new_total = stay_total(room.price_per_night, (new_out - new_in).days)
    reservation.room_id = room.id
    reservation.check_in_date = new_in
    reservation.check_out_date = new_out
    reservation.num_guests = new_guests
    reservation.total_price = new_total
    db.commit()
    db.refresh(reservation)
    return Modification(reservation, old_total, new_total, changed=True)
