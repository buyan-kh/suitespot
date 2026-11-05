"""1.6.1 Amenity data model + seed values (US1.6)."""

import json
import logging
import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError

from app.amenities.models import Amenity, HotelAmenity
from app.models import Hotel
from app.seed.loader import FIXTURES_DIR, load_amenities, load_fixtures, reset_tables

BACKEND = Path(__file__).resolve().parents[1]
FILTER_PANEL = BACKEND.parent / "frontend" / "components" / "search" / "FilterPanel.tsx"

AMENITIES = json.loads((FIXTURES_DIR / "amenities.json").read_text())
HOTELS = json.loads((FIXTURES_DIR / "hotels.json").read_text())


def seed(db):
    load_fixtures(db)
    return load_amenities(db)


def make_hotel(db, name="H"):
    hotel = Hotel(name=name, address="1 Main", city="San Jose", country="US")
    db.add(hotel)
    db.commit()
    return hotel


# Model

def test_hotel_can_be_linked_to_an_amenity(db_session):
    hotel = make_hotel(db_session)
    pool = Amenity(slug="pool", name="Pool")
    db_session.add(pool)
    db_session.flush()
    db_session.add(HotelAmenity(hotel_id=hotel.id, amenity_id=pool.id))
    db_session.commit()
    assert db_session.query(HotelAmenity).count() == 1


def test_same_amenity_cannot_be_linked_twice(db_session):
    hotel = make_hotel(db_session)
    pool = Amenity(slug="pool", name="Pool")
    db_session.add(pool)
    db_session.commit()
    db_session.add(HotelAmenity(hotel_id=hotel.id, amenity_id=pool.id))
    db_session.commit()
    db_session.add(HotelAmenity(hotel_id=hotel.id, amenity_id=pool.id))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("second", [
    {"slug": "pool", "name": "Swimming pool"},  # same slug
    {"slug": "pool-2", "name": "Pool"},        # same name
])
def test_slug_and_name_are_unique(db_session, second):
    db_session.add(Amenity(slug="pool", name="Pool"))
    db_session.commit()
    db_session.add(Amenity(**second))
    with pytest.raises(IntegrityError):
        db_session.commit()


# Seed

def test_seed_creates_amenities_and_links(db_session):
    links = sum(len(h.get("amenities", [])) for h in HOTELS)
    assert seed(db_session) == {"amenities": len(AMENITIES), "hotel_amenities": links}
    assert db_session.query(Amenity).count() == len(AMENITIES)
    assert db_session.query(HotelAmenity).count() == links


def test_seed_links_the_right_amenities(db_session):
    seed(db_session)
    hotel = db_session.query(Hotel).filter_by(name="Ocean Drive Resort").one()
    names = {
        a.name for a in db_session.query(Amenity)
        .join(HotelAmenity, HotelAmenity.amenity_id == Amenity.id)
        .filter(HotelAmenity.hotel_id == hotel.id)
    }
    assert names == {"Pool", "Beach nearby", "Spa & wellness", "Restaurant"}


def test_seed_is_idempotent(db_session):
    seed(db_session)
    assert seed(db_session) == {"amenities": 0, "hotel_amenities": 0}


def test_unknown_amenity_is_skipped_with_a_warning(db_session, tmp_path, caplog):
    (tmp_path / "users.json").write_text("[]")
    (tmp_path / "amenities.json").write_text(json.dumps([{"slug": "pool", "name": "Pool"}]))
    (tmp_path / "hotels.json").write_text(json.dumps([{
        "name": "H", "address": "1 Main", "city": "San Jose", "country": "US",
        "amenities": ["Pool", "Helipad"],
    }]))
    load_fixtures(db_session, tmp_path)
    with caplog.at_level(logging.WARNING, logger="app.seed.loader"):
        created = load_amenities(db_session, tmp_path)
    assert created == {"amenities": 1, "hotel_amenities": 1}
    assert "Helipad" in caplog.text


def test_reset_clears_amenity_tables(db_session):
    seed(db_session)
    reset_tables(db_session)
    assert db_session.query(Amenity).count() == 0
    assert db_session.query(HotelAmenity).count() == 0


# Fixtures stay consistent (also guards Elsa's 30-hotel catalog, 8.3.1)

def test_every_hotel_amenity_exists_in_amenities_json():
    known = {a["name"] for a in AMENITIES}
    for hotel in HOTELS:
        unknown = set(hotel.get("amenities", [])) - known
        assert not unknown, f"{hotel['name']} lists unknown amenities {unknown}"


def test_every_seeded_hotel_lists_amenities():
    for hotel in HOTELS:
        assert hotel.get("amenities"), f"{hotel['name']} has no amenities"


def test_amenities_match_the_frontend_filter_panel():
    # Renaming an amenity on either side would break the filter (1.4.1).
    if not FILTER_PANEL.exists():
        pytest.skip("frontend not checked out")
    block = re.search(r"AMENITY_OPTIONS\s*=\s*\[(.*?)\]", FILTER_PANEL.read_text(), re.S)
    assert block, "AMENITY_OPTIONS not found in FilterPanel.tsx"
    frontend = re.findall(r"'([^']+)'|\"([^\"]+)\"", block.group(1))
    assert {a or b for a, b in frontend} == {a["name"] for a in AMENITIES}


# API

def test_hotel_amenities_sorted_by_name(client, db_session):
    seed(db_session)
    hotel = db_session.query(Hotel).filter_by(name="Ocean Drive Resort").one()
    response = client.get(f"/hotels/{hotel.id}/amenities")
    assert response.status_code == 200
    assert response.json() == {"amenities": [
        {"slug": "beach-nearby", "name": "Beach nearby"},
        {"slug": "pool", "name": "Pool"},
        {"slug": "restaurant", "name": "Restaurant"},
        {"slug": "spa-wellness", "name": "Spa & wellness"},
    ]}


def test_hotel_without_amenities_gets_empty_list(client, db_session):
    hotel = make_hotel(db_session)
    assert client.get(f"/hotels/{hotel.id}/amenities").json() == {"amenities": []}


def test_unknown_hotel_is_404(client):
    assert client.get("/hotels/does-not-exist/amenities").status_code == 404


def test_list_all_amenities(client, db_session):
    seed(db_session)
    body = client.get("/amenities").json()
    assert [a["name"] for a in body["amenities"]] == sorted(a["name"] for a in AMENITIES)


# Migrations

def test_migrations_have_a_single_head():
    # Two branches adding migrations off the same parent leave two heads;
    # whichever merges second must point down_revision at the other.
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert len(script.get_heads()) == 1, script.get_heads()
