"""US7.3, task 7.3.1 — Redemption router.

Endpoints
---------
GET  /reservations/{id}/redemption/quote
    Returns a RedemptionQuoteResponse without committing anything.
    Query param: points (int, required)

POST /reservations/{id}/redemption/apply
    Applies the redemption: writes a ledger row and returns the result.
    Body: { "points": <int> }
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.reservation import Reservation
from app.services.redemption import (
    MIN_REDEMPTION_POINTS,
    POINTS_PER_DOLLAR,
    AlreadyRedeemed,
    NotRedeemable,
    apply_redemption,
    redemption_quote,
)

router = APIRouter(tags=["redemption"])


# ── Pydantic schemas ────────────────────────────────────────────────────────
class RedemptionQuoteResponse(BaseModel):
    points_requested: int
    points_applied: int
    dollar_discount: float
    new_total: float
    balance_before: int
    balance_after: int
    # Informational constants echoed back so the frontend doesn't hardcode them.
    points_per_dollar: int = POINTS_PER_DOLLAR
    min_redemption_points: int = MIN_REDEMPTION_POINTS


class RedemptionApplyRequest(BaseModel):
    points: int = Field(..., gt=0, description="Points to redeem (must be > 0)")


# ── helpers ─────────────────────────────────────────────────────────────────
def _get_owned_reservation(
    reservation_id: str,
    current_user,
    db: Session,
) -> Reservation:
    reservation = db.get(Reservation, reservation_id)
    if reservation is None or reservation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found.")
    return reservation


def _quote_to_response(quote) -> RedemptionQuoteResponse:
    return RedemptionQuoteResponse(
        points_requested=quote.points_requested,
        points_applied=quote.points_applied,
        dollar_discount=float(quote.dollar_discount),
        new_total=float(quote.new_total),
        balance_before=quote.balance_before,
        balance_after=quote.balance_after,
    )


# ── routes ──────────────────────────────────────────────────────────────────
@router.get(
    "/reservations/{reservation_id}/redemption/quote",
    response_model=RedemptionQuoteResponse,
)
def get_redemption_quote(
    reservation_id: str,
    points: int = Query(..., gt=0, description="Points the user wants to redeem"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview a redemption without applying it."""
    reservation = _get_owned_reservation(reservation_id, current_user, db)
    try:
        quote = redemption_quote(
            db,
            user_id=current_user.id,
            reservation=reservation,
            points_requested=points,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return _quote_to_response(quote)


@router.post(
    "/reservations/{reservation_id}/redemption/apply",
    response_model=RedemptionQuoteResponse,
    status_code=status.HTTP_200_OK,
)
def post_redemption_apply(
    reservation_id: str,
    body: RedemptionApplyRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply a redemption and write a ledger row."""
    reservation = _get_owned_reservation(reservation_id, current_user, db)
    try:
        quote = apply_redemption(
            db,
            user_id=current_user.id,
            reservation=reservation,
            points_requested=body.points,
        )
    except NotRedeemable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except AlreadyRedeemed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return _quote_to_response(quote)
