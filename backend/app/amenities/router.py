from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.amenities.service import all_amenities, hotel_amenities
from app.database import get_db
from app.models import Hotel

router = APIRouter(tags=["amenities"])


@router.get("/amenities")
def list_amenities(db: Session = Depends(get_db)):
    """Every amenity a hotel can offer, e.g. for the filter panel (1.6.1)."""
    return all_amenities(db)


@router.get("/hotels/{hotel_id}/amenities")
def get_hotel_amenities(hotel_id: str, db: Session = Depends(get_db)):
    """What one hotel offers, for the hotel page (1.6.1 / 1.6.2)."""
    if db.get(Hotel, hotel_id) is None:
        raise HTTPException(status_code=404, detail="Hotel not found.")
    return hotel_amenities(db, hotel_id)
