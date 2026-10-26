from sqlalchemy import select
from sqlalchemy.orm import Session

from app.amenities.models import Amenity, HotelAmenity


def serialize(amenity: Amenity) -> dict:
    return {"slug": amenity.slug, "name": amenity.name}


def all_amenities(db: Session) -> dict:
    """Every amenity, by name: {"amenities": [{"slug", "name"}, ...]}."""
    rows = db.scalars(select(Amenity).order_by(Amenity.name)).all()
    return {"amenities": [serialize(a) for a in rows]}


def hotel_amenities(db: Session, hotel_id: str) -> dict:
    """One hotel's amenities, by name. A hotel with none gets []."""
    rows = db.scalars(
        select(Amenity)
        .join(HotelAmenity, HotelAmenity.amenity_id == Amenity.id)
        .where(HotelAmenity.hotel_id == hotel_id)
        .order_by(Amenity.name)
    ).all()
    return {"amenities": [serialize(a) for a in rows]}
