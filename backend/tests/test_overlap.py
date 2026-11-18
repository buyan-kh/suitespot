"""Tests for US2.4, task 2.4.1 — Overlap detection across reservations."""

from datetime import date

import pytest

from app.models import Hotel, Reservation, Room, User
from app.services.overlap import OverlappingStay, find_overlapping_stay


# ── helpers ───────────────────────────────────────────────────────────────────

def _hotel(db, name="Hotel A"):
    h = Hotel(name=name, address="1 Main St", city="SF", country="US",
              star_rating=3, is_active=True)
    db.add(h)
    db.flush()
    return h


def _room(db, hotel_id, number="101"):
    r = Room(hotel_id=hotel_id, room_number=number, room_type="double",
             price_per_night=100, max_guests=2)
    db.add(r)
    db.flush()
    return r


def _user(db, email="u@x.com"):
    u = User(email=email, hashed_password="x", first_name="A", last_name="B")
    db.add(u)
    db.flush()
    return u


def _reservation(db, user_id, room_id, check_in, check_out, status="confirmed"):
    res = Reservation(
        user_id=user_id, room_id=room_id,
        check_in_date=check_in, check_out_date=check_out,
        num_guests=1, total_price=200, status=status,
    )
    db.add(res)
    db.flush()
    return res


# ── find_overlapping_stay tests ───────────────────────────────────────────────

def test_no_conflict_no_existing_reservations(db_session):
    u = _user(db_session)
    h = _hotel(db_session)
    result = find_overlapping_stay(
        db_session, user_id=u.id, hotel_id=h.id,
        check_in=date(2025, 8, 1), check_out=date(2025, 8, 5),
    )
    assert result is None


def test_conflict_exact_same_dates(db_session):
    """Same dates at different hotel → conflict."""
    u = _user(db_session)
    h1 = _hotel(db_session, "Hotel A")
    h2 = _hotel(db_session, "Hotel B")
    r1 = _room(db_session, h1.id)
    _reservation(db_session, u.id, r1.id, date(2025, 8, 1), date(2025, 8, 5))

    conflict = find_overlapping_stay(
        db_session, user_id=u.id, hotel_id=h2.id,
        check_in=date(2025, 8, 1), check_out=date(2025, 8, 5),
    )
    assert conflict is not None


def test_conflict_overlapping_dates(db_session):
    """Partial overlap → conflict."""
    u = _user(db_session)
    h1 = _hotel(db_session, "Hotel A")
    h2 = _hotel(db_session, "Hotel B")
    r1 = _room(db_session, h1.id)
    _reservation(db_session, u.id, r1.id, date(2025, 8, 1), date(2025, 8, 5))

    conflict = find_overlapping_stay(
        db_session, user_id=u.id, hotel_id=h2.id,
        check_in=date(2025, 8, 3), check_out=date(2025, 8, 8),
    )
    assert conflict is not None


def test_no_conflict_adjacent_dates(db_session):
    """Back-to-back stays (check-out == next check-in) are allowed."""
    u = _user(db_session)
    h1 = _hotel(db_session, "Hotel A")
    h2 = _hotel(db_session, "Hotel B")
    r1 = _room(db_session, h1.id)
    _reservation(db_session, u.id, r1.id, date(2025, 8, 1), date(2025, 8, 5))

    conflict = find_overlapping_stay(
        db_session, user_id=u.id, hotel_id=h2.id,
        check_in=date(2025, 8, 5), check_out=date(2025, 8, 9),
    )
    assert conflict is None


def test_no_conflict_same_hotel(db_session):
    """Overlap at the SAME hotel is allowed (multiple rooms)."""
    u = _user(db_session)
    h = _hotel(db_session)
    r = _room(db_session, h.id)
    _reservation(db_session, u.id, r.id, date(2025, 8, 1), date(2025, 8, 5))

    conflict = find_overlapping_stay(
        db_session, user_id=u.id, hotel_id=h.id,
        check_in=date(2025, 8, 1), check_out=date(2025, 8, 5),
    )
    assert conflict is None


def test_no_conflict_cancelled_reservation(db_session):
    """Cancelled reservations don't block new bookings."""
    u = _user(db_session)
    h1 = _hotel(db_session, "Hotel A")
    h2 = _hotel(db_session, "Hotel B")
    r1 = _room(db_session, h1.id)
    _reservation(db_session, u.id, r1.id, date(2025, 8, 1), date(2025, 8, 5),
                 status="cancelled")

    conflict = find_overlapping_stay(
        db_session, user_id=u.id, hotel_id=h2.id,
        check_in=date(2025, 8, 1), check_out=date(2025, 8, 5),
    )
    assert conflict is None


def test_no_conflict_different_user(db_session):
    """Another user's conflicting stay doesn't block this user."""
    u1 = _user(db_session, "u1@x.com")
    u2 = _user(db_session, "u2@x.com")
    h1 = _hotel(db_session, "Hotel A")
    h2 = _hotel(db_session, "Hotel B")
    r1 = _room(db_session, h1.id)
    _reservation(db_session, u1.id, r1.id, date(2025, 8, 1), date(2025, 8, 5))

    conflict = find_overlapping_stay(
        db_session, user_id=u2.id, hotel_id=h2.id,
        check_in=date(2025, 8, 1), check_out=date(2025, 8, 5),
    )
    assert conflict is None


def test_exclude_reservation_id(db_session):
    """exclude_reservation_id lets a modify-booking skip its own reservation."""
    u = _user(db_session)
    h1 = _hotel(db_session, "Hotel A")
    h2 = _hotel(db_session, "Hotel B")
    r1 = _room(db_session, h1.id)
    existing = _reservation(db_session, u.id, r1.id, date(2025, 8, 1), date(2025, 8, 5))

    # Without exclude — sees itself as a conflict (same user, diff hotel doesn't apply here,
    # but test the exclude param contract)
    conflict = find_overlapping_stay(
        db_session, user_id=u.id, hotel_id=h2.id,
        check_in=date(2025, 8, 1), check_out=date(2025, 8, 5),
        exclude_reservation_id=existing.id,
    )
    assert conflict is None


def test_conflict_contains_reservation_object(db_session):
    """The returned object is the conflicting Reservation."""
    u = _user(db_session)
    h1 = _hotel(db_session, "Hotel A")
    h2 = _hotel(db_session, "Hotel B")
    r1 = _room(db_session, h1.id)
    existing = _reservation(db_session, u.id, r1.id, date(2025, 8, 1), date(2025, 8, 5))

    conflict = find_overlapping_stay(
        db_session, user_id=u.id, hotel_id=h2.id,
        check_in=date(2025, 8, 2), check_out=date(2025, 8, 6),
    )
    assert conflict.id == existing.id


# ── HTTP endpoint integration ─────────────────────────────────────────────────

def _register_and_login(client):
    client.post("/register", json={
        "email": "test@example.com", "password": "Password1!",
        "first_name": "Test", "last_name": "User",
    })
    r = client.post("/login", json={"email": "test@example.com", "password": "Password1!"})
    return r.json()["access_token"]


def _make_hotels_and_rooms(db_session):
    h1 = _hotel(db_session, "Alpha Hotel")
    h2 = _hotel(db_session, "Beta Hotel")
    r1 = _room(db_session, h1.id, "101")
    r2 = _room(db_session, h2.id, "201")
    db_session.commit()
    return h1, h2, r1, r2


def test_http_booking_blocked_by_overlap(client, db_session):
    """POST /reservations returns 409 when user has overlapping stay elsewhere."""
    token = _register_and_login(client)
    h1, h2, r1, r2 = _make_hotels_and_rooms(db_session)

    # First booking at hotel 1
    r = client.post("/reservations", json={
        "room_id": r1.id,
        "check_in": "2030-09-01",
        "check_out": "2030-09-05",
        "num_guests": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201

    # Confirm it so it's not in pending state
    from app.models.user import User as UserModel
    user = db_session.query(UserModel).filter_by(email="test@example.com").first()
    res = db_session.query(Reservation).filter_by(user_id=user.id).first()
    res.status = "confirmed"
    db_session.commit()

    # Second booking at hotel 2 — overlapping dates
    r2_resp = client.post("/reservations", json={
        "room_id": r2.id,
        "check_in": "2030-09-02",
        "check_out": "2030-09-06",
        "num_guests": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    assert r2_resp.status_code == 409
    assert r2_resp.json()["detail"]["code"] == "overlapping_stay"


def test_http_adjacent_booking_allowed(client, db_session):
    """Back-to-back stays at different hotels are allowed."""
    token = _register_and_login(client)
    h1, h2, r1, r2 = _make_hotels_and_rooms(db_session)

    r = client.post("/reservations", json={
        "room_id": r1.id,
        "check_in": "2030-09-01",
        "check_out": "2030-09-05",
        "num_guests": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201

    from app.models.user import User as UserModel
    user = db_session.query(UserModel).filter_by(email="test@example.com").first()
    res = db_session.query(Reservation).filter_by(user_id=user.id).first()
    res.status = "confirmed"
    db_session.commit()

    # Second stay starts exactly when first ends — should be allowed
    r2_resp = client.post("/reservations", json={
        "room_id": r2.id,
        "check_in": "2030-09-05",
        "check_out": "2030-09-09",
        "num_guests": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    assert r2_resp.status_code == 201
