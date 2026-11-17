"""2.2.3 Cancel a reservation: edge cases (US2.2).

test_cancel.py (2.2.1) covers the endpoint's main paths. These cover what sits
around it: a payment that arrives after a cancel, the exact check-in-day
boundary, and that a cancel frees only its own dates.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Hotel, Payment, Reservation, Room, User
from app.security import issue_tokens
from app.services.availability import is_room_available
from app.services.booking_confirmation import NotPayable, confirm_booking
from app.services.cancellation import NotCancellable, cancel_reservation

TODAY = datetime.now(timezone.utc).date()
IN, OUT = TODAY + timedelta(days=10), TODAY + timedelta(days=13)


def make_user(db, email):
    user = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(user)
    db.commit()
    return user


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


@pytest.fixture
def user(db_session):
    return make_user(db_session, "me@x.com")


@pytest.fixture
def other(db_session):
    return make_user(db_session, "other@x.com")


@pytest.fixture
def room(db_session):
    hotel = Hotel(name="H", address="1 Main", city="San Jose", country="US")
    db_session.add(hotel)
    db_session.flush()
    room = Room(hotel_id=hotel.id, room_number="101", price_per_night=100, max_guests=2)
    db_session.add(room)
    db_session.commit()
    return room


def reserve(db, user, room, status="pending", check_in=IN, check_out=OUT):
    reservation = Reservation(
        user_id=user.id, room_id=room.id, check_in_date=check_in,
        check_out_date=check_out, total_price=300, status=status,
    )
    db.add(reservation)
    db.commit()
    return reservation


def cancel(client, reservation_id, headers):
    return client.post(f"/reservations/{reservation_id}/cancel", headers=headers)


def status_of(db, reservation):
    db.expire_all()
    return db.get(Reservation, reservation.id).status


def pay(db, reservation, transaction_id="txn_1"):
    # A real payment call gets a fresh session; drop what this one has cached
    # so it sees the cancel the API just wrote.
    db.expire_all()
    return confirm_booking(
        db, reservation_id=reservation.id, amount=300,
        payment_method="card", transaction_id=transaction_id,
    )


# A payment that arrives after the cancel.

def test_payment_after_cancel_is_refused_and_records_nothing(client, db_session, user, room):
    hold = reserve(db_session, user, room)
    assert cancel(client, hold.id, auth(user)).status_code == 200

    with pytest.raises(NotPayable):
        pay(db_session, hold)

    assert status_of(db_session, hold) == "cancelled"
    assert db_session.query(Payment).count() == 0


def test_late_copy_of_the_original_charge_does_not_revive_a_cancelled_booking(
    client, db_session, user, room
):
    hold = reserve(db_session, user, room)
    pay(db_session, hold, "txn_1")
    assert status_of(db_session, hold) == "confirmed"
    assert cancel(client, hold.id, auth(user)).status_code == 200

    # The provider resends the same charge after the cancel went through.
    with pytest.raises(NotPayable):
        pay(db_session, hold, "txn_1")

    assert status_of(db_session, hold) == "cancelled"
    assert is_room_available(db_session, room.id, IN, OUT) is True
    payments = db_session.query(Payment).all()
    assert len(payments) == 1  # the original charge, not a second one


# The check-in-day boundary, with "today" pinned so the test can't drift.

@pytest.mark.parametrize("days_before_check_in", [30, 7, 2, 1, 0])
def test_can_cancel_any_day_up_to_and_including_check_in(
    db_session, user, room, days_before_check_in
):
    reservation = reserve(db_session, user, room, status="confirmed")
    today = IN - timedelta(days=days_before_check_in)
    result = cancel_reservation(
        db_session, reservation_id=reservation.id, user_id=user.id, today=today
    )
    assert result.status == "cancelled"


@pytest.mark.parametrize("days_after_check_in", [1, 2, 3, 30])
def test_cannot_cancel_once_the_stay_has_started_or_ended(
    db_session, user, room, days_after_check_in
):
    reservation = reserve(db_session, user, room, status="confirmed")
    today = IN + timedelta(days=days_after_check_in)
    with pytest.raises(NotCancellable):
        cancel_reservation(
            db_session, reservation_id=reservation.id, user_id=user.id, today=today
        )
    assert status_of(db_session, reservation) == "confirmed"


# A cancel frees only its own dates.

def test_cancel_frees_only_that_stays_nights(client, db_session, user, room):
    first = reserve(db_session, user, room, check_in=IN, check_out=OUT)
    second = reserve(db_session, user, room, check_in=OUT, check_out=OUT + timedelta(days=2))

    assert cancel(client, first.id, auth(user)).status_code == 200

    assert is_room_available(db_session, room.id, IN, OUT) is True
    assert is_room_available(db_session, room.id, OUT, OUT + timedelta(days=2)) is False
    # A range that spans both stays is still blocked by the second one.
    assert is_room_available(db_session, room.id, IN, OUT + timedelta(days=1)) is False
    assert status_of(db_session, second) == "pending"


# Privacy holds for cancelled reservations too.

def test_someone_elses_cancelled_reservation_is_still_404(client, db_session, user, other, room):
    reservation = reserve(db_session, user, room, status="cancelled")
    response = cancel(client, reservation.id, auth(other))
    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "not_found"


def test_an_expired_hold_can_be_cancelled_again_without_error(client, db_session, user, room):
    # release_expired_holds marks a lapsed hold "cancelled"; a guest who then
    # clicks Cancel should get a normal answer, not an error.
    reservation = reserve(db_session, user, room, status="cancelled")
    response = cancel(client, reservation.id, auth(user))
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
