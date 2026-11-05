"""US1.5 distance sort: measured from the city centre, or from lat/lng."""

import json
from datetime import date, timedelta

import pytest

from app.models import Hotel, Room
from app.seed.loader import FIXTURES_DIR, load_fixtures
from app.services.distance import CITY_CENTRES, haversine_km, resolve_origin, sort_by_distance

TODAY = date.today()
PARAMS = {
    "destination": "San Jose",
    "checkIn": (TODAY + timedelta(days=10)).isoformat(),
    "checkOut": (TODAY + timedelta(days=13)).isoformat(),
    "guests": 1,
    "sort": "distance",
}

# name, latitude, longitude. The San Jose city centre is (37.3382, -121.8863).
HOTELS = [
    ("Airport Lodge", 37.3639, -121.9289),    # ~4.7 km
    ("Downtown Suites", 37.3352, -121.8906),  # ~0.5 km
    ("Japantown Inn", 37.3483, -121.8949),    # ~1.4 km
    ("No Coordinates Hotel", None, None),     # always last
]


@pytest.fixture
def hotels(db_session):
    for name, lat, lng in HOTELS:
        hotel = Hotel(name=name, address="1 St", city="San Jose", country="US",
                      latitude=lat, longitude=lng)
        db_session.add(hotel)
        db_session.flush()
        db_session.add(Room(hotel_id=hotel.id, room_number="1", price_per_night=100, max_guests=2))
    db_session.commit()


def search(client, **extra):
    response = client.get("/search", params={**PARAMS, **extra})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def names(client, **extra):
    return [h["name"] for h in search(client, **extra)]


# The point we measure from

def test_origin_is_the_city_centre():
    assert resolve_origin("San Jose") == CITY_CENTRES["san jose"]
    assert resolve_origin("  new YORK ") == CITY_CENTRES["new york"]


def test_origin_finds_the_city_inside_a_longer_destination():
    assert resolve_origin("San Jose, CA") == CITY_CENTRES["san jose"]


def test_lat_lng_override_the_city_centre():
    assert resolve_origin("San Jose", 37.0, -121.0) == (37.0, -121.0)


def test_unknown_destination_has_no_origin():
    assert resolve_origin("CA") is None
    assert resolve_origin("Atlantis") is None


def test_every_seeded_city_has_a_centre():
    # New hotels in a new city (e.g. the 8.3.1 catalog) must add it to CITY_CENTRES.
    hotels = json.loads((FIXTURES_DIR / "hotels.json").read_text())
    missing = {h["city"] for h in hotels if h["city"].lower() not in CITY_CENTRES}
    assert not missing, f"add these cities to CITY_CENTRES: {missing}"


def test_every_seeded_hotel_has_coordinates():
    for hotel in json.loads((FIXTURES_DIR / "hotels.json").read_text()):
        assert hotel.get("latitude") is not None and hotel.get("longitude") is not None, hotel["name"]


# Distance in km

def test_haversine_san_jose_to_san_francisco():
    assert haversine_km(CITY_CENTRES["san jose"], 37.7749, -122.4194) == pytest.approx(67.6, abs=0.5)


def test_haversine_is_zero_at_the_origin_and_none_without_coordinates():
    assert haversine_km((10.0, 20.0), 10.0, 20.0) == 0.0
    assert haversine_km((10.0, 20.0), None, None) is None


def test_order_is_right_across_long_distances():
    # From San Francisco, New York (~4,130 km) is closer than Miami (~4,170 km).
    # A flat-map approximation gets this backwards.
    hotels = [
        {"id": "1", "name": "Miami", "latitude": 25.7802, "longitude": -80.1301},
        {"id": "2", "name": "New York", "latitude": 40.7587, "longitude": -73.9952},
    ]
    ordered = sort_by_distance(hotels, CITY_CENTRES["san francisco"])
    assert [h["name"] for h in ordered] == ["New York", "Miami"]


# The search endpoint

def test_closest_to_the_city_centre_first(client, hotels):
    assert names(client) == ["Downtown Suites", "Japantown Inn", "Airport Lodge", "No Coordinates Hotel"]


def test_results_include_distance_km(client, hotels):
    distances = {h["name"]: h["distance_km"] for h in search(client)}
    assert distances["Downtown Suites"] == pytest.approx(0.5, abs=0.2)
    assert distances["Airport Lodge"] == pytest.approx(4.7, abs=0.3)
    assert distances["No Coordinates Hotel"] is None


def test_lat_lng_change_the_order(client, hotels):
    # Standing at the airport, the airport hotel is closest.
    assert names(client, lat=37.3639, lng=-121.9289)[0] == "Airport Lodge"


def test_distance_km_is_null_for_other_sorts(client, hotels):
    assert all(h["distance_km"] is None for h in search(client, sort="price_asc"))


def test_distance_sorting_is_applied_before_paging(client, hotels):
    page1 = names(client, limit=2, offset=0)
    page2 = names(client, limit=2, offset=2)
    assert page1 + page2 == names(client)


def test_unknown_city_without_lat_lng_is_rejected(client, hotels):
    response = client.get("/search", params={**PARAMS, "destination": "Atlantis"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "sort"]


def test_unknown_city_works_with_lat_lng(client, hotels):
    response = client.get("/search", params={**PARAMS, "destination": "Hotel", "lat": 37.34, "lng": -121.89})
    assert response.status_code == 200


def test_service_requires_an_origin_for_distance(db_session):
    from app.services.availability import find_available_hotels

    with pytest.raises(ValueError):
        find_available_hotels(
            db_session, destination="San Jose", check_in=TODAY, check_out=TODAY + timedelta(days=1),
            guests=1, sort="distance",
        )


@pytest.mark.parametrize("extra,field", [
    ({"lat": 37.3}, "lng"),
    ({"lng": -121.9}, "lng"),
    ({"lat": 91, "lng": 0}, "lat"),
    ({"lat": 0, "lng": 181}, "lng"),
])
def test_bad_lat_lng_is_rejected_and_names_the_field(client, hotels, extra, field):
    response = client.get("/search", params={**PARAMS, **extra})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", field]


# Seed backfill

def test_seed_fills_in_coordinates_on_existing_hotels(db_session):
    load_fixtures(db_session)
    for hotel in db_session.query(Hotel):
        hotel.latitude = hotel.longitude = None
    db_session.commit()

    load_fixtures(db_session)
    assert all(h.latitude is not None and h.longitude is not None for h in db_session.query(Hotel))
