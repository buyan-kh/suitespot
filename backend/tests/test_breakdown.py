"""Tests for US3.2, task 3.2.1 — price breakdown endpoint."""

from decimal import Decimal

import pytest

from app.models import Hotel, Reservation, Room, User
from app.services.passwords import hash_password


# ── helpers ───────────────────────────────────────────────────────────────────

def _register_and_login(client, email="guest@x.com"):
    client.post("/register", json={
        "email": email, "password": "Pass1234!", "first_name": "A", "last_name": "B"
    })
    r = client.post("/login", json={"email": email, "password": "Pass1234!"})
    return r.json()["access_token"]


def _make_reservation(db_session, user_id, room_id, check_in, check_out, price):
    r = Reservation(
        user_id=user_id, room_id=room_id,
        check_in_date=check_in, check_out_date=check_out,
        num_guests=1, total_price=price, status="pending",
    )
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    return r


def _seed(db_session):
    hotel = Hotel(name="H", address="A", city="C", country="US",
                  star_rating=3, is_active=True)
    db_session.add(hotel)
    db_session.flush()
    room = Room(hotel_id=hotel.id, room_number="1", room_type="double",
                price_per_night=100.00, max_guests=2)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)
    return room


# ── tests ─────────────────────────────────────────────────────────────────────

def test_breakdown_structure(client, db_session):
    from datetime import date
    token = _register_and_login(client)
    room = _seed(db_session)
    user = db_session.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(User).where(User.email == "guest@x.com")
    ).scalar_one()
    res = _make_reservation(
        db_session, user.id, room.id,
        date(2025, 6, 1), date(2025, 6, 4), 300.00
    )
    r = client.get(
        f"/reservations/{res.id}/breakdown",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["nights"] == 3
    assert body["rate_per_night"] == 100.0
    assert body["subtotal"] == 300.0
    assert isinstance(body["fees"], list)
    assert len(body["fees"]) == 3
    assert body["tax"] > 0
    assert body["total"] > body["subtotal"]


def test_breakdown_math(client, db_session):
    """rate=100 × 3 nights → subtotal 300; check every line."""
    from datetime import date
    token = _register_and_login(client, "math@x.com")
    room = _seed(db_session)
    user = db_session.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(User).where(User.email == "math@x.com")
    ).scalar_one()
    res = _make_reservation(
        db_session, user.id, room.id,
        date(2025, 7, 1), date(2025, 7, 4), 300.00
    )
    r = client.get(
        f"/reservations/{res.id}/breakdown",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    subtotal = Decimal("300.00")
    service_fee = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
    resort_fee  = (Decimal("15.00") * 3).quantize(Decimal("0.01"))
    cleaning    = Decimal("40.00")
    pre_tax = subtotal + service_fee + resort_fee + cleaning
    tax   = (pre_tax * Decimal("0.12")).quantize(Decimal("0.01"))
    total = pre_tax + tax

    assert Decimal(str(r["tax"])).quantize(Decimal("0.01")) == tax
    assert Decimal(str(r["total"])).quantize(Decimal("0.01")) == total


def test_breakdown_404_other_user(client, db_session):
    from datetime import date
    _register_and_login(client, "owner@x.com")
    token2 = _register_and_login(client, "other@x.com")
    room = _seed(db_session)
    owner = db_session.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(User).where(User.email == "owner@x.com")
    ).scalar_one()
    res = _make_reservation(
        db_session, owner.id, room.id,
        date(2025, 8, 1), date(2025, 8, 3), 200.00
    )
    r = client.get(
        f"/reservations/{res.id}/breakdown",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert r.status_code == 404


def test_breakdown_404_missing(client):
    token = _register_and_login(client, "miss@x.com")
    r = client.get(
        "/reservations/does-not-exist/breakdown",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_breakdown_requires_auth(client):
    r = client.get("/reservations/anything/breakdown")
    assert r.status_code == 401
