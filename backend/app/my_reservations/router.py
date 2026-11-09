"""GET /me/reservations: the logged-in guest's bookings (US4.1, task 4.1.1)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.my_reservations.schemas import MyReservations
from app.my_reservations.service import my_reservations

router = APIRouter(prefix="/me", tags=["my reservations"])


@router.get("/reservations", response_model=MyReservations)
def list_my_reservations(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upcoming, past and cancelled bookings, each as a summary card."""
    grouped = my_reservations(db, user_id=user.id, base_url=str(request.base_url))
    return {
        "upcoming": grouped.upcoming,
        "past": grouped.past,
        "cancelled": grouped.cancelled,
        "counts": {
            "upcoming": len(grouped.upcoming),
            "past": len(grouped.past),
            "cancelled": len(grouped.cancelled),
        },
    }
