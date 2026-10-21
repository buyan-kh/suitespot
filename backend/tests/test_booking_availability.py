from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Hotel, Reservation, Room, User
from app.services.availability import is_room_available
from app.services.booking_availability import (
    HOLD_MINUTES,
    InvalidStay,
    RoomNotFound,
    RoomUnavailable,
    place_hold,
    release_expired_holds,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
IN, OUT = date(2026, 11, 10), date(2026, 11, 13)  # 3 nights


@pytest.fixture
def room(db_session):
    hotel = Hotel(name="H", address="1 Main", city="San Jose", country="US")
    db_session.add(hotel)
    db_session.flush()
    room = Room(hotel_id=hotel.id, room_number="101", price_per_night=100, max_guests=2)
    db_session.add(room)
    db_session.commit()
    return room


@pytest.fixture
def user(db_session):
    u = User(email="g@example.com", hashed_password="x", first_name="G", last_name="H")
    db_session.add(u)
    db_session.commit()
    return u


def add_reservation(db, user, room, check_in, check_out, status="confirmed"):
    r = Reservation(
        user_id=user.id, room_id=room.id, check_in_date=check_in, check_out_date=check_out,
        total_price=100, status=status,
    )
    db.add(r)
    db.commit()
    return r


def hold(db, user, room, **kw):
    args = dict(user_id=user.id, room_id=room.id, check_in=IN, check_out=OUT, now=NOW)
    args.update(kw)
    h = place_hold(db, **args)
    # The DB stamps created_at with the real clock; pin it to the test clock.
    h.created_at = args["now"]
    db.commit()
    return h


def test_hold_is_created_pending_with_correct_price(db_session, user, room):
    h = hold(db_session, user, room)
    assert h.status == "pending"
    assert float(h.total_price) == 300.0  # 3 nights x 100
    assert h.check_in_date == IN and h.check_out_date == OUT


def test_confirmed_overlap_blocks_hold(db_session, user, room):
    add_reservation(db_session, user, room, date(2026, 11, 11), date(2026, 11, 12))
    with pytest.raises(RoomUnavailable):
        hold(db_session, user, room)


@pytest.mark.parametrize("a,b", [
    (date(2026, 11, 8), date(2026, 11, 11)),   # overlaps the start
    (date(2026, 11, 12), date(2026, 11, 15)),  # overlaps the end
    (date(2026, 11, 10), date(2026, 11, 13)),  # identical
    (date(2026, 11, 1), date(2026, 11, 30)),   # surrounds
])
def test_all_overlap_shapes_are_refused(db_session, user, room, a, b):
    add_reservation(db_session, user, room, a, b)
    with pytest.raises(RoomUnavailable):
        hold(db_session, user, room)


def test_back_to_back_stays_are_allowed(db_session, user, room):
    add_reservation(db_session, user, room, date(2026, 11, 7), IN)    # checks out the day we check in
    add_reservation(db_session, user, room, OUT, date(2026, 11, 16))  # checks in the day we check out
    assert hold(db_session, user, room).status == "pending"


def test_fresh_hold_blocks_second_guest(db_session, user, room):
    hold(db_session, user, room)
    with pytest.raises(RoomUnavailable):
        hold(db_session, user, room, now=NOW + timedelta(minutes=HOLD_MINUTES - 1))


def test_expired_hold_no_longer_blocks(db_session, user, room):
    first = hold(db_session, user, room)
    later = NOW + timedelta(minutes=HOLD_MINUTES + 1)
    assert hold(db_session, user, room, now=later).status == "pending"
    db_session.refresh(first)
    assert first.status == "cancelled"


def test_release_expired_holds_only_touches_stale_pending(db_session, user, room):
    stale = hold(db_session, user, room)
    confirmed = add_reservation(db_session, user, room, date(2027, 1, 1), date(2027, 1, 3))
    later = NOW + timedelta(minutes=HOLD_MINUTES + 1)
    assert release_expired_holds(db_session, now=later) == 1
    db_session.refresh(stale)
    db_session.refresh(confirmed)
    assert stale.status == "cancelled"
    assert confirmed.status == "confirmed"


def test_search_availability_agrees_after_hold_expires(db_session, user, room):
    """Search (1.1.2) and booking (2.1.2) must give the same answer."""
    hold(db_session, user, room)
    assert is_room_available(db_session, room.id, IN, OUT) is False
    release_expired_holds(db_session, now=NOW + timedelta(minutes=HOLD_MINUTES + 1))
    assert is_room_available(db_session, room.id, IN, OUT) is True


def test_cancelled_reservation_does_not_block(db_session, user, room):
    add_reservation(db_session, user, room, IN, OUT, status="cancelled")
    assert hold(db_session, user, room).status == "pending"


def test_other_rooms_are_unaffected(db_session, user, room):
    other = Room(hotel_id=room.hotel_id, room_number="102", price_per_night=80, max_guests=2)
    db_session.add(other)
    db_session.commit()
    add_reservation(db_session, user, other, IN, OUT)
    assert hold(db_session, user, room).room_id == room.id


def test_room_marked_unavailable_is_refused(db_session, user, room):
    room.is_available = False
    db_session.commit()
    with pytest.raises(RoomUnavailable):
        hold(db_session, user, room)


def test_unknown_room(db_session, user):
    with pytest.raises(RoomNotFound):
        place_hold(db_session, user_id=user.id, room_id="nope", check_in=IN, check_out=OUT, now=NOW)


@pytest.mark.parametrize("kw,field", [
    (dict(check_in=OUT, check_out=IN), "check_out"),
    (dict(check_in=IN, check_out=IN), "check_out"),
    (dict(check_in=date(2026, 10, 9), check_out=date(2026, 10, 11)), "check_in"),
    (dict(num_guests=0), "num_guests"),
    (dict(num_guests=3), "num_guests"),
])
def test_invalid_stays(db_session, user, room, kw, field):
    with pytest.raises(InvalidStay) as e:
        hold(db_session, user, room, **kw)
    assert e.value.field == field


def test_failed_hold_creates_nothing(db_session, user, room):
    add_reservation(db_session, user, room, IN, OUT)
    with pytest.raises(RoomUnavailable):
        hold(db_session, user, room)
    assert db_session.query(Reservation).count() == 1


def test_check_in_today_is_allowed(db_session, user, room):
    h = hold(db_session, user, room, check_in=NOW.date(), check_out=NOW.date() + timedelta(days=1))
    assert h.status == "pending"

def test_room_in_a_deactivated_hotel_is_refused(db_session, user, room):
    db_session.get(Hotel, room.hotel_id).is_active = False
    db_session.commit()
    with pytest.raises(RoomNotFound):
        hold(db_session, user, room)
    assert db_session.query(Reservation).count() == 0


def test_room_is_bookable_again_when_the_hotel_is_reactivated(db_session, user, room):
    hotel = db_session.get(Hotel, room.hotel_id)
    hotel.is_active = False
    db_session.commit()
    with pytest.raises(RoomNotFound):
        hold(db_session, user, room)
    hotel.is_active = True
    db_session.commit()
    assert hold(db_session, user, room).status == "pending"


def test_deactivating_one_hotel_does_not_block_another(db_session, user, room):
    db_session.get(Hotel, room.hotel_id).is_active = False
    other_hotel = Hotel(name="Open Inn", address="2 Main", city="San Jose", country="US")
    db_session.add(other_hotel)
    db_session.flush()
    other_room = Room(hotel_id=other_hotel.id, room_number="201", price_per_night=90, max_guests=2)
    db_session.add(other_room)
    db_session.commit()
    assert hold(db_session, user, other_room).status == "pending"
