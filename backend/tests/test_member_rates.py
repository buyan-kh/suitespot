"""1.8.1 Member vs public rate on room records (US1.8)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.member_rates.service import member_rates, savings_percent
from app.models import Hotel, Room, User
from app.seed.loader import load_fixtures
from app.services.booking_availability import place_hold

TODAY = datetime.now(timezone.utc).date()


def make_hotel(db, name="Hotel Aurora", active=True):
    hotel = Hotel(name=name, address="1 Main", city="San Jose", country="US", is_active=active)
    db.add(hotel)
    db.commit()
    return hotel


def make_room(db, hotel, number, price, member=None, available=True):
    room = Room(hotel_id=hotel.id, room_number=number, price_per_night=price,
                member_price_per_night=member, max_guests=2, is_available=available)
    db.add(room)
    db.commit()
    return room


@pytest.fixture
def hotel(db_session):
    return make_hotel(db_session)


def url(hotel_id):
    return f"/hotels/{hotel_id}/member-rates"


# --- the column and its constraint -------------------------------------------

def test_a_room_without_a_member_rate_is_fine(db_session, hotel):
    assert make_room(db_session, hotel, "1", 100).member_price_per_night is None


def test_a_member_rate_below_the_public_rate_is_fine(db_session, hotel):
    room = make_room(db_session, hotel, "1", 100, member=90)
    db_session.refresh(room)
    assert Decimal(str(room.member_price_per_night)) == Decimal("90.00")


@pytest.mark.parametrize("member", [100, 120, 0, -5], ids=["equal", "above", "zero", "negative"])
def test_a_member_rate_must_be_a_real_discount(db_session, hotel, member):
    with pytest.raises(IntegrityError):
        make_room(db_session, hotel, "1", 100, member=member)
    db_session.rollback()


# --- the numbers ----------------------------------------------------------------

@pytest.mark.parametrize("public,member,percent", [
    ("100.00", "90.00", 10),
    ("129.00", "116.62", 9),     # 9.6% rounds DOWN, never overstates
    ("129.00", "115.00", 10),    # 10.85%
    ("1199.00", "1049.00", 12),  # 12.5%
    ("100.00", "99.99", 0),      # a tiny saving shows as 0%, not 1%
])
def test_savings_percent_rounds_down(public, member, percent):
    assert savings_percent(Decimal(public), Decimal(member)) == percent


def test_lists_only_rooms_with_a_member_rate_in_hotel_page_order(db_session, hotel):
    suite = make_room(db_session, hotel, "301", 300, member=255)
    make_room(db_session, hotel, "102", 150)  # no member rate: not listed
    single = make_room(db_session, hotel, "101", 100, member=90)
    result = member_rates(db_session, hotel.id)
    assert [r["room_id"] for r in result["rooms"]] == [single.id, suite.id]
    assert result["rooms"][0] == {
        "room_id": single.id, "room_number": "101", "room_type": "single",
        "price_per_night": 100.0, "member_price_per_night": 90.0,
        "savings_per_night": 10.0, "savings_percent": 10,
    }
    assert result["rooms"][1]["savings_per_night"] == 45.0
    assert result["best_savings_percent"] == 15


def test_a_hotel_with_no_member_rates(db_session, hotel):
    make_room(db_session, hotel, "1", 100)
    assert member_rates(db_session, hotel.id) == {
        "hotel_id": hotel.id, "best_savings_percent": None, "rooms": [],
    }


def test_another_hotels_rooms_are_not_listed(db_session, hotel):
    make_room(db_session, make_hotel(db_session, "Elsewhere"), "1", 100, member=80)
    assert member_rates(db_session, hotel.id)["rooms"] == []


def test_an_unavailable_room_still_shows_its_rate(db_session, hotel):
    room = make_room(db_session, hotel, "1", 100, member=90, available=False)
    assert [r["room_id"] for r in member_rates(db_session, hotel.id)["rooms"]] == [room.id]


# --- the endpoint -----------------------------------------------------------------

def test_works_without_logging_in(client, db_session, hotel):
    make_room(db_session, hotel, "1", 100, member=90)
    response = client.get(url(hotel.id))
    assert response.status_code == 200
    assert response.json()["best_savings_percent"] == 10


def test_returns_only_the_documented_fields(client, db_session, hotel):
    make_room(db_session, hotel, "1", 100, member=90)
    body = client.get(url(hotel.id)).json()
    assert set(body) == {"hotel_id", "best_savings_percent", "rooms"}
    assert set(body["rooms"][0]) == {
        "room_id", "room_number", "room_type", "price_per_night",
        "member_price_per_night", "savings_per_night", "savings_percent",
    }


def test_unknown_hotel_is_404(client):
    response = client.get(url("nope"))
    assert response.status_code == 404
    assert response.json()["detail"] == "Hotel not found."


def test_deactivated_hotel_is_404(client, db_session):
    closed = make_hotel(db_session, "Closed", active=False)
    make_room(db_session, closed, "1", 100, member=90)
    assert client.get(url(closed.id)).status_code == 404


def test_post_is_not_allowed(client, hotel):
    assert client.post(url(hotel.id)).status_code == 405


# --- out of scope: booking still charges the public rate ------------------------------

def test_booking_still_charges_the_public_rate(db_session, hotel):
    """Charging members the member rate isn't built (no task covers it yet).
    Whoever adds it should change this test on purpose."""
    user = User(email="me@x.com", hashed_password="x", first_name="T", last_name="U")
    db_session.add(user)
    db_session.commit()
    room = make_room(db_session, hotel, "1", 100, member=90)
    hold = place_hold(db_session, user_id=user.id, room_id=room.id,
                      check_in=TODAY + timedelta(days=10), check_out=TODAY + timedelta(days=13))
    assert Decimal(str(hold.total_price)) == Decimal("300.00")


# --- seed data -----------------------------------------------------------------------

def test_seed_has_rooms_with_and_without_member_rates(db_session):
    load_fixtures(db_session)
    rooms = db_session.query(Room).all()
    with_rate = [r for r in rooms if r.member_price_per_night is not None]
    assert with_rate and len(with_rate) < len(rooms)
    assert all(r.member_price_per_night < r.price_per_night for r in with_rate)
