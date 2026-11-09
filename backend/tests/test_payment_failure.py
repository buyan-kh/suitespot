"""3.1.5 Failed payment + retry handling (US3.1)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Hotel, Payment, Reservation, Room, User
from app.services.availability import is_room_available
from app.services.booking_availability import HOLD_MINUTES, place_hold
from app.services.booking_confirmation import NotPayable, confirm_booking
from app.services.payment_failure import (
    MAX_FAILED_ATTEMPTS,
    DuplicatePayment,
    ReservationNotFound,
    record_failed_payment,
    retry_status,
)

TODAY = datetime.now(timezone.utc).date()
IN, OUT = TODAY + timedelta(days=10), TODAY + timedelta(days=13)  # 3 nights x 100 = 300


def make_user(db, email):
    user = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(user)
    db.commit()
    return user


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


@pytest.fixture
def hold(db_session, user, room):
    return place_hold(db_session, user_id=user.id, room_id=room.id, check_in=IN, check_out=OUT)


def fail(db, reservation, txn="txn_1", amount=300):
    db.expire_all()  # each provider callback runs in a fresh session
    return record_failed_payment(
        db, reservation_id=reservation.id, amount=amount,
        payment_method="card", transaction_id=txn,
    )


def pay(db, reservation, txn="txn_ok", amount=300):
    db.expire_all()
    return confirm_booking(
        db, reservation_id=reservation.id, amount=amount,
        payment_method="card", transaction_id=txn,
    )


def payments(db):
    db.expire_all()
    return db.execute(select(Payment)).scalars().all()


def status_of(db, reservation):
    db.expire_all()
    return db.get(Reservation, reservation.id).status


# 1. A failure keeps the hold.

def test_first_failure_is_recorded_and_the_hold_stays(db_session, hold):
    result = fail(db_session, hold)

    assert result.payment.status == "failed"
    assert result.payment.paid_at is None
    assert result.attempts_left == MAX_FAILED_ATTEMPTS - 1
    assert result.hold_released is False
    assert result.already_recorded is False
    assert status_of(db_session, hold) == "pending"
    assert is_room_available(db_session, hold.room_id, IN, OUT) is False


# 2-3. Retrying works through confirm_booking.

def test_retry_with_a_new_charge_confirms(db_session, hold):
    fail(db_session, hold, txn="txn_1")
    confirmation = pay(db_session, hold, txn="txn_2")

    assert confirmation.reservation.status == "confirmed"
    statuses = sorted(p.status for p in payments(db_session))
    assert statuses == ["failed", "succeeded"]


def test_failed_then_succeeded_with_the_same_charge_id_is_one_row(db_session, hold):
    # Stripe keeps one PaymentIntent id across attempts on the same card form.
    fail(db_session, hold, txn="pi_1")
    assert pay(db_session, hold, txn="pi_1").reservation.status == "confirmed"

    rows = payments(db_session)
    assert len(rows) == 1
    assert rows[0].status == "succeeded"
    assert rows[0].paid_at is not None


def test_a_retry_after_two_failures_still_confirms(db_session, hold):
    fail(db_session, hold, txn="txn_1")
    fail(db_session, hold, txn="txn_2")
    assert pay(db_session, hold, txn="txn_3").reservation.status == "confirmed"


# 4-5. Too many failures release the hold.

def test_third_failure_releases_the_hold_and_frees_the_room(db_session, hold, other):
    fail(db_session, hold, txn="txn_1")
    fail(db_session, hold, txn="txn_2")
    result = fail(db_session, hold, txn="txn_3")

    assert result.hold_released is True
    assert result.attempts_left == 0
    assert status_of(db_session, hold) == "cancelled"
    assert is_room_available(db_session, hold.room_id, IN, OUT) is True
    another = place_hold(db_session, user_id=other.id, room_id=hold.room_id,
                         check_in=IN, check_out=OUT)
    assert another.status == "pending"


def test_a_released_hold_cannot_be_paid(db_session, hold):
    for n in range(MAX_FAILED_ATTEMPTS):
        fail(db_session, hold, txn=f"txn_{n}")
    with pytest.raises(NotPayable):
        pay(db_session, hold, txn="txn_late")


# 6-7. Webhook resends and out-of-order reports.

def test_the_same_failure_reported_twice_counts_once(db_session, hold):
    fail(db_session, hold, txn="txn_1")
    again = fail(db_session, hold, txn="txn_1")

    assert again.already_recorded is True
    assert again.attempts_left == MAX_FAILED_ATTEMPTS - 1
    assert len(payments(db_session)) == 1
    # Repeating it enough times must not release the hold either.
    for _ in range(MAX_FAILED_ATTEMPTS):
        fail(db_session, hold, txn="txn_1")
    assert status_of(db_session, hold) == "pending"


def test_a_failure_after_the_same_charge_succeeded_changes_nothing(db_session, hold):
    pay(db_session, hold, txn="pi_1")
    late = fail(db_session, hold, txn="pi_1")

    assert late.already_recorded is True
    assert status_of(db_session, hold) == "confirmed"
    rows = payments(db_session)
    assert len(rows) == 1
    assert rows[0].status == "succeeded"


def test_an_existing_pending_payment_row_is_updated_not_duplicated(db_session, hold):
    db_session.add(Payment(reservation_id=hold.id, amount=300, payment_method="card",
                           transaction_id="txn_1", status="pending"))
    db_session.commit()

    fail(db_session, hold, txn="txn_1")

    rows = payments(db_session)
    assert len(rows) == 1
    assert rows[0].status == "failed"


# 8. Failures on a booking that isn't a pending hold.

def test_failure_on_a_confirmed_booking_is_kept_but_changes_nothing(db_session, hold):
    pay(db_session, hold, txn="txn_ok")
    result = fail(db_session, hold, txn="txn_double_click")

    assert result.already_recorded is False
    assert result.attempts_left == 0
    assert status_of(db_session, hold) == "confirmed"
    assert sorted(p.status for p in payments(db_session)) == ["failed", "succeeded"]


@pytest.mark.parametrize("status", ["cancelled", "completed"])
def test_failure_on_a_closed_reservation_is_kept_but_changes_nothing(db_session, hold, status):
    hold.status = status
    db_session.commit()

    result = fail(db_session, hold)

    assert result.hold_released is False
    assert result.attempts_left == 0
    assert status_of(db_session, hold) == status
    assert [p.status for p in payments(db_session)] == ["failed"]


# 9. Bad input.

def test_a_charge_id_from_another_reservation_is_refused(db_session, hold, other, room):
    theirs = place_hold(db_session, user_id=other.id, room_id=room.id,
                        check_in=OUT, check_out=OUT + timedelta(days=1))
    fail(db_session, theirs, txn="txn_1", amount=100)

    with pytest.raises(DuplicatePayment):
        fail(db_session, hold, txn="txn_1")
    assert len(payments(db_session)) == 1


@pytest.mark.parametrize("txn", ["", None])
def test_transaction_id_is_required(db_session, hold, txn):
    with pytest.raises(ValueError):
        fail(db_session, hold, txn=txn)
    assert payments(db_session) == []


def test_unknown_reservation(db_session):
    with pytest.raises(ReservationNotFound):
        record_failed_payment(db_session, reservation_id="nope", amount=300,
                              payment_method="card", transaction_id="txn_1")
    with pytest.raises(ReservationNotFound):
        retry_status(db_session, reservation_id="nope")


# 10. retry_status.

def test_retry_is_allowed_on_a_fresh_hold(db_session, hold):
    status = retry_status(db_session, reservation_id=hold.id)
    assert status.allowed is True
    assert status.attempts_left == MAX_FAILED_ATTEMPTS
    assert status.reason is None
    assert status.hold_expires_at is not None


def test_retry_counts_down_after_each_failure(db_session, hold):
    fail(db_session, hold, txn="txn_1")
    status = retry_status(db_session, reservation_id=hold.id)
    assert status.allowed is True
    assert status.attempts_left == MAX_FAILED_ATTEMPTS - 1


def test_retry_is_not_allowed_once_the_hold_runs_out(db_session, hold):
    fail(db_session, hold)
    created = hold.created_at.replace(tzinfo=timezone.utc) if hold.created_at.tzinfo is None else hold.created_at
    almost = created + timedelta(minutes=HOLD_MINUTES) - timedelta(seconds=1)
    after = created + timedelta(minutes=HOLD_MINUTES)

    assert retry_status(db_session, reservation_id=hold.id, now=almost).allowed is True
    expired = retry_status(db_session, reservation_id=hold.id, now=after)
    assert expired.allowed is False
    assert expired.reason == "hold_expired"


def test_retry_is_not_allowed_after_too_many_failures(db_session, hold):
    for n in range(MAX_FAILED_ATTEMPTS):
        fail(db_session, hold, txn=f"txn_{n}")
    status = retry_status(db_session, reservation_id=hold.id)
    assert status.allowed is False
    assert status.reason == "too_many_attempts"
    assert status.attempts_left == 0


def test_retry_is_not_allowed_on_a_paid_booking(db_session, hold):
    pay(db_session, hold)
    status = retry_status(db_session, reservation_id=hold.id)
    assert status.allowed is False
    assert status.reason == "not_payable"


def test_retry_is_not_allowed_on_a_cancelled_booking(db_session, hold):
    hold.status = "cancelled"
    db_session.commit()
    assert retry_status(db_session, reservation_id=hold.id).reason == "not_payable"


# 11. Money is stored to the cent.

@pytest.mark.parametrize("amount", [300, "300", 300.0, "300.004"])
def test_amount_is_stored_to_the_cent(db_session, hold, amount):
    result = fail(db_session, hold, amount=amount)
    assert Decimal(str(result.payment.amount)) == Decimal("300.00")


# 12. Two copies of one failure racing.

def test_two_copies_of_one_failure_racing_is_retried_not_a_crash(db_session, hold, monkeypatch):
    real_commit = Session.commit
    calls = {"n": 0}

    def flaky_commit(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: payments.transaction_id"))
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", flaky_commit)
    result = fail(db_session, hold)
    monkeypatch.undo()

    assert result.payment.status == "failed"
    assert len(payments(db_session)) == 1
    assert status_of(db_session, hold) == "pending"
