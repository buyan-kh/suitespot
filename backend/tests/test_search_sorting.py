"""1.5.1 Sort ordering on the search endpoint (US1.5)."""

from datetime import date, timedelta

import pytest

from app.models import Hotel, Room

TODAY = date.today()
PARAMS = {
    "destination": "San Jose",
    "checkIn": (TODAY + timedelta(days=10)).isoformat(),
    "checkOut": (TODAY + timedelta(days=13)).isoformat(),
    "guests": 1,
}

# name, stars, (room prices). from_price is the cheapest room.
HOTELS = [
    ("Bravo Inn", 3, [120, 300]),   # from 120
    ("Alpha Lodge", 5, [200]),      # from 200
    ("Charlie Suites", 4, [80]),    # from 80
    ("Delta Hotel", 4, [150]),      # from 150
]


@pytest.fixture
def hotels(db_session):
    for name, stars, prices in HOTELS:
        hotel = Hotel(name=name, address="1 St", city="San Jose", country="US", star_rating=stars)
        db_session.add(hotel)
        db_session.flush()
        for i, price in enumerate(prices):
            db_session.add(Room(hotel_id=hotel.id, room_number=str(i), price_per_night=price, max_guests=2))
    db_session.commit()


def names(client, **extra):
    response = client.get("/search", params={**PARAMS, **extra})
    assert response.status_code == 200, response.text
    return [h["name"] for h in response.json()["results"]]


def test_default_order_is_recommended(client, hotels):
    assert names(client) == ["Alpha Lodge", "Bravo Inn", "Charlie Suites", "Delta Hotel"]


def test_recommended_can_be_requested_explicitly(client, hotels):
    # The frontend SortControl uses "recommended" as its default value.
    assert names(client, sort="recommended") == names(client)


def test_price_low_to_high(client, hotels):
    assert names(client, sort="price_asc") == ["Charlie Suites", "Bravo Inn", "Delta Hotel", "Alpha Lodge"]


def test_price_high_to_low(client, hotels):
    assert names(client, sort="price_desc") == ["Alpha Lodge", "Delta Hotel", "Bravo Inn", "Charlie Suites"]


def test_rating_high_to_low_breaks_ties_by_price(client, hotels):
    # 5 stars, then the two 4-star hotels (Charlie is cheaper), then 3 stars.
    assert names(client, sort="rating") == ["Alpha Lodge", "Charlie Suites", "Delta Hotel", "Bravo Inn"]


def test_response_reports_the_sort_used(client, hotels):
    assert client.get("/search", params={**PARAMS, "sort": "rating"}).json()["sort"] == "rating"
    assert client.get("/search", params=PARAMS).json()["sort"] == "recommended"


@pytest.mark.parametrize("bad", ["distance", "name", "cheapest", "", "PRICE_ASC"])
def test_unknown_sort_is_rejected_and_names_the_field(client, hotels, bad):
    response = client.get("/search", params={**PARAMS, "sort": bad})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "sort"]


def test_sorting_is_applied_before_paging(client, hotels):
    page1 = names(client, sort="price_asc", limit=2, offset=0)
    page2 = names(client, sort="price_asc", limit=2, offset=2)
    assert page1 + page2 == ["Charlie Suites", "Bravo Inn", "Delta Hotel", "Alpha Lodge"]


def test_sort_works_with_booked_rooms_excluded(client, db_session, hotels):
    from app.models import Reservation, User

    user = User(email="s@x.com", hashed_password="x", first_name="S", last_name="T")
    db_session.add(user)
    db_session.flush()
    cheapest = db_session.query(Room).filter(Room.price_per_night == 80).one()
    db_session.add(Reservation(
        user_id=user.id, room_id=cheapest.id, total_price=240, status="confirmed",
        check_in_date=TODAY + timedelta(days=10), check_out_date=TODAY + timedelta(days=13),
    ))
    db_session.commit()
    assert "Charlie Suites" not in names(client, sort="price_asc")


def test_service_rejects_unknown_sort(db_session):
    from app.services.availability import find_available_hotels

    with pytest.raises(ValueError):
        find_available_hotels(
            db_session, destination="x", check_in=TODAY, check_out=TODAY + timedelta(days=1),
            guests=1, sort="distance",
        )