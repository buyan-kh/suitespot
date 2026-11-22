"""US7.1, task 7.1.1 — Points ledger earn rules.

Earn rate: 1 point per $1 of the reservation's total_price (rounded down).
Points are recorded as a new PointsLedger row; the running balance is the
sum of all delta rows for the user.

Usage:
    earn_points(db, reservation=reservation)       # on confirmation
    reverse_points(db, reservation=reservation)    # on refund / cancellation
    get_balance(db, user_id=user_id)               # current balance
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.points import PointsLedger
from app.models.reservation import Reservation

POINTS_PER_DOLLAR = 1  # 1 point per $1 spent


def _points_for(reservation: Reservation) -> int:
    """How many points a reservation earns (floor division)."""
    return int(Decimal(str(reservation.total_price)))


def earn_points(
    db: Session,
    *,
    reservation: Reservation,
    note: str | None = None,
) -> PointsLedger:
    """Award points for a completed/confirmed stay and return the ledger row."""
    delta = _points_for(reservation)
    entry = PointsLedger(
        user_id=reservation.user_id,
        reservation_id=reservation.id,
        delta=delta,
        reason="stay_earned",
        note=note,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def reverse_points(
    db: Session,
    *,
    reservation: Reservation,
    note: str | None = None,
) -> PointsLedger | None:
    """Reverse any points previously earned for this reservation.

    If no points were earned for the reservation, returns None silently
    so the caller doesn't need to check first.
    """
    # Sum up what was earned for this reservation.
    earned: int = db.execute(
        select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(
            PointsLedger.reservation_id == reservation.id
        )
    ).scalar_one()

    if earned <= 0:
        return None

    entry = PointsLedger(
        user_id=reservation.user_id,
        reservation_id=reservation.id,
        delta=-earned,
        reason="stay_reversed",
        note=note,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_balance(db: Session, *, user_id: str) -> int:
    """Return the current points balance for a user (never negative)."""
    total: int = db.execute(
        select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(
            PointsLedger.user_id == user_id
        )
    ).scalar_one()
    return max(0, int(total))
