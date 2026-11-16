from datetime import datetime, timedelta, timezone

import pytest

from app.models import Hotel, Reservation, Room, User
from app.security import issue_tokens
from app.services.booking_availability import (
    OverlappingStay,
    RoomNotFound,
    RoomUnavailable,
    place_hold,
)
from app.services.stay_overlap import find_overlapping_stay

TODAY = datetime.now(timezone.utc).date()
D = lambda n: TODAY + timedelta(days=n)
IN, OUT = D(10), D(13)  # the guest's first stay: 3 nights


def make_user(db, email):
    u = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(u)
    db.commit()
    return u


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


def make_hotel(db, name, active=True):
    hotel = Hotel(name=name, address="1 Main", city="San Jose", country="US", is_active=active)
    db.add(hotel)
    db.flush()
    return hotel


def make_room(db, hotel, number="1", price=100):
    room = Room(hotel_id=hotel.id, room_number=number, price_per_night=price, max_guests=2)
    db.add(room)
    db.commit()
    return room


@pytest.fixture
def user(db_session):
    return make_user(db_session, "me@x.com")


@pytest.fixture
def other(db_session):
    return make_user(db_session, "other@x.com")


@pytest.fixture
def hotel_a(db_session):
    return make_hotel(db_session, "Hotel Aurora")


@pytest.fixture
def hotel_b(db_session):
    return make_hotel(db_session, "Hotel Borealis")


@pytest.fixture
def room_a(db_session, hotel_a):
    return make_room(db_session, hotel_a, "A1")


@pytest.fixture
def room_b(db_session, hotel_b):
    return make_room(db_session, hotel_b, "B1")


@pytest.fixture
def first_stay(db_session, user, room_a):
    """The guest already holds Hotel Aurora for IN..OUT."""
    return place_hold(db_session, user_id=user.id, room_id=room_a.id, check_in=IN, check_out=OUT)


def hold(db, user, room, a, b):
    return place_hold(db, user_id=user.id, room_id=room.id, check_in=a, check_out=b)


# --- the rule ---------------------------------------------------------------

def test_a_second_hotel_on_the_same_nights_is_blocked(db_session, user, room_b, first_stay):
    with pytest.raises(OverlappingStay) as error:
        hold(db_session, user, room_b, IN, OUT)
    conflict = error.value.conflict
    assert conflict.reservation_id == first_stay.id
    assert conflict.hotel_name == "Hotel Aurora"
    assert (conflict.check_in, conflict.check_out) == (IN, OUT)


@pytest.mark.parametrize("a,b", [
    (D(8), D(11)),    # overlaps the start
    (D(12), D(15)),   # overlaps the end
    (D(10), D(13)),   # identical
    (D(5), D(20)),    # surrounds it
    (D(11), D(12)),   # inside it
    (D(12), D(14)),   # shares only the last night
    (D(9), D(11)),    # shares only the first night
])
def test_every_overlap_shape_is_blocked(db_session, user, room_b, first_stay, a, b):
    with pytest.raises(OverlappingStay):
        hold(db_session, user, room_b, a, b)


@pytest.mark.parametrize("a,b", [
    (D(13), D(15)),   # checks in the day the first stay checks out
    (D(7), D(10)),    # checks out the day the first stay checks in
    (D(20), D(22)),   # well apart
])
def test_adjacent_and_separate_stays_are_allowed(db_session, user, room_b, first_stay, a, b):
    assert hold(db_session, user, room_b, a, b).status == "pending"


def test_two_rooms_at_the_same_hotel_are_allowed(db_session, user, hotel_a, first_stay):
    second_room = make_room(db_session, hotel_a, "A2")
    assert hold(db_session, user, second_room, IN, OUT).status == "pending"


def test_the_same_room_again_is_unavailable_not_an_overlap(db_session, user, room_a, first_stay):
    with pytest.raises(RoomUnavailable):
        hold(db_session, user, room_a, IN, OUT)


# --- which reservations count ----------------------------------------------

@pytest.mark.parametrize("status", ["pending", "confirmed"])
def test_holding_and_paid_stays_both_count(db_session, user, room_b, first_stay, status):
    first_stay.status = status
    db_session.commit()
    with pytest.raises(OverlappingStay):
        hold(db_session, user, room_b, IN, OUT)


def test_a_cancelled_stay_does_not_count(db_session, user, room_b, first_stay):
    first_stay.status = "cancelled"
    db_session.commit()
    assert hold(db_session, user, room_b, IN, OUT).status == "pending"


def test_an_expired_unpaid_hold_does_not_count(db_session, user, room_b, first_stay):
    first_stay.created_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    db_session.commit()
    assert hold(db_session, user, room_b, IN, OUT).status == "pending"
    db_session.refresh(first_stay)
    assert first_stay.status == "cancelled"


def test_another_guests_stay_does_not_count(db_session, other, room_b, first_stay):
    assert hold(db_session, other, room_b, IN, OUT).status == "pending"


def test_cancelling_the_first_stay_frees_the_guest_to_book_elsewhere(db_session, user, room_b, first_stay):
    with pytest.raises(OverlappingStay):
        hold(db_session, user, room_b, IN, OUT)
    first_stay.status = "cancelled"
    db_session.commit()
    assert hold(db_session, user, room_b, IN, OUT).status == "pending"


def test_the_earliest_conflicting_stay_is_reported(db_session, user, room_a, room_b, hotel_a):
    later = hold(db_session, user, room_a, D(14), D(16))
    earlier_room = make_room(db_session, hotel_a, "A9")
    earliest = hold(db_session, user, earlier_room, D(11), D(13))
    with pytest.raises(OverlappingStay) as error:
        hold(db_session, user, room_b, D(10), D(20))
    assert error.value.conflict.reservation_id == earliest.id
    assert later.id != earliest.id


def test_a_blocked_attempt_leaves_nothing_behind(db_session, user, room_b, first_stay):
    with pytest.raises(OverlappingStay):
        hold(db_session, user, room_b, IN, OUT)
    assert db_session.query(Reservation).filter_by(room_id=room_b.id).count() == 0
    assert db_session.query(Reservation).count() == 1


# --- order of checks --------------------------------------------------------

def test_a_deactivated_hotel_is_still_not_found(db_session, user, first_stay):
    closed = make_room(db_session, make_hotel(db_session, "Closed", active=False), "C1")
    with pytest.raises(RoomNotFound):
        hold(db_session, user, closed, IN, OUT)


# --- the query on its own ---------------------------------------------------

def test_query_can_ignore_a_reservation_being_changed(db_session, user, hotel_b, first_stay):
    args = dict(user_id=user.id, hotel_id=hotel_b.id, check_in=IN, check_out=OUT)
    assert find_overlapping_stay(db_session, **args).reservation_id == first_stay.id
    assert find_overlapping_stay(db_session, **args, exclude_reservation_id=first_stay.id) is None


def test_query_says_none_when_nothing_overlaps(db_session, user, hotel_b):
    assert find_overlapping_stay(db_session, user_id=user.id, hotel_id=hotel_b.id,
                                 check_in=IN, check_out=OUT) is None


# --- what the frontend actually receives ------------------------------------

def book(client, user, room, a, b):
    return client.post(
        "/reservations", headers=auth(user),
        json={"room_id": room.id, "check_in": a.isoformat(), "check_out": b.isoformat(), "num_guests": 1},
    )


def test_the_booking_endpoint_answers_409_with_the_conflicting_stay(client, user, room_a, room_b, first_stay):
    response = book(client, user, room_b, D(11), D(14))
    assert response.status_code == 409
    error = response.json()["detail"][0]
    assert error["type"] == "overlapping_stay"
    assert error["loc"] == ["body", "check_in"]
    assert "Hotel Aurora" in error["msg"] and "Cancel or change that booking first" in error["msg"]
    assert error["ctx"] == {
        "reservation_id": first_stay.id,
        "hotel_id": room_a.hotel_id,
        "hotel_name": "Hotel Aurora",
        "check_in": IN.isoformat(),
        "check_out": OUT.isoformat(),
    }


def test_the_endpoint_still_books_adjacent_stays(client, user, room_b, first_stay):
    assert book(client, user, room_b, OUT, D(15)).status_code == 201


def test_the_endpoint_still_books_other_guests(client, other, room_b, first_stay):
    assert book(client, other, room_b, IN, OUT).status_code == 201


def test_the_error_only_ever_shows_the_guests_own_stay(client, db_session, user, other, room_b, first_stay):
    """Two guests hold stays on the same nights; each only ever hears about their own."""
    others_stay = book(client, other, room_b, IN, OUT)  # Hotel Borealis; mine is Hotel Aurora
    assert others_stay.status_code == 201
    room_c = make_room(db_session, make_hotel(db_session, "Hotel Cascade"), "C1")
    response = book(client, other, room_c, D(11), D(12))
    ctx = response.json()["detail"][0]["ctx"]
    assert response.status_code == 409
    assert ctx["reservation_id"] == others_stay.json()["id"] and ctx["hotel_name"] == "Hotel Borealis"
    assert ctx["reservation_id"] != first_stay.id
