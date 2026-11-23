"""POST /reservations/{id}/quote-change: price a change before making it (US2.3, 2.3.2).

Read-only. The modify form (2.3.3) calls it whenever the guest edits the dates,
room or guest count, and shows the new total and what they'd pay or get back.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.requote.schemas import QuoteChangeRequest, QuoteOut, StayOut
from app.requote.service import (
    InvalidChange,
    NotChangeable,
    RequoteError,
    ReservationNotFound,
    RoomNotFound,
    RoomUnavailable,
    Stay,
    quote_change,
)

router = APIRouter(prefix="/reservations", tags=["reservations"])

# (HTTP status, error type) per service error.
_ERRORS: dict[type[RequoteError], tuple[int, str]] = {
    ReservationNotFound: (status.HTTP_404_NOT_FOUND, "not_found"),
    RoomNotFound: (status.HTTP_404_NOT_FOUND, "not_found"),
    NotChangeable: (status.HTTP_409_CONFLICT, "not_changeable"),
    RoomUnavailable: (status.HTTP_409_CONFLICT, "room_unavailable"),
    InvalidChange: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_change"),
}


def _stay(stay: Stay) -> StayOut:
    return StayOut(
        room_id=stay.room_id, check_in=stay.check_in, check_out=stay.check_out,
        nights=stay.nights, num_guests=stay.num_guests, total=float(stay.total),
    )


@router.post("/{reservation_id}/quote-change", response_model=QuoteOut)
def quote(
    reservation_id: str,
    body: QuoteChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        q = quote_change(
            db, reservation_id=reservation_id, user_id=user.id,
            room_id=body.room_id, check_in=body.check_in,
            check_out=body.check_out, num_guests=body.num_guests,
        )
    except RequoteError as error:
        code, kind = _ERRORS[type(error)]
        # Same shape as FastAPI's 422 errors, so the frontend handles all errors alike.
        where = "path" if error.field == "reservation_id" else "body"
        raise HTTPException(
            code, [{"type": kind, "loc": [where, error.field], "msg": error.message}]
        )
    return QuoteOut(
        current=_stay(q.current), proposed=_stay(q.proposed),
        difference=float(q.difference), amount_paid=float(q.amount_paid),
        balance_due=float(q.balance_due), refund_due=float(q.refund_due),
        changed=q.changed,
    )
