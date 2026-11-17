from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.member_rates.service import member_rates
from app.models import Hotel

router = APIRouter(tags=["member rates"])


@router.get("/hotels/{hotel_id}/member-rates")
def get_member_rates(hotel_id: str, db: Session = Depends(get_db)):
    """Rooms at this hotel with a lower member rate (1.8.1, for 1.8.2).

    Public on purpose: the audience is visitors who don't have an account yet.
    """
    hotel = db.get(Hotel, hotel_id)
    if hotel is None or not hotel.is_active:  # same rule as the hotel page
        raise HTTPException(status_code=404, detail="Hotel not found.")
    return member_rates(db, hotel_id)
