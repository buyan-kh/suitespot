"""Tests for US7.1, task 7.1.1 — Points ledger table + earn rules."""

from datetime import date
from decimal import Decimal

import pytest

from app.models import Hotel, Reservation, Room, User
from app.models.points import PointsLedger
from app.services.points import earn_points, get_balance, reverse_points


# ── helpers ───────────────────────────────────────────────────────────────────

def _user(db, email="u@x.com"):
    u = User(email=email, hashed_password="x", first_name="A", last_name="B")
    db.add(u)
    db.flush()
    return u


def _reservation(db, user_id, price=200.00):
    hotel = Hotel(name="H", address="A", city="C", country="US",
                  star_rating=3, is_active=True)
    db.add(hotel)
    db.flush()
    room = Room(hotel_id=hotel.id, room_number="1", room_type="double",
                price_per_night=price / 2, max_guests=2)
    db.add(room)
    db.flush()
    r = Reservation(
        user_id=user_id, room_id=room.id,
        check_in_date=date(2025, 6, 1), check_out_date=date(2025, 6, 3),
        num_guests=1, total_price=price, status="confirmed",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ── earn tests ────────────────────────────────────────────────────────────────

def test_earn_creates_ledger_row(db_session):
    u = _user(db_session)
    res = _reservation(db_session, u.id, 200.00)
    entry = earn_points(db_session, reservation=res)
    assert entry.id is not None
    assert entry.user_id == u.id
    assert entry.reservation_id == res.id
    assert entry.delta == 200
    assert entry.reason == "stay_earned"


def test_earn_1_point_per_dollar(db_session):
    u = _user(db_session, "b@x.com")
    res = _reservation(db_session, u.id, 350.00)
    entry = earn_points(db_session, reservation=res)
    assert entry.delta == 350


def test_earn_floors_fractional_dollars(db_session):
    u = _user(db_session, "c@x.com")
    res = _reservation(db_session, u.id, 99.99)
    entry = earn_points(db_session, reservation=res)
    assert entry.delta == 99  # floor, not round


def test_balance_increases_after_earn(db_session):
    u = _user(db_session, "d@x.com")
    res = _reservation(db_session, u.id, 100.00)
    assert get_balance(db_session, user_id=u.id) == 0
    earn_points(db_session, reservation=res)
    assert get_balance(db_session, user_id=u.id) == 100


def test_balance_accumulates_across_reservations(db_session):
    u = _user(db_session, "e@x.com")
    r1 = _reservation(db_session, u.id, 100.00)
    r2 = _reservation(db_session, u.id, 200.00)
    earn_points(db_session, reservation=r1)
    earn_points(db_session, reservation=r2)
    assert get_balance(db_session, user_id=u.id) == 300


# ── reverse tests ─────────────────────────────────────────────────────────────

def test_reverse_subtracts_earned(db_session):
    u = _user(db_session, "f@x.com")
    res = _reservation(db_session, u.id, 150.00)
    earn_points(db_session, reservation=res)
    reverse_points(db_session, reservation=res)
    assert get_balance(db_session, user_id=u.id) == 0


def test_reverse_creates_negative_row(db_session):
    u = _user(db_session, "g@x.com")
    res = _reservation(db_session, u.id, 100.00)
    earn_points(db_session, reservation=res)
    entry = reverse_points(db_session, reservation=res)
    assert entry is not None
    assert entry.delta == -100
    assert entry.reason == "stay_reversed"


def test_reverse_no_earned_returns_none(db_session):
    u = _user(db_session, "h@x.com")
    res = _reservation(db_session, u.id, 100.00)
    result = reverse_points(db_session, reservation=res)
    assert result is None


def test_balance_never_goes_negative(db_session):
    u = _user(db_session, "i@x.com")
    res = _reservation(db_session, u.id, 100.00)
    # Manually insert a negative entry without prior earn
    db_session.add(PointsLedger(
        user_id=u.id, reservation_id=res.id,
        delta=-50, reason="manual_debit"
    ))
    db_session.commit()
    assert get_balance(db_session, user_id=u.id) == 0


def test_zero_balance_for_new_user(db_session):
    u = _user(db_session, "j@x.com")
    assert get_balance(db_session, user_id=u.id) == 0
