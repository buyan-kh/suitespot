"""Tests for US7.3, task 7.3.1 — Points redemption rules."""

from datetime import date
from decimal import Decimal

import pytest

from app.models import Hotel, Reservation, Room, User
from app.models.points import PointsLedger
from app.services.points import earn_points, get_balance
from app.services.redemption import (
    MIN_REDEMPTION_POINTS,
    POINTS_PER_DOLLAR,
    RedemptionQuote,
    apply_redemption,
    redemption_quote,
)


# ── shared helpers ────────────────────────────────────────────────────────────

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
    res = Reservation(
        user_id=user_id,
        room_id=room.id,
        check_in_date=date(2025, 8, 1),
        check_out_date=date(2025, 8, 3),
        num_guests=1,
        total_price=price,
        status="confirmed",
    )
    db.add(res)
    db.flush()
    return res


def _give_points(db, user_id, reservation, points: int):
    """Directly insert a ledger row so tests control the balance exactly."""
    entry = PointsLedger(
        user_id=user_id,
        reservation_id=reservation.id,
        delta=points,
        reason="stay_earned",
    )
    db.add(entry)
    db.commit()


# ── constants ─────────────────────────────────────────────────────────────────

def test_constants():
    """Conversion rate and minimum are set correctly."""
    assert POINTS_PER_DOLLAR == 100
    assert MIN_REDEMPTION_POINTS == 500


# ── redemption_quote — happy paths ────────────────────────────────────────────

def test_quote_basic_conversion(db_session):
    """1000 points → $10.00 discount."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1000)

    quote = redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=1000)

    assert quote.points_applied == 1000
    assert quote.dollar_discount == Decimal("10.00")
    assert quote.new_total == Decimal("190.00")


def test_quote_minimum_boundary(db_session):
    """Exactly 500 points ($5.00) is accepted."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=100.00)
    _give_points(db_session, u.id, res, 500)

    quote = redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=500)

    assert quote.points_applied == 500
    assert quote.dollar_discount == Decimal("5.00")


def test_quote_clamps_to_balance(db_session):
    """Requesting more points than balance → silently clamped to balance."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=500.00)
    _give_points(db_session, u.id, res, 800)

    quote = redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=2000)

    assert quote.points_applied == 800
    assert quote.balance_after == 0


def test_quote_clamps_to_reservation_total(db_session):
    """Points worth more than the reservation total → capped to the total."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=10.00)   # $10 total
    _give_points(db_session, u.id, res, 5000)            # 5000 pts = $50

    quote = redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=5000)

    # Maximum useful points = 10 * 100 = 1000
    assert quote.points_applied == 1000
    assert quote.new_total == Decimal("0.00")


def test_quote_balance_fields(db_session):
    """balance_before and balance_after are consistent."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1500)

    quote = redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=1000)

    assert quote.balance_before == 1500
    assert quote.balance_after == 500


def test_quote_does_not_write_ledger(db_session):
    """redemption_quote is read-only — no new ledger rows."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1000)

    rows_before = db_session.query(PointsLedger).count()
    redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=1000)
    rows_after = db_session.query(PointsLedger).count()

    assert rows_before == rows_after


# ── redemption_quote — error cases ───────────────────────────────────────────

def test_quote_below_minimum_raises(db_session):
    """Requesting fewer than 500 points raises ValueError."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1000)

    with pytest.raises(ValueError, match="Minimum redemption"):
        redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=499)


def test_quote_zero_points_raises(db_session):
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1000)

    with pytest.raises(ValueError):
        redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=0)


def test_quote_insufficient_balance_raises(db_session):
    """User has fewer than 500 points → raises ValueError."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 300)  # only 300 pts

    with pytest.raises(ValueError, match="Insufficient points balance"):
        redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=500)


def test_quote_zero_balance_raises(db_session):
    """User with zero points cannot redeem."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    # No points added.

    with pytest.raises(ValueError, match="Insufficient points balance"):
        redemption_quote(db_session, user_id=u.id, reservation=res, points_requested=500)


# ── apply_redemption ──────────────────────────────────────────────────────────

def test_apply_writes_ledger_row(db_session):
    """apply_redemption inserts a negative PointsLedger row."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1000)

    rows_before = db_session.query(PointsLedger).count()
    apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=1000)
    rows_after = db_session.query(PointsLedger).count()

    assert rows_after == rows_before + 1


def test_apply_ledger_row_is_negative(db_session):
    """The written ledger row has a negative delta."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1000)

    apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=1000)

    redemption_row = (
        db_session.query(PointsLedger)
        .filter_by(reason="points_redeemed")
        .one()
    )
    assert redemption_row.delta == -1000


def test_apply_reduces_balance(db_session):
    """After apply, get_balance reflects the deduction."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1500)

    apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=1000)

    assert get_balance(db_session, user_id=u.id) == 500


def test_apply_returns_correct_quote(db_session):
    """apply_redemption returns a RedemptionQuote with correct fields."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1000)

    quote = apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=1000)

    assert isinstance(quote, RedemptionQuote)
    assert quote.points_applied == 1000
    assert quote.dollar_discount == Decimal("10.00")
    assert quote.new_total == Decimal("190.00")
    assert quote.balance_after == 0


# ── HTTP endpoint tests ───────────────────────────────────────────────────────

def _register_and_login(client):
    client.post("/register", json={
        "email": "test@example.com",
        "password": "Password1!",
        "first_name": "Test",
        "last_name": "User",
    })
    r = client.post("/login", json={"email": "test@example.com", "password": "Password1!"})
    return r.json()["access_token"]


def _make_reservation_with_points(client, db_session, price=200.00, points=1000):
    """Create a reservation in the DB and credit points directly."""
    # Pull the user from DB via email.
    from app.models.user import User as UserModel
    user = db_session.query(UserModel).filter_by(email="test@example.com").first()
    res = _reservation(db_session, user.id, price=price)
    _give_points(db_session, user.id, res, points)
    return res


def test_http_quote_200(client, db_session):
    token = _register_and_login(client)
    res = _make_reservation_with_points(client, db_session)

    r = client.get(
        f"/reservations/{res.id}/redemption/quote?points=1000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["points_applied"] == 1000
    assert data["dollar_discount"] == 10.0
    assert data["new_total"] == 190.0


def test_http_quote_401_no_auth(client, db_session):
    token = _register_and_login(client)
    res = _make_reservation_with_points(client, db_session)

    r = client.get(f"/reservations/{res.id}/redemption/quote?points=1000")
    assert r.status_code == 401


def test_http_quote_422_below_min(client, db_session):
    token = _register_and_login(client)
    res = _make_reservation_with_points(client, db_session)

    r = client.get(
        f"/reservations/{res.id}/redemption/quote?points=100",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_http_quote_404_other_user(client, db_session):
    """Cannot quote against another user's reservation."""
    token = _register_and_login(client)

    # Create a second user and their reservation.
    u2 = _user(db_session, email="other@x.com")
    res2 = _reservation(db_session, u2.id, price=200.00)
    _give_points(db_session, u2.id, res2, 1000)

    r = client.get(
        f"/reservations/{res2.id}/redemption/quote?points=1000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_http_apply_200(client, db_session):
    token = _register_and_login(client)
    res = _make_reservation_with_points(client, db_session)

    r = client.post(
        f"/reservations/{res.id}/redemption/apply",
        json={"points": 1000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["points_applied"] == 1000
    assert data["balance_after"] == 0


def test_http_apply_writes_ledger(client, db_session):
    """POST apply creates a ledger row in the DB."""
    token = _register_and_login(client)
    res = _make_reservation_with_points(client, db_session, points=1500)

    rows_before = db_session.query(PointsLedger).count()
    client.post(
        f"/reservations/{res.id}/redemption/apply",
        json={"points": 1000},
        headers={"Authorization": f"Bearer {token}"},
    )
    rows_after = db_session.query(PointsLedger).count()
    assert rows_after == rows_before + 1


def test_http_apply_401_no_auth(client, db_session):
    token = _register_and_login(client)
    res = _make_reservation_with_points(client, db_session)

    r = client.post(
        f"/reservations/{res.id}/redemption/apply",
        json={"points": 1000},
    )
    assert r.status_code == 401
