from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.schemas.modify import ModifyReservation, ModifyResponse, PriceChange
from app.services.booking_availability import InvalidStay, RoomNotFound, RoomUnavailable
from app.services.modification import (
    NotModifiable,
    ReservationNotFound,
    modify_reservation,
)

router = APIRouter(prefix="/reservations", tags=["reservations"])


def _error(kind: str, loc: list[str], message: str) -> list[dict]:
    # Same shape as FastAPI's 422 errors, so the frontend handles all errors alike.
    return [{"type": kind, "loc": loc, "msg": message}]


@router.patch("/{reservation_id}", response_model=ModifyResponse)
def modify(
    reservation_id: str,
    body: ModifyReservation,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = modify_reservation(
            db, reservation_id=reservation_id, user_id=user.id,
            room_id=body.room_id, check_in=body.check_in,
            check_out=body.check_out, num_guests=body.num_guests,
        )
    except ReservationNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            _error("not_found", ["path", "reservation_id"], "Reservation not found."),
        )
    except NotModifiable as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            _error("not_modifiable", ["path", "reservation_id"], error.message),
        )
    except RoomNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            _error("not_found", ["body", "room_id"], "Room not found."),
        )
    except RoomUnavailable as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            _error("room_unavailable", ["body"], str(error)),
        )
    except InvalidStay as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            _error("invalid_stay", ["body", error.field], error.message),
        )

    reservation = result.reservation
    return ModifyResponse(
        id=reservation.id,
        room_id=reservation.room_id,
        status=reservation.status,
        check_in=reservation.check_in_date,
        check_out=reservation.check_out_date,
        num_guests=reservation.num_guests,
        total_price=float(reservation.total_price),
        changed=result.changed,
        price_change=PriceChange(
            old_total=float(result.old_total),
            new_total=float(result.new_total),
            difference=float(result.difference),
        ),
    )
