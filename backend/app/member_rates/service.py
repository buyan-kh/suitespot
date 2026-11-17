"""Member vs public rate for each room (US1.8, task 1.8.1).

Read-only. Lists the rooms at a hotel that have a lower member rate, so the
hotel page (1.8.2) can tell a visitor without an account what signing up saves.

Only shows the rate. Booking, modify and the re-quote still charge
price_per_night for everyone (stay_total in app.services.pricing); charging
members the member rate is not part of this task.
"""

from decimal import ROUND_FLOOR, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Room
from app.services.pricing import money


def savings_percent(public: Decimal, member: Decimal) -> int:
    """Whole percent saved, rounded DOWN so the callout never overstates it."""
    return int(((public - member) * 100 / public).to_integral_value(rounding=ROUND_FLOOR))


def member_rates(db: Session, hotel_id: str) -> dict:
    rooms = db.scalars(
        select(Room)
        .where(Room.hotel_id == hotel_id, Room.member_price_per_night.is_not(None))
        .order_by(Room.price_per_night, Room.room_number)  # same order as the hotel page
    ).all()

    listed = []
    for room in rooms:
        public, member = money(room.price_per_night), money(room.member_price_per_night)
        listed.append({
            "room_id": room.id,
            "room_number": room.room_number,
            "room_type": room.room_type,
            "price_per_night": float(public),
            "member_price_per_night": float(member),
            "savings_per_night": float(public - member),
            "savings_percent": savings_percent(public, member),
        })

    return {
        "hotel_id": hotel_id,
        "best_savings_percent": max((r["savings_percent"] for r in listed), default=None),
        "rooms": listed,
    }
