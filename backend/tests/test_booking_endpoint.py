"""2.1.4 Booking endpoint: overlapping dates and unavailable rooms (US2.1).

test_booking_availability.py checks place_hold directly. These go through
POST /reservations as two different logged-in guests, so they also cover the
status codes, the response bodies and the API's cancel route.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Hotel, Reservation, Room, User
from app.security import issue_tokens
from app.services.booking_availability import HOLD_MINUTES

TODAY = date.today()


def day(n: int) -> date:
    return TODAY + timedelta(days=n)


# Alice's stay in every overlap test: 3 nights, days 10-13.
IN, OUT = day(10), day(13)


@pytest.fixture
def hotel(db_session):
    hotel = Hotel(name="Overlap Hotel", address="1 Main", city="San Jose", country="US")
    db_session.add(hotel)
    db_session.commit()
    return hotel


def add_room(db, hotel, number, **kw):
    room = Room(hotel_id=hotel.id, room_number=number, price_per_night=100, max_guests=2, **kw)
    db.add(room)
    db.commit()
    return room


@pytest.fixture
def room(db_session, hotel):
    return add_room(db_session, hotel, "101")


def add_user(db, name):
    user = User(email=f"{name}@example.com", hashed_password="x", first_name=name, last_name="T")
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def alice(db_session):
    return add_user(db_session, "alice")


@pytest.fixture
def bob(db_session):
    return add_user(db_session, "bob")


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


def book(client, user, room, check_in=IN, check_out=OUT, **kw):
    body = {"room_id": room.id, "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(), **kw}
    return client.post("/reservations", json=body, headers=auth(user))


def reservations_for(db, room):
    db.expire_all()
    return db.query(Reservation).filter_by(room_id=room.id).all()


# Overlapping dates

@pytest.mark.parametrize("check_in,check_out", [
    (IN, OUT),            # same dates
    (day(11), day(15)),   # starts inside
    (day(8), day(11)),    # ends inside
    (day(9), day(14)),    # wraps around
    (day(11), day(12)),   # inside
])
def test_overlapping_stay_is_refused(client, room, alice, bob, check_in, check_out):
    assert book(client, alice, room).status_code == 201
    response = book(client, bob, room, check_in, check_out)
    assert response.status_code == 409
    assert response.json() == {"detail": "Room is unavailable for those dates."}


@pytest.mark.parametrize("check_in,check_out", [
    (OUT, day(15)),  # checks in the day Alice checks out
    (day(8), IN),    # checks out the day Alice checks in
])
def test_back_to_back_stays_are_allowed(client, room, alice, bob, check_in, check_out):
    assert book(client, alice, room).status_code == 201
    assert book(client, bob, room, check_in, check_out).status_code == 201


def test_refused_booking_creates_nothing(client, db_session, room, alice, bob):
    assert book(client, alice, room).status_code == 201
    assert book(client, bob, room).status_code == 409
    assert [r.user_id for r in reservations_for(db_session, room)] == [alice.id]


def test_other_rooms_are_unaffected(client, db_session, hotel, room, alice, bob):
    other = add_room(db_session, hotel, "102")
    assert book(client, alice, room).status_code == 201
    assert book(client, bob, other).status_code == 201


def test_cancelling_frees_the_room(client, room, alice, bob):
    hold = book(client, alice, room).json()
    cancel = client.post(f"/reservations/{hold['id']}/cancel", headers=auth(alice))
    assert cancel.status_code == 200, cancel.text
    assert book(client, bob, room).status_code == 201


def test_expired_hold_stops_blocking(client, db_session, room, alice, bob):
    hold_id = book(client, alice, room).json()["id"]
    hold = db_session.get(Reservation, hold_id)

    # Still inside the hold window: Bob is refused.
    hold.created_at = datetime.now(timezone.utc) - timedelta(minutes=HOLD_MINUTES - 5)
    db_session.commit()
    assert book(client, bob, room).status_code == 409

    # Past it: Alice's hold is released and Bob gets the room.
    hold.created_at = datetime.now(timezone.utc) - timedelta(minutes=HOLD_MINUTES + 1)
    db_session.commit()
    assert book(client, bob, room).status_code == 201


def test_confirmed_booking_blocks(client, db_session, room, alice, bob):
    db_session.add(Reservation(user_id=alice.id, room_id=room.id, check_in_date=IN,
                               check_out_date=OUT, total_price=300, status="confirmed"))
    db_session.commit()
    assert book(client, bob, room).status_code == 409


# Unavailable room

def test_room_marked_unavailable_is_refused(client, db_session, hotel, bob):
    closed = add_room(db_session, hotel, "201", is_available=False)
    response = book(client, bob, closed)
    assert response.status_code == 409
    assert reservations_for(db_session, closed) == []


def test_unknown_room_is_404(client, bob):
    response = client.post("/reservations", headers=auth(bob), json={
        "room_id": "no-such-room", "check_in": IN.isoformat(), "check_out": OUT.isoformat(),
    })
    assert response.status_code == 404
    assert response.json() == {"detail": "Room not found."}


def test_too_many_guests_is_refused(client, room, bob):
    response = book(client, bob, room, num_guests=3)  # room sleeps 2
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "num_guests"


@pytest.mark.xfail(reason="place_hold doesn't check Hotel.is_active, so the booking succeeds (201)")
def test_room_in_inactive_hotel_is_refused(client, db_session, hotel, room, bob):
    # Search hides inactive hotels and the hotel page 404s them, so booking
    # their rooms should fail too.
    hotel.is_active = False
    db_session.commit()
    assert book(client, bob, room).status_code == 404
    assert reservations_for(db_session, room) == []


# Request validation

@pytest.mark.parametrize("check_in,check_out,field", [
    (IN, IN, "check_out"),                       # zero nights
    (OUT, IN, "check_out"),                      # check-out before check-in
    (TODAY - timedelta(days=1), day(2), "check_in"),  # in the past
])
def test_invalid_dates_name_the_field(client, room, bob, check_in, check_out, field):
    response = book(client, bob, room, check_in, check_out)
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == field


def test_missing_room_id_is_rejected(client, bob):
    response = client.post("/reservations", headers=auth(bob), json={
        "check_in": IN.isoformat(), "check_out": OUT.isoformat(),
    })
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "room_id"]
