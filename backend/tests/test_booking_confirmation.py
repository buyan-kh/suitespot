from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Hotel, Payment, Reservation, Room, User
from app.services.availability import is_room_available
from app.services.booking_availability import HOLD_MINUTES, place_hold
from app.services.booking_confirmation import (
    AmountMismatch,
    DuplicatePayment,
    NotPayable,
    ReservationNotFound,
    confirm_booking,
)

TODAY = datetime.now(timezone.utc).date()
IN, OUT = TODAY + timedelta(days=10), TODAY + timedelta(days=13)  # 3 nights x 100 = 300


@pytest.fixture
def user(db_session):
    u = User(email="pay@x.com", hashed_password="x", first_name="P", last_name="Q")
    db_session.add(u)
    db_session.commit()
    return u


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


def pay(db, reservation, amount=300, txn="txn_1", method="card"):
    return confirm_booking(
        db, reservation_id=reservation.id, amount=amount,
        payment_method=method, transaction_id=txn,
    )


def payments(db):
    db.expire_all()
    return db.execute(select(Payment)).scalars().all()


def status_of(db, reservation):
    db.expire_all()
    return db.get(Reservation, reservation.id).status


def test_successful_charge_confirms_the_booking(db_session, hold):
    result = pay(db_session, hold)
    assert result.already_confirmed is False
    assert result.reservation.status == "confirmed"
    assert status_of(db_session, hold) == "confirmed"


def test_payment_is_recorded(db_session, hold):
    pay(db_session, hold, txn="txn_abc")
    [p] = payments(db_session)
    assert p.reservation_id == hold.id
    assert p.transaction_id == "txn_abc"
    assert p.status == "succeeded"
    assert p.payment_method == "card"
    assert float(p.amount) == 300.0
    assert p.paid_at is not None


def test_confirmed_booking_still_blocks_the_room(db_session, hold, room):
    pay(db_session, hold)
    assert is_room_available(db_session, room.id, IN, OUT) is False


def test_same_charge_reported_twice_pays_once(db_session, hold):
    first = pay(db_session, hold)
    second = pay(db_session, hold)
    assert first.already_confirmed is False
    assert second.already_confirmed is True
    assert len(payments(db_session)) == 1
    assert status_of(db_session, hold) == "confirmed"


def test_existing_pending_payment_row_is_updated_not_duplicated(db_session, hold):
    """The charge endpoint (3.1.2) may create a pending Payment when it starts the charge."""
    db_session.add(Payment(reservation_id=hold.id, amount=300, payment_method="card",
                           transaction_id="txn_1", status="pending"))
    db_session.commit()
    pay(db_session, hold, txn="txn_1")
    [p] = payments(db_session)
    assert p.status == "succeeded" and p.paid_at is not None


@pytest.mark.parametrize("amount", [299.99, 300.01, 0, 150, 3000])
def test_wrong_amount_is_refused_and_nothing_changes(db_session, hold, amount):
    with pytest.raises(AmountMismatch) as error:
        pay(db_session, hold, amount=amount)
    assert error.value.expected == Decimal("300.00")
    assert status_of(db_session, hold) == "pending"
    assert payments(db_session) == []


@pytest.mark.parametrize("amount", [300, 300.0, "300", "300.00", Decimal("300.0")])
def test_amount_formats_that_equal_the_total_are_accepted(db_session, hold, amount):
    assert pay(db_session, hold, amount=amount).reservation.status == "confirmed"


def test_cancelled_reservation_cannot_be_paid(db_session, hold):
    hold.status = "cancelled"
    db_session.commit()
    with pytest.raises(NotPayable):
        pay(db_session, hold)
    assert status_of(db_session, hold) == "cancelled"
    assert payments(db_session) == []


def test_completed_reservation_cannot_be_paid(db_session, hold):
    hold.status = "completed"
    db_session.commit()
    with pytest.raises(NotPayable):
        pay(db_session, hold)
    assert payments(db_session) == []


def test_paying_a_confirmed_booking_with_another_charge_is_a_duplicate(db_session, hold):
    pay(db_session, hold, txn="txn_1")
    with pytest.raises(DuplicatePayment):
        pay(db_session, hold, txn="txn_2")
    assert [p.transaction_id for p in payments(db_session)] == ["txn_1"]


def test_charge_id_from_another_reservation_is_refused(db_session, user, room, hold):
    other = place_hold(
        db_session, user_id=user.id, room_id=room.id,
        check_in=OUT + timedelta(days=2), check_out=OUT + timedelta(days=4),
    )
    pay(db_session, hold, txn="txn_1")
    with pytest.raises(DuplicatePayment):
        pay(db_session, other, amount=200, txn="txn_1")
    assert status_of(db_session, other) == "pending"


def test_unknown_reservation(db_session):
    with pytest.raises(ReservationNotFound):
        confirm_booking(db_session, reservation_id="nope", amount=1,
                        payment_method="card", transaction_id="t")


@pytest.mark.parametrize("txn", ["", None])
def test_transaction_id_is_required(db_session, hold, txn):
    with pytest.raises(ValueError):
        pay(db_session, hold, txn=txn)
    assert status_of(db_session, hold) == "pending"


def test_a_late_payment_still_confirms_if_the_hold_was_not_released(db_session, hold):
    """Paying after the 15-minute hold window works while nobody else has taken the room."""
    hold.created_at = datetime.now(timezone.utc) - timedelta(minutes=HOLD_MINUTES + 5)
    db_session.commit()
    assert pay(db_session, hold).reservation.status == "confirmed"


def test_a_late_payment_after_the_hold_was_released_is_not_payable(db_session, hold):
    hold.status = "cancelled"  # what release_expired_holds does
    db_session.commit()
    with pytest.raises(NotPayable):
        pay(db_session, hold)


def test_two_copies_of_one_charge_racing_is_retried_not_a_crash(db_session, hold, monkeypatch):
    real_commit = Session.commit
    calls = {"n": 0}

    def flaky_commit(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: payments.transaction_id"))
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", flaky_commit)
    assert pay(db_session, hold).reservation.status == "confirmed"
    monkeypatch.undo()
    assert len(payments(db_session)) == 1


def test_only_the_paid_reservation_changes(db_session, user, room, hold):
    other = place_hold(
        db_session, user_id=user.id, room_id=room.id,
        check_in=OUT + timedelta(days=2), check_out=OUT + timedelta(days=4),
    )
    pay(db_session, hold)
    assert status_of(db_session, other) == "pending"