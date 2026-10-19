from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

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
    # Optional point for the distance sort; without it distance is measured
    # from the destination's city centre. Send both or neither.
    lat: float | None = Field(default=None, ge=-90, le=90)
    # validate_default so "lat without lng" is still caught.
    lng: float | None = Field(default=None, ge=-180, le=180, validate_default=True)

    # Field validators (not a model validator) so each error's loc names the
    # field, e.g. ["query", "check_out"], and the form can highlight it.
    @field_validator("check_in")
    @classmethod
    def check_in_not_past(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("Check-in can't be in the past.")
        return value

    @field_validator("check_out")
    @classmethod
    def check_out_after_check_in(cls, value: date, info: ValidationInfo) -> date:
        check_in = info.data.get("check_in")
        if check_in is None:
            return value
        if value <= check_in:
            raise ValueError("Check-out must be after check-in.")
        if (value - check_in).days > MAX_STAY_NIGHTS:
            raise ValueError(f"Stays are limited to {MAX_STAY_NIGHTS} nights.")
        return value

    @field_validator("max_price")
    @classmethod
    def max_price_not_below_min(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        min_price = info.data.get("min_price")
        if value is not None and min_price is not None and min_price > value:
            raise ValueError("Minimum price can't be more than maximum price.")
        return value

    @field_validator("lng", mode="after")
    @classmethod
    def lat_and_lng_together(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        if "lat" not in info.data:
            return value  # lat already failed its own range check
        if (info.data["lat"] is None) != (value is None):
            raise ValueError("Send lat and lng together.")
        return value
