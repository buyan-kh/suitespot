import json

from app.models import Hotel, Room, User
from app.seed.loader import FIXTURES_DIR, load_fixtures, reset_tables


def _fixture_counts():
    users = json.loads((FIXTURES_DIR / "users.json").read_text())
    hotels = json.loads((FIXTURES_DIR / "hotels.json").read_text())
    rooms = sum(len(h.get("rooms", [])) for h in hotels)
    return len(users), len(hotels), rooms


def test_load_fixtures_creates_rows(db_session):
    n_users, n_hotels, n_rooms = _fixture_counts()

    created = load_fixtures(db_session)

    assert created == {"users": n_users, "hotels": n_hotels, "rooms": n_rooms}
    assert db_session.query(User).count() == n_users
    assert db_session.query(Hotel).count() == n_hotels
    assert db_session.query(Room).count() == n_rooms


def test_load_fixtures_is_idempotent(db_session):
    load_fixtures(db_session)
    created = load_fixtures(db_session)

    assert created == {"users": 0, "hotels": 0, "rooms": 0}
    n_users, n_hotels, n_rooms = _fixture_counts()
    assert db_session.query(User).count() == n_users
    assert db_session.query(Hotel).count() == n_hotels
    assert db_session.query(Room).count() == n_rooms


def test_rooms_linked_to_hotels(db_session):
    load_fixtures(db_session)

    hotel = db_session.query(Hotel).filter_by(name="Ocean Drive Resort").one()
    assert {r.room_number for r in hotel.rooms} == {"301", "302", "PH1"}


def test_reset_tables_clears_data(db_session):
    load_fixtures(db_session)
    reset_tables(db_session)

    assert db_session.query(User).count() == 0
    assert db_session.query(Hotel).count() == 0
    assert db_session.query(Room).count() == 0
