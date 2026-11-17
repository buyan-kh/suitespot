from datetime import date

from pydantic import BaseModel, Field, model_validator


class QuoteChangeRequest(BaseModel):
    """What the guest wants to change. Leave a field out to keep it as booked.

    Accepts exactly what PATCH /reservations/{id} (2.3.1) accepts, so the quote and
    the change it previews refuse the same requests.
    """

    # Unknown fields are refused, never ignored (same as modify).
    model_config = {"extra": "forbid"}

    room_id: str | None = None
    check_in: date | None = None
    check_out: date | None = None
    num_guests: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def at_least_one_change(self):
        if all(v is None for v in (self.room_id, self.check_in, self.check_out, self.num_guests)):
            raise ValueError("Send at least one of room_id, check_in, check_out, num_guests.")
        return self


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
