import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("hotel_id", "room_number", name="uq_hotel_room_number"),
        # 1.8.1: a member rate, when there is one, is always a real discount.
        CheckConstraint(
            "member_price_per_night IS NULL OR "
            "(member_price_per_night > 0 AND member_price_per_night < price_per_night)",
            name="ck_member_rate_below_public",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hotel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hotels.id"), nullable=False
    )
    room_number: Mapped[str] = mapped_column(String(20), nullable=False)
    room_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="single"
    )
    price_per_night: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    # Lower rate for signed-in members (US1.8). NULL: this room has no member rate.
    member_price_per_night: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    max_guests: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    hotel = relationship("Hotel", back_populates="rooms")
    reservations = relationship("Reservation", back_populates="room")
