"""POST /reservations/{id}/verify-total: does the shown price match what we charge?

(US3.2, task 3.2.2.) Call it right before the guest pays, with the total the
screen is displaying. 200 means that number is exactly what will be charged. 409
means it isn't, and the error carries the real total to show instead.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import Reservation, User
from app.schemas.verify_total import VerifyTotalRequest, VerifyTotalResponse
from app.services.pricing import TotalMismatch, verify_displayed_total

router = APIRouter(prefix="/reservations", tags=["reservations"])

CHARGEABLE_STATUSES = ("pending", "confirmed")


def _error(kind: str, loc: list[str], message: str, **ctx) -> list[dict]:
    # Same shape as FastAPI's 422 errors, so the frontend handles all errors alike.
    error = {"type": kind, "loc": loc, "msg": message}
    if ctx:
        error["ctx"] = ctx
    return [error]


@router.post("/{reservation_id}/verify-total", response_model=VerifyTotalResponse)
def verify_total(
    reservation_id: str,
    body: VerifyTotalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Only the owner can see a reservation; anyone else gets the same 404 as a missing one.
    reservation = db.execute(
        select(Reservation).where(
            Reservation.id == reservation_id, Reservation.user_id == user.id
        )
    ).scalar_one_or_none()
    if reservation is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            _error("not_found", ["path", "reservation_id"], "Reservation not found."),
        )
    if reservation.status not in CHARGEABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            _error("not_payable", ["path", "reservation_id"],
                   f"A {reservation.status} reservation can't be paid."),
        )
    try:
        total = verify_displayed_total(reservation, body.displayed_total)
    except TotalMismatch as mismatch:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            _error("total_mismatch", ["body", "displayed_total"],
                   "The total changed. Refresh the price before paying.",
                   expected_total=str(mismatch.expected)),
        )
    return VerifyTotalResponse(matches=True, total=float(total))
