"""Points ledger model — US7.1, task 7.1.1.

Every time points change (earned on a confirmed stay, reversed on a refund)
a new row is inserted.  The balance is the SUM of all delta rows for a user,
so the history is fully auditable and reversals are just negative entries.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PointsLedger(Base):
    __tablename__ = "points_ledger"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    reservation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("reservations.id"), nullable=True, index=True
    )
    # Positive = earned, negative = reversed/spent
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g. "stay_earned", "stay_reversed"
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", back_populates="points_ledger")
    reservation = relationship("Reservation", back_populates="points_ledger")
