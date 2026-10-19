import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.images.models import HotelImage
from app.images.resize import ORIGINALS_DIR, SIZED_DIR, build_sizes, slugify
from app.models import Hotel, Payment, Reservation, Room, User

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Seeded users cannot log in until the auth work picks a hashing scheme.
PLACEHOLDER_PASSWORD_HASH = "!seed-placeholder-not-a-real-hash"


def _read_fixture(name: str, fixtures_dir: Path) -> list[dict]:
    with open(fixtures_dir / name, encoding="utf-8") as f:
        return json.load(f)


def reset_tables(db: Session) -> None:
    """Delete all rows, children first so foreign keys stay valid."""
    for model in (HotelImage, Payment, Reservation, Room, Hotel, User):
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
        else:
            # Hotels seeded before coordinates existed get them filled in.
            for field in ("latitude", "longitude"):
                if getattr(hotel, field) is None and data.get(field) is not None:
                    setattr(hotel, field, data[field])

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


def load_images(
    db: Session,
    fixtures_dir: Path = FIXTURES_DIR,
    originals: Path = ORIGINALS_DIR,
    sized: Path = SIZED_DIR,
) -> int:
    """Build resized copies and insert hotel_images rows (1.3.1). Safe to run repeatedly.

    images.json order is display order per hotel. Entries whose hotel or
    original file is missing are skipped with a warning, so the seed still
    runs before every photo has arrived. Returns the number of rows created.
    """
    created = 0
    positions: dict[str, int] = {}

    for data in _read_fixture("images.json", fixtures_dir):
        hotel = db.query(Hotel).filter_by(name=data["hotel"], city=data["city"]).first()
        if hotel is None:
            logger.warning("images.json: no hotel %r in %r", data["hotel"], data["city"])
            continue
        file = f"{slugify(hotel.name)}/{data['file']}"
        if not (originals / file).exists():
            logger.warning("images.json: missing original media/originals/%s", file)
            continue

        position = positions.get(hotel.id, 0)
        positions[hotel.id] = position + 1
        width, height = build_sizes(file, originals, sized)
        if db.query(HotelImage).filter_by(hotel_id=hotel.id, file=file).first():
            continue
        db.add(
            HotelImage(
                hotel_id=hotel.id,
                room_type=data.get("room_type"),
                position=position,
                file=file,
                alt=data.get("alt", ""),
                width=width,
                height=height,
            )
        )
        created += 1

    db.commit()
    return created
