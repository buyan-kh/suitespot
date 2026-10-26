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
# Delta and Charlie are both 4 stars, and Delta is cheaper but later in the
# alphabet, so price order and name order disagree for them.
HOTELS = [
    ("Bravo Inn", 3, [120, 300]),   # from 120
    ("Alpha Lodge", 5, [200]),      # from 200
    ("Charlie Suites", 4, [80]),    # from 80
    ("Delta Hotel", 4, [70]),       # from 70
]


def add_hotel(db, name, stars, rooms, city="San Jose", hotel_id=None):
    """rooms is a list of (price_per_night, max_guests)."""
    extra = {"id": hotel_id} if hotel_id else {}
    hotel = Hotel(name=name, address="1 St", city=city, country="US", star_rating=stars, **extra)
    db.add(hotel)
    db.flush()
    for i, (price, max_guests) in enumerate(rooms):
        db.add(Room(hotel_id=hotel.id, room_number=str(i), price_per_night=price, max_guests=max_guests))
    return hotel


@pytest.fixture
def hotels(db_session):
    for name, stars, prices in HOTELS:
        add_hotel(db_session, name, stars, [(price, 2) for price in prices])
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
    assert names(client, sort="price_asc") == ["Delta Hotel", "Charlie Suites", "Bravo Inn", "Alpha Lodge"]


def test_price_high_to_low(client, hotels):
    assert names(client, sort="price_desc") == ["Alpha Lodge", "Bravo Inn", "Charlie Suites", "Delta Hotel"]


def test_rating_high_to_low_breaks_ties_by_price(client, hotels):
    # 5 stars first, 3 stars last. The two 4-star hotels tie on rating, so the
    # cheaper one (Delta, 70) comes first even though Charlie is first by name.
    assert names(client, sort="rating") == ["Alpha Lodge", "Delta Hotel", "Charlie Suites", "Bravo Inn"]


def test_response_reports_the_sort_used(client, hotels):
    assert client.get("/search", params={**PARAMS, "sort": "rating"}).json()["sort"] == "rating"
    assert client.get("/search", params=PARAMS).json()["sort"] == "recommended"


@pytest.mark.parametrize("bad", ["name", "cheapest", "", "PRICE_ASC"])
def test_unknown_sort_is_rejected_and_names_the_field(client, hotels, bad):
    response = client.get("/search", params={**PARAMS, "sort": bad})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "sort"]


def test_sorting_is_applied_before_paging(client, hotels):
    page1 = names(client, sort="price_asc", limit=2, offset=0)
    page2 = names(client, sort="price_asc", limit=2, offset=2)
    assert page1 + page2 == ["Delta Hotel", "Charlie Suites", "Bravo Inn", "Alpha Lodge"]


def test_price_sort_only_counts_rooms_that_fit_the_party(client, db_session):
    # Echo's cheapest room sleeps 1, so for 3 guests its price is the 300 room.
    add_hotel(db_session, "Echo Lodge", 3, [(50, 1), (300, 4)], city="Fit City")
    add_hotel(db_session, "Foxtrot Inn", 3, [(200, 4)], city="Fit City")
    db_session.commit()
    params = {**PARAMS, "destination": "Fit City", "sort": "price_asc"}

    three = client.get("/search", params={**params, "guests": 3}).json()["results"]
    assert [h["name"] for h in three] == ["Foxtrot Inn", "Echo Lodge"]
    assert {h["name"]: h["from_price"] for h in three} == {"Foxtrot Inn": 200.0, "Echo Lodge": 300.0}

    # For one guest the 50 room fits, so Echo is the cheapest.
    one = client.get("/search", params={**params, "guests": 1}).json()["results"]
    assert [h["name"] for h in one] == ["Echo Lodge", "Foxtrot Inn"]
    assert one[0]["from_price"] == 50.0


@pytest.mark.parametrize("sort", ["price_asc", "price_desc"])
def test_equal_prices_are_ordered_by_name(client, db_session, sort):
    # The ids are set opposite to the name order, so only the name tie-break
    # (not the id fallback) can produce this result.
    add_hotel(db_session, "Yankee Inn", 3, [(90, 2)], city="Tie City", hotel_id="aaa-yankee")
    add_hotel(db_session, "Xray Inn", 3, [(90, 2)], city="Tie City", hotel_id="zzz-xray")
    db_session.commit()
    assert names(client, destination="Tie City", sort=sort) == ["Xray Inn", "Yankee Inn"]


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
            guests=1, sort="name",
        )
