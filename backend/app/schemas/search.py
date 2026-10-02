from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MAX_GUESTS = 10
MAX_STAY_NIGHTS = 30


class HotelSearchParams(BaseModel):
    """Query parameters for hotel search.

    Accepts the camelCase keys the frontend sends (checkIn, checkOut) as well
    as snake_case. Use in a route as:

        def search(params: Annotated[HotelSearchParams, Query()]): ...
    """

    model_config = {"populate_by_name": True, "str_strip_whitespace": True}

    destination: str = Field(min_length=1, max_length=100)
    check_in: date = Field(alias="checkIn")
    check_out: date = Field(alias="checkOut")
    guests: int = Field(default=1, ge=1, le=MAX_GUESTS)
    min_price: float | None = Field(default=None, ge=0, alias="minPrice")
    max_price: float | None = Field(default=None, ge=0, alias="maxPrice")
    min_stars: int | None = Field(default=None, ge=1, le=5, alias="minStars")
    room_type: Literal["single", "double", "suite"] | None = Field(
        default=None, alias="roomType"
    )

    @model_validator(mode="after")
    def check_dates_and_prices(self) -> "HotelSearchParams":
        if self.check_in < date.today():
            raise ValueError("Check-in can't be in the past.")
        if self.check_out <= self.check_in:
            raise ValueError("Check-out must be after check-in.")
        if (self.check_out - self.check_in).days > MAX_STAY_NIGHTS:
            raise ValueError(f"Stays are limited to {MAX_STAY_NIGHTS} nights.")
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("Minimum price can't be more than maximum price.")
        return self
