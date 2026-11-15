from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hotel import Hotel
from app.models.reservation import Reservation
from app.models.room import Room
from app.services.availability import FREE_STATUSES


@dataclass(frozen=True)
class StayConflict:
    reservation_id: str
    hotel_id: str
    hotel_name: str
    check_in: date
    check_out: date


def find_overlapping_stay(
    db: Session,
    *,
    user_id: str,
    hotel_id: str,
    check_in: date,
    check_out: date,
    exclude_reservation_id: str | None = None,
) -> StayConflict | None:
    """The guest's earliest stay at a different hotel that shares a night, or None.

    exclude_reservation_id lets a reservation being changed ignore itself.
    """
    stmt = (
        select(
            Reservation.id, Hotel.id, Hotel.name,
            Reservation.check_in_date, Reservation.check_out_date,
        )
        .join(Room, Room.id == Reservation.room_id)
        .join(Hotel, Hotel.id == Room.hotel_id)
        .where(
            Reservation.user_id == user_id,
            Reservation.status.not_in(FREE_STATUSES),
            Hotel.id != hotel_id,
            Reservation.check_in_date < check_out,  # starts before the new stay ends
            Reservation.check_out_date > check_in,  # ends after the new stay starts
        )
        .order_by(Reservation.check_in_date, Reservation.id)
        .limit(1)
    )
    if exclude_reservation_id is not None:
        stmt = stmt.where(Reservation.id != exclude_reservation_id)
    row = db.execute(stmt).first()
    return StayConflict(*row) if row else None
