from datetime import date

from pydantic import BaseModel, Field, model_validator


class ModifyReservation(BaseModel):
    """What to change. Anything left out keeps its current value."""

    # Unknown fields (status, total_price, user_id...) are refused, never ignored.
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


class PriceChange(BaseModel):
    old_total: float
    new_total: float
    difference: float  # positive: costs more, negative: costs less


class ModifyResponse(BaseModel):
    id: str
    room_id: str
    status: str
    check_in: date
    check_out: date
    num_guests: int
    total_price: float
    changed: bool
    price_change: PriceChange
