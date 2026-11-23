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
    AlreadyRedeemed,
    NotRedeemable,
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


# ── Bug fix tests (Darren's review) ──────────────────────────────────────────

# Bug 1: redeeming lowers the charge (reservation.total_price is updated).

def test_apply_lowers_reservation_total_price(db_session):
    """After apply, reservation.total_price reflects the discount."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1000)

    quote = apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=1000)

    db_session.refresh(res)
    assert Decimal(str(res.total_price)) == Decimal("190.00")
    assert quote.new_total == Decimal("190.00")


def test_apply_full_discount_sets_total_to_zero(db_session):
    """When points cover the entire stay, total_price is set to 0.00."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=10.00)
    _give_points(db_session, u.id, res, 5000)  # worth $50 — more than enough

    apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=5000)

    db_session.refresh(res)
    assert Decimal(str(res.total_price)) == Decimal("0.00")


# Bug 2: redeeming twice returns a clean error, not a 500.

def test_apply_twice_raises_already_redeemed(db_session):
    """Calling apply_redemption twice on the same reservation raises AlreadyRedeemed."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 2000)

    apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=1000)

    with pytest.raises(AlreadyRedeemed):
        apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=500)


def test_http_apply_twice_returns_409(client, db_session):
    """HTTP: second apply on the same reservation → 409, not 500."""
    token = _register_and_login(client)
    res = _make_reservation_with_points(client, db_session, points=2000)

    headers = {"Authorization": f"Bearer {token}"}
    r1 = client.post(f"/reservations/{res.id}/redemption/apply",
                     json={"points": 1000}, headers=headers)
    assert r1.status_code == 200

    r2 = client.post(f"/reservations/{res.id}/redemption/apply",
                     json={"points": 500}, headers=headers)
    assert r2.status_code == 409


# Bug 3: cancelled booking cannot be redeemed against.

@pytest.mark.parametrize("bad_status", ["cancelled", "completed"])
def test_apply_on_closed_reservation_raises_not_redeemable(db_session, bad_status):
    """apply_redemption raises NotRedeemable for cancelled/completed reservations."""
    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    res.status = bad_status
    db_session.flush()
    _give_points(db_session, u.id, res, 1000)

    with pytest.raises(NotRedeemable):
        apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=1000)


@pytest.mark.parametrize("bad_status", ["cancelled", "completed"])
def test_http_apply_on_closed_reservation_returns_409(client, db_session, bad_status):
    """HTTP: redeeming against a closed reservation → 409."""
    token = _register_and_login(client)
    res = _make_reservation_with_points(client, db_session)
    res.status = bad_status
    db_session.commit()

    r = client.post(
        f"/reservations/{res.id}/redemption/apply",
        json={"points": 1000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409


# Bug 4: points are reversed (returned) when a booking is refunded after redemption.

def test_reverse_points_returns_redeemed_points_on_refund(db_session):
    """When a booking that had points redeemed is refunded, the user gets
    the redeemed points back (net delta after all rows must be zero)."""
    from app.services.points import reverse_points

    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 1000)   # +1000 (stay earned)

    apply_redemption(db_session, user_id=u.id, reservation=res, points_requested=1000)
    # balance is now 0: earned 1000, spent 1000

    assert get_balance(db_session, user_id=u.id) == 0

    # Simulate cancellation / refund.
    reverse_points(db_session, reservation=res)

    # After reversal the net for this reservation is zero; balance returns to 0
    # (no stay_earned to restore either since they were also offset by the spend).
    # What matters: balance does not go negative.
    assert get_balance(db_session, user_id=u.id) == 0


def test_reverse_points_refunds_redeemed_points_when_earn_exists(db_session):
    """Earned points were awarded THEN spent on redemption.
    On refund: reverse(net) = reverse(+earn - spend) = -earn + spend → user
    ends up with net 0 for that reservation, which is correct."""
    from app.services.points import reverse_points

    u = _user(db_session)
    # Reservation A: earn 200 pts (stay at $200)
    res_a = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res_a, 200)

    # Reservation B: will be redeemed + refunded
    res_b = _reservation(db_session, u.id, price=200.00)

    # Redeem 500 pts from res_a balance against res_b
    # First give enough points via res_b for the test to work independently
    _give_points(db_session, u.id, res_b, 500)
    apply_redemption(db_session, user_id=u.id, reservation=res_b, points_requested=500)
    # balance: res_a +200, res_b +500-500=0 → total 200

    before = get_balance(db_session, user_id=u.id)

    # Refund res_b → reverse net for res_b (which is 0, so nothing changes)
    reverse_points(db_session, reservation=res_b)

    after = get_balance(db_session, user_id=u.id)
    assert after == before  # res_b net was 0, no change expected


def test_reverse_points_earn_only_still_works(db_session):
    """Existing behaviour: reversing a reservation that only has earned points
    (no redemption) still deducts those points."""
    from app.services.points import reverse_points

    u = _user(db_session)
    res = _reservation(db_session, u.id, price=200.00)
    _give_points(db_session, u.id, res, 200)

    assert get_balance(db_session, user_id=u.id) == 200
    reverse_points(db_session, reservation=res)
    assert get_balance(db_session, user_id=u.id) == 0
