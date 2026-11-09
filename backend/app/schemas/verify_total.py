from decimal import Decimal

from pydantic import BaseModel, Field


class VerifyTotalRequest(BaseModel):
    """The total the checkout screen is showing the guest."""

    displayed_total: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class VerifyTotalResponse(BaseModel):
    matches: bool
    total: float