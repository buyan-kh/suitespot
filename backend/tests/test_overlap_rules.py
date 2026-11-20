"""2.4.5 Testing: same dates, adjacent dates, same hotel (US2.4).

US2.4: a guest can't hold rooms at two different hotels on the same nights.
test_overlap_block.py (2.4.2) covers the rule inside place_hold. These tests
cover what it doesn't:
  1. same dates, end to end through the API and the real payment/cancel paths
  2. adjacent dates, including one-night stays and the year boundary
  3. same hotel: allowed, and the right error when the room itself is taken
  4. changing a booking (PATCH /reservations/{id} and the re-quote) - not
     enforced yet, so those tests are strict xfails
  5. one guest's stays never affect or leak to another guest
  6. concurrency on PostgreSQL (opt-in: set SUITESPOT_PG_TEST_URL)
"""

import os
import threading
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Hotel, Room, User
from app.security import issue_tokens
from app.services.booking_availability import OverlappingStay, place_hold
from app.services.booking_confirmation import confirm_booking
from app.services.payment_failure import MAX_FAILED_ATTEMPTS, record_failed_payment

TODAY = datetime.now(timezone.utc).date()


def D(n):
    return TODAY + timedelta(days=n)


IN, OUT = D(10), D(13)  # the guest's first stay: 3 nights


def next_dec(day):
    """December `day` of a year far enough ahead that the stay is in the future."""
    year = TODAY.year if date(TODAY.year, 12, day) > TODAY + timedelta(days=2) else TODAY.year + 1
    return date(year, 12, day)


# --- helpers (copied, not imported, so other test files can change freely) ---

def make_user(db, email):
    user = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(user)
    db.commit()
    return user


def make_hotel(db, name, active=True):
    hotel = Hotel(name=name, address="1 Main", city="San Jose", country="US", is_active=active)
    db.add(hotel)
    db.commit()
    return hotel


def make_room(db, hotel, number, price=100):
    room = Room(hotel_id=hotel.id, room_number=number, price_per_night=price, max_guests=2)
    db.add(room)
    db.commit()
    return room


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


def book(client, user, room, check_in, check_out):
    return client.post(
        "/reservations", headers=auth(user),
        json={"room_id": room.id, "check_in": check_in.isoformat(),
              "check_out": check_out.isoformat(), "num_guests": 1},
    )


def error_of(response):
    return response.json()["detail"][0]


@pytest.fixture
def guest(db_session):
    return make_user(db_session, "guest@x.com")


@pytest.fixture
def stranger(db_session):
    return make_user(db_session, "stranger@x.com")


@pytest.fixture
def aurora(db_session):
    return make_hotel(db_session, "Hotel Aurora")


@pytest.fixture
def borealis(db_session):
    return make_hotel(db_session, "Hotel Borealis")


@pytest.fixture
def cascade(db_session):
    return make_hotel(db_session, "Hotel Cascade")


@pytest.fixture
def room_a(db_session, aurora):
    return make_room(db_session, aurora, "A1")


@pytest.fixture
def room_b(db_session, borealis):
    return make_room(db_session, borealis, "B1")


@pytest.fixture
def room_c(db_session, cascade):
    return make_room(db_session, cascade, "C1")


# --- 1. Same dates, end to end ----------------------------------------------

def test_same_dates_at_another_hotel_is_409_naming_the_first_stay(client, guest, room_a, room_b):
    first = book(client, guest, room_a, IN, OUT)
    assert first.status_code == 201
    second = book(client, guest, room_b, IN, OUT)
    assert second.status_code == 409
    error = error_of(second)
    assert error["type"] == "overlapping_stay"
    assert error["ctx"]["reservation_id"] == first.json()["id"]
    assert error["ctx"]["hotel_name"] == "Hotel Aurora"


def test_a_paid_stay_blocks_the_same_dates_elsewhere(client, db_session, guest, room_a, room_b):
    first = place_hold(db_session, user_id=guest.id, room_id=room_a.id, check_in=IN, check_out=OUT)
    confirm_booking(db_session, reservation_id=first.id, amount=first.total_price,
                    payment_method="card", transaction_id="txn_paid")
    db_session.refresh(first)
    assert first.status == "confirmed"
    response = book(client, guest, room_b, IN, OUT)
    assert response.status_code == 409
    assert error_of(response)["ctx"]["reservation_id"] == first.id


def test_cancelling_through_the_api_frees_the_same_dates_elsewhere(client, guest, room_a, room_b):
    first = book(client, guest, room_a, IN, OUT).json()
    assert book(client, guest, room_b, IN, OUT).status_code == 409
    assert client.post(f"/reservations/{first['id']}/cancel", headers=auth(guest)).status_code == 200
    assert book(client, guest, room_b, IN, OUT).status_code == 201


def test_a_hold_released_after_failed_payments_frees_the_same_dates(client, db_session, guest, room_a, room_b):
    first = place_hold(db_session, user_id=guest.id, room_id=room_a.id, check_in=IN, check_out=OUT)
    for attempt in range(MAX_FAILED_ATTEMPTS):
        record_failed_payment(db_session, reservation_id=first.id, amount=first.total_price,
                              payment_method="card", transaction_id=f"txn_fail_{attempt}")
    db_session.refresh(first)
    assert first.status == "cancelled"
    assert book(client, guest, room_b, IN, OUT).status_code == 201


def test_the_message_spells_out_both_years_across_new_year(client, guest, room_a, room_b):
    start = next_dec(30)
    end = start + timedelta(days=3)  # Jan 2 of the next year
    assert book(client, guest, room_a, start, end).status_code == 201
    response = book(client, guest, room_b, start, end)
    assert response.status_code == 409
    msg = error_of(response)["msg"]
    assert f"Dec 30, {start.year}" in msg and f"Jan 2, {end.year}" in msg
    assert error_of(response)["ctx"]["check_out"] == end.isoformat()


# --- 2. Adjacent dates --------------------------------------------------------

def test_checking_in_the_day_the_other_stay_checks_out(client, guest, room_a, room_b):
    assert book(client, guest, room_a, IN, OUT).status_code == 201
    assert book(client, guest, room_b, OUT, D(15)).status_code == 201


def test_checking_out_the_day_the_other_stay_checks_in(client, guest, room_a, room_b):
    assert book(client, guest, room_a, IN, OUT).status_code == 201
    assert book(client, guest, room_b, D(7), IN).status_code == 201


def test_three_hotels_back_to_back(client, guest, room_a, room_b, room_c):
    assert book(client, guest, room_a, D(10), D(13)).status_code == 201
    assert book(client, guest, room_b, D(13), D(15)).status_code == 201
    assert book(client, guest, room_c, D(15), D(17)).status_code == 201


def test_one_night_stays_next_to_each_other(client, guest, room_a, room_b, room_c):
    assert book(client, guest, room_a, D(10), D(11)).status_code == 201
    assert book(client, guest, room_b, D(11), D(12)).status_code == 201
    assert book(client, guest, room_c, D(10), D(11)).status_code == 409  # same single night


def test_adjacent_across_the_year_end(client, guest, room_a, room_b):
    start = next_dec(29)
    new_year = start + timedelta(days=3)  # Jan 1
    assert book(client, guest, room_a, start, new_year).status_code == 201
    assert book(client, guest, room_b, new_year, new_year + timedelta(days=2)).status_code == 201


# --- 3. Same hotel ------------------------------------------------------------

def test_two_rooms_at_one_hotel_then_a_second_hotel(client, db_session, guest, aurora, room_a, room_b):
    second_room = make_room(db_session, aurora, "A2")
    early = book(client, guest, second_room, D(9), D(12))
    assert early.status_code == 201
    assert book(client, guest, room_a, IN, OUT).status_code == 201  # same hotel: fine
    response = book(client, guest, room_b, IN, OUT)
    assert response.status_code == 409
    assert error_of(response)["ctx"]["reservation_id"] == early.json()["id"]  # the earlier one


def test_overlapping_rooms_at_the_same_hotel_are_allowed(client, db_session, guest, aurora, room_a):
    other_room = make_room(db_session, aurora, "A2")
    assert book(client, guest, room_a, IN, OUT).status_code == 201
    assert book(client, guest, other_room, D(12), D(15)).status_code == 201


def test_the_same_room_again_says_room_taken_not_overlapping_stay(client, guest, room_a):
    assert book(client, guest, room_a, IN, OUT).status_code == 201
    response = book(client, guest, room_a, IN, OUT)
    assert response.status_code == 409
    assert response.json()["detail"] == "Room is unavailable for those dates."


def test_a_stay_at_a_since_deactivated_hotel_still_blocks(client, db_session, guest, aurora, room_a, room_b):
    assert book(client, guest, room_a, IN, OUT).status_code == 201
    aurora.is_active = False  # the guest still holds that booking
    db_session.commit()
    response = book(client, guest, room_b, IN, OUT)
    assert response.status_code == 409
    assert error_of(response)["ctx"]["hotel_name"] == "Hotel Aurora"


# --- 4. Changing a booking ----------------------------------------------------

QUOTE_GAP = pytest.mark.xfail(
    strict=True,
    reason="modify (2.3.1) and the re-quote (2.3.2) don't apply the US2.4 rule yet; "
           "remove this marker when they call find_overlapping_stay",
)


@pytest.fixture
def two_stays(client, guest, room_a, room_b):
    """Aurora on IN..OUT, and a later Borealis stay that could be moved onto it."""
    aurora_stay = book(client, guest, room_a, IN, OUT).json()
    borealis_stay = book(client, guest, room_b, D(20), D(23)).json()
    return aurora_stay, borealis_stay


def change(client, guest, reservation_id, body, *, quote=False):
    if quote:
        return client.post(f"/reservations/{reservation_id}/quote-change", json=body, headers=auth(guest))
    return client.patch(f"/reservations/{reservation_id}", json=body, headers=auth(guest))


@pytest.mark.parametrize("quote", [False, pytest.param(True, marks=QUOTE_GAP)], ids=["modify", "quote"])
def test_moving_dates_onto_another_hotels_nights_is_refused(client, guest, two_stays, quote):
    aurora_stay, borealis_stay = two_stays
    response = change(client, guest, borealis_stay["id"],
                      {"check_in": IN.isoformat(), "check_out": OUT.isoformat()}, quote=quote)
    assert response.status_code == 409
    assert error_of(response)["type"] == "overlapping_stay"


@pytest.mark.parametrize("quote", [False, pytest.param(True, marks=QUOTE_GAP)], ids=["modify", "quote"])
def test_moving_room_and_dates_onto_another_hotels_nights_is_refused(
    client, guest, room_c, two_stays, quote
):
    aurora_stay, borealis_stay = two_stays
    response = change(client, guest, borealis_stay["id"],
                      {"room_id": room_c.id, "check_in": D(11).isoformat(), "check_out": D(12).isoformat()},
                      quote=quote)
    assert response.status_code == 409
    assert error_of(response)["type"] == "overlapping_stay"


@pytest.mark.parametrize("quote", [False, True], ids=["modify", "quote"])
def test_moving_within_the_same_hotel_onto_overlapping_nights_is_allowed(
    client, db_session, guest, aurora, two_stays, quote
):
    aurora_stay, _ = two_stays
    other_room = make_room(db_session, aurora, "A2")
    second = book(client, guest, other_room, D(30), D(32)).json()
    response = change(client, guest, second["id"],
                      {"check_in": IN.isoformat(), "check_out": OUT.isoformat()}, quote=quote)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("quote", [False, True], ids=["modify", "quote"])
def test_extending_a_stay_over_its_own_nights_is_allowed(client, guest, two_stays, quote):
    _, borealis_stay = two_stays
    response = change(client, guest, borealis_stay["id"], {"check_out": D(25).isoformat()}, quote=quote)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("quote", [False, True], ids=["modify", "quote"])
def test_moving_next_to_another_hotels_stay_is_allowed(client, guest, two_stays, quote):
    _, borealis_stay = two_stays
    response = change(client, guest, borealis_stay["id"],
                      {"check_in": OUT.isoformat(), "check_out": D(15).isoformat()}, quote=quote)
    assert response.status_code == 200, response.text


# --- 5. Between guests --------------------------------------------------------

def test_another_guests_stay_never_blocks_me(client, guest, stranger, room_a, room_b):
    assert book(client, stranger, room_a, IN, OUT).status_code == 201
    assert book(client, guest, room_b, IN, OUT).status_code == 201


def test_my_409_never_mentions_another_guests_stay(client, guest, stranger, room_a, room_b, room_c):
    theirs = book(client, stranger, room_a, IN, OUT).json()
    mine = book(client, guest, room_b, IN, OUT).json()
    response = book(client, guest, room_c, IN, OUT)
    assert response.status_code == 409
    error = error_of(response)
    assert error["ctx"]["reservation_id"] == mine["id"] != theirs["id"]
    assert "Aurora" not in error["msg"] and error["ctx"]["hotel_name"] == "Hotel Borealis"


# --- 6. Concurrency on PostgreSQL (opt-in) -------------------------------------

PG_URL = os.environ.get("SUITESPOT_PG_TEST_URL")


@pytest.mark.skipif(not PG_URL, reason="set SUITESPOT_PG_TEST_URL to run against PostgreSQL")
def test_simultaneous_bookings_at_different_hotels_have_one_winner():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base

    engine = create_engine(PG_URL)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        with Session() as db:
            user_id = make_user(db, "racer@x.com").id
            room_ids = [make_room(db, make_hotel(db, f"Hotel {i}"), f"R{i}").id for i in range(4)]

        for round_no in range(10):
            check_in = D(10 + round_no * 5)
            check_out = check_in + timedelta(days=2)
            barrier = threading.Barrier(len(room_ids))
            results = []

            def attempt(room_id):
                with Session() as db:
                    barrier.wait()
                    try:
                        place_hold(db, user_id=user_id, room_id=room_id,
                                   check_in=check_in, check_out=check_out)
                        results.append("won")
                    except OverlappingStay:
                        results.append("blocked")
                    except Exception as exc:  # anything else is a bug
                        results.append(repr(exc))

            threads = [threading.Thread(target=attempt, args=(r,)) for r in room_ids]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert sorted(results) == ["blocked"] * 3 + ["won"], f"round {round_no}: {results}"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
