"""US2.1 authenticated room holds; payment confirmation belongs to Sprint 4."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.services.booking_availability import InvalidStay, RoomNotFound, RoomUnavailable, place_hold
from app.services.overlap import OverlappingStay

router = APIRouter(prefix="/reservations", tags=["reservations"])

class CreateReservation(BaseModel):
    room_id: str
    check_in: date
    check_out: date
    num_guests: int = Field(default=1, ge=1, le=10)
    special_requests: str | None = Field(default=None, max_length=1000)

@router.post("", status_code=201)
def create_reservation(body: CreateReservation, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        reservation = place_hold(db, user_id=user.id, room_id=body.room_id,
            check_in=body.check_in, check_out=body.check_out,
            num_guests=body.num_guests, special_requests=body.special_requests)
    except RoomNotFound:
        raise HTTPException(404, "Room not found.")
    except RoomUnavailable:
        raise HTTPException(409, "Room is unavailable for those dates.")
    except OverlappingStay as exc:
        raise HTTPException(409, {
            "code": "overlapping_stay",
            "message": "You already have a reservation at another hotel on those dates.",
            "conflicting_reservation_id": exc.reservation.id,
        })
    except InvalidStay as exc:
        raise HTTPException(422, {"field": exc.field, "message": exc.message})
    return {"id": reservation.id, "room_id": reservation.room_id,
        "status": reservation.status, "check_in": reservation.check_in_date,
        "check_out": reservation.check_out_date,
        "total_price": float(reservation.total_price)}
