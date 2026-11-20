"""Modifying a reservation must obey the same rule as booking one (US2.4): a guest
may not hold stays at two different hotels that share a night."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Hotel, Reservation, Room, User
from app.security import issue_tokens
from app.services.booking_availability import place_hold

TODAY = datetime.now(timezone.utc).date()
D = lambda n: TODAY + timedelta(days=n)


def make_user(db, email):
    u = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(u)
    db.commit()
    return u


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


def make_room(db, hotel_name, number="1"):
    hotel = Hotel(name=hotel_name, address="1 Main", city="San Jose", country="US")
    db.add(hotel)
    db.flush()
    room = Room(hotel_id=hotel.id, room_number=number, price_per_night=100, max_guests=2)
    db.add(room)
    db.commit()
    return room


@pytest.fixture
def user(db_session):
    return make_user(db_session, "me@x.com")


@pytest.fixture
def aurora(db_session, user):
    """Hotel Aurora, D10..D13."""
    room = make_room(db_session, "Hotel Aurora")
    return place_hold(db_session, user_id=user.id, room_id=room.id, check_in=D(10), check_out=D(13))


@pytest.fixture
def borealis(db_session, user):
    """Hotel Borealis, D20..D23: safe from Aurora, and the one we will modify."""
    room = make_room(db_session, "Hotel Borealis")
    return place_hold(db_session, user_id=user.id, room_id=room.id, check_in=D(20), check_out=D(23))


def patch(client, reservation, user, **changes):
    body = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in changes.items()}
    return client.patch(f"/reservations/{reservation.id}", json=body, headers=auth(user))


def test_moving_onto_nights_held_at_another_hotel_is_blocked(client, db_session, user, aurora, borealis):
    response = patch(client, borealis, user, check_in=D(11), check_out=D(14))
    assert response.status_code == 409
    error = response.json()["detail"][0]
    assert error["type"] == "overlapping_stay"
    assert error["ctx"]["reservation_id"] == aurora.id and error["ctx"]["hotel_name"] == "Hotel Aurora"
    db_session.expire_all()
    assert db_session.get(Reservation, borealis.id).check_in_date == D(20)  # nothing changed


@pytest.mark.parametrize("a,b", [(D(8), D(11)), (D(12), D(15)), (D(5), D(20)), (D(10), D(13)), (D(11), D(12))])
def test_every_overlap_shape_is_blocked_when_modifying(client, user, aurora, borealis, a, b):
    assert patch(client, borealis, user, check_in=a, check_out=b).status_code == 409


@pytest.mark.parametrize("a,b", [(D(13), D(15)), (D(7), D(10)), (D(30), D(32))])
def test_adjacent_and_separate_dates_are_fine_when_modifying(client, user, aurora, borealis, a, b):
    assert patch(client, borealis, user, check_in=a, check_out=b).status_code == 200


def test_moving_into_a_room_at_the_same_hotel_is_fine(client, db_session, user, aurora):
    hotel_id = db_session.get(Room, aurora.room_id).hotel_id
    second_room = Room(hotel_id=hotel_id, room_number="A2", price_per_night=100, max_guests=2)
    db_session.add(second_room)
    db_session.commit()
    other_stay = place_hold(db_session, user_id=user.id, room_id=second_room.id, check_in=D(30), check_out=D(32))
    assert patch(client, other_stay, user, check_in=D(11), check_out=D(12)).status_code == 200


def test_a_reservation_never_conflicts_with_itself(client, user, aurora):
    assert patch(client, aurora, user, check_in=D(11), check_out=D(14)).status_code == 200


def test_switching_to_another_hotel_is_blocked_on_clashing_nights_and_fine_on_clear_ones(client, db_session, user, aurora):
    cascade = make_room(db_session, "Hotel Cascade")
    delta = make_room(db_session, "Hotel Delta")
    stay = place_hold(db_session, user_id=user.id, room_id=cascade.id, check_in=D(30), check_out=D(33))
    # Same nights as Aurora (D10..D13), at a different hotel: blocked, and nothing moves.
    assert patch(client, stay, user, room_id=delta.id, check_in=D(10), check_out=D(13)).status_code == 409
    db_session.expire_all()
    assert db_session.get(Reservation, stay.id).room_id == cascade.id
    # Clear nights at the new hotel: fine.
    response = patch(client, stay, user, room_id=delta.id, check_in=D(40), check_out=D(43))
    assert response.status_code == 200 and response.json()["room_id"] == delta.id


def test_a_cancelled_stay_no_longer_blocks_a_modify(client, db_session, user, aurora, borealis):
    aurora.status = "cancelled"
    db_session.commit()
    assert patch(client, borealis, user, check_in=D(11), check_out=D(14)).status_code == 200


def test_a_stay_moving_to_another_hotel_is_judged_by_the_new_hotel(client, db_session, user, aurora):
    """The stay sits at Hotel Aurora (another room) but moves to Hotel Delta on nights Aurora already holds."""
    aurora_hotel_id = db_session.get(Room, aurora.room_id).hotel_id
    second_aurora_room = Room(hotel_id=aurora_hotel_id, room_number="A2", price_per_night=100, max_guests=2)
    db_session.add(second_aurora_room)
    db_session.commit()
    stay = place_hold(db_session, user_id=user.id, room_id=second_aurora_room.id, check_in=D(30), check_out=D(33))
    delta = make_room(db_session, "Hotel Delta")
    # Same hotel as the clashing stay would be fine, but the NEW hotel (Delta) differs: blocked.
    assert patch(client, stay, user, room_id=delta.id, check_in=D(10), check_out=D(13)).status_code == 409


def test_switching_hotel_on_the_same_nights_does_not_conflict_with_itself(client, db_session, user):
    """Only the stay's own old nights overlap, at its old hotel: that must not count as a clash."""
    cascade = make_room(db_session, "Hotel Cascade")
    delta = make_room(db_session, "Hotel Delta")
    stay = place_hold(db_session, user_id=user.id, room_id=cascade.id, check_in=D(30), check_out=D(33))
    assert patch(client, stay, user, room_id=delta.id).status_code == 200
    assert patch(client, stay, user, room_id=cascade.id, check_in=D(31), check_out=D(34)).status_code == 200
