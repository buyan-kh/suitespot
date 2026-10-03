import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Hotel, Payment, Reservation, Room, User

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Seeded users cannot log in until the auth work picks a hashing scheme.
PLACEHOLDER_PASSWORD_HASH = "!seed-placeholder-not-a-real-hash"


def _read_fixture(name: str, fixtures_dir: Path) -> list[dict]:
    with open(fixtures_dir / name, encoding="utf-8") as f:
        return json.load(f)


def reset_tables(db: Session) -> None:
    """Delete all rows, children first so foreign keys stay valid."""
    for model in (Payment, Reservation, Room, Hotel, User):
        db.query(model).delete()
    db.commit()


def load_fixtures(db: Session, fixtures_dir: Path = FIXTURES_DIR) -> dict[str, int]:
    """Insert fixture rows that are not already present. Safe to run repeatedly.

    Returns the number of rows created per table.
    """
    created = {"users": 0, "hotels": 0, "rooms": 0}

    for data in _read_fixture("users.json", fixtures_dir):
        if db.query(User).filter_by(email=data["email"]).first():
            continue
        db.add(User(hashed_password=PLACEHOLDER_PASSWORD_HASH, **data))
        created["users"] += 1

    for data in _read_fixture("hotels.json", fixtures_dir):
        rooms = data.pop("rooms", [])
        hotel = db.query(Hotel).filter_by(name=data["name"], city=data["city"]).first()
        if hotel is None:
            hotel = Hotel(**data)
            db.add(hotel)
            db.flush()
            created["hotels"] += 1

        for room_data in rooms:
            exists = (
                db.query(Room)
                .filter_by(hotel_id=hotel.id, room_number=room_data["room_number"])
                .first()
            )
            if exists:
                continue
            db.add(Room(hotel_id=hotel.id, **room_data))
            created["rooms"] += 1

    db.commit()
    return created
