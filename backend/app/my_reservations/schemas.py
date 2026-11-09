from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

CardStatus = Literal["awaiting_payment", "confirmed", "completed", "cancelled"]


class CardHotel(BaseModel):
    id: str
    name: str
    city: str
    image: dict | None  # same shape as GET /hotels/{id}/images entries, or null


class CardRoom(BaseModel):
    id: str
    room_type: str
    room_number: str


class ReservationCard(BaseModel):
    id: str
    status: CardStatus
    hotel: CardHotel
    room: CardRoom
    check_in: date
    check_out: date
    nights: int
    num_guests: int
    total_price: float
    amount_paid: float
    hold_expires_at: datetime | None  # only set while awaiting payment


class GroupCounts(BaseModel):
    upcoming: int
    past: int
    cancelled: int


class MyReservations(BaseModel):
    upcoming: list[ReservationCard]
    past: list[ReservationCard]
    cancelled: list[ReservationCard]
    counts: GroupCounts
