"""US2.4, task 2.4.1 — Overlap detection query across reservations.

A user must not hold two hotel rooms on overlapping nights.  This module
provides the query that checks for a cross-hotel overlap and the exception
the booking layer raises when one is found.

The overlap rule (half-open intervals):
    existing stay [A, B) overlaps new stay [C, D)  ⟺  A < D and B > C

Usage
-----
    from app.services.overlap import OverlappingStay, find_overlapping_stay

    conflict = find_overlapping_stay(
        db,
        user_id=user.id,
        hotel_id=room.hotel_id,
        check_in=check_in,
        check_out=check_out,
    )
    if conflict:
        raise OverlappingStay(conflict)

The booking layer (booking_availability.py) calls this after the per-room
availability check so both constraints are enforced before the hold is saved.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reservation import Reservation
from app.models.room import Room
from app.services.availability import FREE_STATUSES


class OverlappingStay(Exception):
    """Raised when a user already has a reservation at another hotel that
    overlaps the requested dates."""

    def __init__(self, conflicting_reservation: Reservation) -> None:
        self.reservation = conflicting_reservation
        super().__init__(
            f"You already have a reservation ({conflicting_reservation.id}) "
            f"at another hotel that overlaps those dates."
        )


def find_overlapping_stay(
    db: Session,
    *,
    user_id: str,
    hotel_id: str,
    check_in: date,
    check_out: date,
    exclude_reservation_id: str | None = None,
) -> Reservation | None:
    """Return an existing active reservation that overlaps [check_in, check_out)
    at a *different* hotel, or None if no conflict exists.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    user_id:
        The guest whose reservations are searched.
    hotel_id:
        The hotel the guest is *trying* to book.  Reservations at the same
        hotel are excluded because a guest can book multiple rooms at the
        same property on the same nights.
    check_in / check_out:
        The requested stay (half-open interval).
    exclude_reservation_id:
        Skip this reservation ID when checking (used by the modify endpoint
        so a date-change doesn't conflict with the reservation being changed).
    """
    stmt = (
        select(Reservation)
        .join(Room, Room.id == Reservation.room_id)
        .where(
            Reservation.user_id == user_id,
            Reservation.status.not_in(FREE_STATUSES),
            # Different hotel only — same hotel is fine
            Room.hotel_id != hotel_id,
            # Half-open overlap: existing.check_in < new.check_out AND
            #                    existing.check_out > new.check_in
            Reservation.check_in_date < check_out,
            Reservation.check_out_date > check_in,
        )
    )

    if exclude_reservation_id:
        stmt = stmt.where(Reservation.id != exclude_reservation_id)

    return db.scalars(stmt).first()
