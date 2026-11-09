from datetime import date

from pydantic import BaseModel, Field


class QuoteChangeRequest(BaseModel):
    """What the guest wants to change. Leave a field out to keep it as booked."""

    room_id: str | None = None
    check_in: date | None = None
    check_out: date | None = None
    num_guests: int | None = Field(default=None, ge=1, le=10)


class StayOut(BaseModel):
    room_id: str
    check_in: date
    check_out: date
    nights: int
    num_guests: int
    total: float


class QuoteOut(BaseModel):
    current: StayOut
    proposed: StayOut
    difference: float
    amount_paid: float
    balance_due: float
    refund_due: float
    changed: bool
