from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Hotel, Payment, Reservation, Room, User
from app.services.cancellation import cancel_reservation


TODAY = date(2026, 11, 20)


@pytest.fixture
def user(db_session):
    value = User(
        email="cancel-refund@example.com",
        hashed_password="x",
        first_name="Cancel",
        last_name="Refund",
    )
    db_session.add(value)
    db_session.commit()
    return value


@pytest.fixture
def room(db_session):
    hotel = Hotel(name="Refund Hotel", address="1 Main", city="San Jose", country="US")
    db_session.add(hotel)
    db_session.flush()
    value = Room(hotel_id=hotel.id, room_number="101", price_per_night=100, max_guests=2)
    db_session.add(value)
    db_session.commit()
    return value


def reservation_with_payment(db_session, user, room, check_in):
    reservation = Reservation(
        user_id=user.id,
        room_id=room.id,
        check_in_date=check_in,
        check_out_date=check_in + timedelta(days=3),
        total_price=300,
        status="confirmed",
    )
    db_session.add(reservation)
    db_session.flush()
    db_session.add(
        Payment(
            reservation_id=reservation.id,
            amount=300,
            payment_method="card",
            transaction_id=f"charge:{check_in}",
            status="succeeded",
        )
    )
    db_session.commit()
    return reservation


def refund_rows(db_session, reservation):
    return db_session.execute(
        select(Payment).where(
            Payment.reservation_id == reservation.id,
            Payment.payment_method == "refund",
        )
    ).scalars().all()


@pytest.mark.parametrize(
    ("days_until_checkin", "expected_refund"),
    [(10, Decimal("300.00")), (5, Decimal("150.00")), (1, Decimal("0.00"))],
)
def test_cancel_records_refund_for_each_policy_tier(
    db_session, user, room, days_until_checkin, expected_refund
):
    reservation = reservation_with_payment(
        db_session, user, room, TODAY + timedelta(days=days_until_checkin)
    )

    result = cancel_reservation(
        db_session,
        reservation_id=reservation.id,
        user_id=user.id,
        today=TODAY,
    )

    assert result.status == "cancelled"
    rows = refund_rows(db_session, reservation)
    if expected_refund:
        assert len(rows) == 1
        assert Decimal(str(rows[0].amount)) == -expected_refund
    else:
        assert rows == []


def test_cancel_without_a_successful_charge_does_not_create_refund(
    db_session, user, room
):
    reservation = Reservation(
        user_id=user.id,
        room_id=room.id,
        check_in_date=TODAY + timedelta(days=10),
        check_out_date=TODAY + timedelta(days=13),
        total_price=300,
        status="pending",
    )
    db_session.add(reservation)
    db_session.commit()

    cancel_reservation(
        db_session,
        reservation_id=reservation.id,
        user_id=user.id,
        today=TODAY,
    )

    assert refund_rows(db_session, reservation) == []


def test_repeated_cancel_does_not_create_a_second_refund(db_session, user, room):
    reservation = reservation_with_payment(
        db_session, user, room, TODAY + timedelta(days=10)
    )
    cancel_reservation(
        db_session,
        reservation_id=reservation.id,
        user_id=user.id,
        today=TODAY,
    )
    cancel_reservation(
        db_session,
        reservation_id=reservation.id,
        user_id=user.id,
        today=TODAY,
    )

    assert len(refund_rows(db_session, reservation)) == 1
