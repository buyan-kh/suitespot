import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Amenity(Base):
    """Something a hotel offers, e.g. "Pool". name is what the UI shows."""

    __tablename__ = "amenities"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Stable key for URLs and code, e.g. "free-parking".
    slug: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class HotelAmenity(Base):
    """Links a hotel to one amenity. The composite key stops duplicates."""

    __tablename__ = "hotel_amenities"

    hotel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hotels.id"), primary_key=True, index=True
    )
    amenity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("amenities.id"), primary_key=True
    )
