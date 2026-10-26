from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hotel import Hotel
from app.models.reservation import Reservation
from app.models.room import Room
from app.services.availability import FREE_STATUSES, is_room_available

HOLD_MINUTES = 15
STATUS_PENDING = "pending"
STATUS_CANCELLED = FREE_STATUSES[0]


class BookingError(Exception):
    """Base class for booking errors."""


class RoomNotFound(BookingError):
    pass


class InvalidStay(BookingError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class RoomUnavailable(BookingError):
    pass


def _utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def release_expired_holds(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Cancel pending reservations older than HOLD_MINUTES."""
    now = now or datetime.now(timezone.utc)
    cutoff = timedelta(minutes=HOLD_MINUTES)

    pending = db.execute(
        select(Reservation).where(
            Reservation.status == STATUS_PENDING
        )
    ).scalars()

    released = 0

    for reservation in pending:
        if (
            reservation.created_at
            and now - _utc(reservation.created_at) >= cutoff
        ):
            reservation.status = STATUS_CANCELLED
            released += 1

    if released:
        db.commit()

    return released


def place_hold(
    db: Session,
    *,
    user_id: str,
    room_id: str,
    check_in: date,
    check_out: date,
    num_guests: int = 1,
    special_requests: str | None = None,
    now: datetime | None = None,
) -> Reservation:
    now = now or datetime.now(timezone.utc)

    if check_out <= check_in:
        raise InvalidStay(
            "check_out",
            "Check-out must be after check-in.",
        )

    if check_in < now.date():
        raise InvalidStay(
            "check_in",
            "Check-in cannot be in the past.",
        )

    if num_guests < 1:
        raise InvalidStay(
            "num_guests",
            "Number of guests must be at least 1.",
        )

    release_expired_holds(db, now=now)

    # FOR UPDATE locks the room row on PostgreSQL, so two guests submitting at
    # the same moment are checked one after the other. SQLite ignores it.
    room = db.execute(
        select(Room).where(Room.id == room_id).with_for_update()
    ).scalar_one_or_none()
    
    hotel = db.get(Hotel, room.hotel_id) if room is not None else None
    if room is None or hotel is None or not hotel.is_active:
        db.rollback()  # release the room lock
        raise RoomNotFound(f"Room {room_id} does not exist.")
        
    if num_guests > room.max_guests:
        raise InvalidStay(
            "num_guests",
            f"This room sleeps at most {room.max_guests} guests.",
        )

    if not is_room_available(db, room.id, check_in, check_out):
        db.rollback()  # release the room lock
        raise RoomUnavailable("This room is no longer available for those dates.")

    nights = (check_out - check_in).days
    total_price = Decimal(str(room.price_per_night)) * nights

    reservation = Reservation(
        user_id=user_id,
        room_id=room.id,
        check_in_date=check_in,
        check_out_date=check_out,
        num_guests=num_guests,
        total_price=total_price,
        status=STATUS_PENDING,
        special_requests=special_requests,
    )

    db.add(reservation)
    db.commit()
    db.refresh(reservation)

    return reservation
