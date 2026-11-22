"""GET /reservations/{id}/breakdown — full price breakdown (US3.2, task 3.2.1).

Returns the rate per night, number of nights, each fee line item, tax, and
total so the checkout screen can show a fully itemised summary before the
guest pays.

The ``total`` in this response always equals ``Reservation.total_price``
because both are computed by the same fee rules in ``app.services.pricing``.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import Reservation, Room, User
from app.services.pricing import _FEE_RULES, _TAX_RATE, money, stay_total

router = APIRouter(prefix="/reservations", tags=["reservations"])


class LineItem(BaseModel):
    label: str
    amount: float


class BreakdownResponse(BaseModel):
    rate_per_night: float
    nights: int
    subtotal: float
    fees: list[LineItem]
    tax: float
    total: float


@router.get("/{reservation_id}/breakdown", response_model=BreakdownResponse)
def get_breakdown(
    reservation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation = db.execute(
        select(Reservation).where(
            Reservation.id == reservation_id,
            Reservation.user_id == user.id,
        )
    ).scalar_one_or_none()
    if reservation is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Reservation not found.",
        )

    room = db.get(Room, reservation.room_id)
    rate = money(room.price_per_night) if room else money(0)
    nights = (reservation.check_out_date - reservation.check_in_date).days
    subtotal = stay_total(rate, nights)

    fee_lines: list[LineItem] = []
    fee_total = Decimal("0.00")
    for label, kind, value in _FEE_RULES:
        if kind == "pct":
            amt = money(subtotal * value)
        elif kind == "night":
            amt = money(value * nights)
        else:  # stay
            amt = money(value)
        fee_lines.append(LineItem(label=label, amount=float(amt)))
        fee_total += amt

    pre_tax = subtotal + fee_total
    tax = money(pre_tax * _TAX_RATE)
    total = pre_tax + tax

    return BreakdownResponse(
        rate_per_night=float(rate),
        nights=nights,
        subtotal=float(subtotal),
        fees=fee_lines,
        tax=float(tax),
        total=float(total),
    )
