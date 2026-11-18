"""Tests for US3.1, task 3.1.2 — payment confirmation endpoint."""
from datetime import date
import pytest
from app.models import Hotel, Reservation, Room, User
from app.models.payment import Payment


# ── helpers ───────────────────────────────────────────────────────────────────

def _setup(db_session):
    """Create a hotel, room, user, and pending reservation."""
    hotel = Hotel(name="Test Hotel", address="1 St", city="SF", country="US",
                  star_rating=3, is_active=True)
    db_session.add(hotel)
    db_session.flush()
    room = Room(hotel_id=hotel.id, room_number="101", room_type="double",
                price_per_night=100, max_guests=2)
    db_session.add(room)
    db_session.flush()
    user = User(email="pay@test.com", hashed_password="x", first_name="A", last_name="B")
    db_session.add(user)
    db_session.flush()
    res = Reservation(user_id=user.id, room_id=room.id,
                      check_in_date="2030-01-01", check_out_date="2030-01-03",
                      num_guests=1, total_price=200, status="pending")
    db_session.add(res)
    db_session.commit()
    return user, res


def _login(client):
    client.post("/register", json={
        "email": "pay@test.com", "password": "Password1!",
        "first_name": "A", "last_name": "B",
    })
    r = client.post("/login", json={"email": "pay@test.com", "password": "Password1!"})
    return r.json()["access_token"]


# ── tests ─────────────────────────────────────────────────────────────────────

def test_confirm_payment_success(client, db_session):
    token = _login(client)
    # create a pending reservation directly in db for this user
    from app.models.user import User as UserModel
    user = db_session.query(UserModel).filter_by(email="pay@test.com").first()
    hotel = Hotel(name="H1", address="1 St", city="SF", country="US",
                  star_rating=3, is_active=True)
    db_session.add(hotel)
    db_session.flush()
    room = Room(hotel_id=hotel.id, room_number="101", room_type="double",
                price_per_night=100, max_guests=2)
    db_session.add(room)
    db_session.flush()
    res = Reservation(user_id=user.id, room_id=room.id,
                      check_in_date=date(2030,2,1), check_out_date=date(2030,2,3),
                      num_guests=1, total_price=200, status="pending")
    db_session.add(res)
    db_session.commit()

    r = client.post(f"/reservations/{res.id}/confirm", json={
        "amount": 200.00,
        "payment_method": "card",
        "transaction_id": "txn_abc123",
    }, headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "confirmed"
    assert data["already_confirmed"] is False
    assert data["payment"]["transaction_id"] == "txn_abc123"
    assert data["payment"]["amount"] == 200.0


def test_confirm_payment_amount_mismatch(client, db_session):
    token = _login(client)
    from app.models.user import User as UserModel
    user = db_session.query(UserModel).filter_by(email="pay@test.com").first()
    hotel = Hotel(name="H2", address="1 St", city="SF", country="US",
                  star_rating=3, is_active=True)
    db_session.add(hotel)
    db_session.flush()
    room = Room(hotel_id=hotel.id, room_number="102", room_type="double",
                price_per_night=100, max_guests=2)
    db_session.add(room)
    db_session.flush()
    res = Reservation(user_id=user.id, room_id=room.id,
                      check_in_date=date(2030,3,1), check_out_date=date(2030,3,3),
                      num_guests=1, total_price=200, status="pending")
    db_session.add(res)
    db_session.commit()

    r = client.post(f"/reservations/{res.id}/confirm", json={
        "amount": 150.00,  # wrong amount
        "payment_method": "card",
        "transaction_id": "txn_mismatch",
    }, headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "amount_mismatch"
    assert r.json()["detail"]["expected"] == 200.0


def test_confirm_payment_not_found(client, db_session):
    token = _login(client)
    r = client.post("/reservations/nonexistent-id/confirm", json={
        "amount": 100.00,
        "payment_method": "card",
        "transaction_id": "txn_404",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_confirm_payment_idempotent(client, db_session):
    """Same transaction_id submitted twice returns 200 with already_confirmed=True."""
    token = _login(client)
    from app.models.user import User as UserModel
    user = db_session.query(UserModel).filter_by(email="pay@test.com").first()
    hotel = Hotel(name="H3", address="1 St", city="SF", country="US",
                  star_rating=3, is_active=True)
    db_session.add(hotel)
    db_session.flush()
    room = Room(hotel_id=hotel.id, room_number="103", room_type="double",
                price_per_night=100, max_guests=2)
    db_session.add(room)
    db_session.flush()
    res = Reservation(user_id=user.id, room_id=room.id,
                      check_in_date=date(2030,4,1), check_out_date=date(2030,4,3),
                      num_guests=1, total_price=200, status="pending")
    db_session.add(res)
    db_session.commit()

    payload = {"amount": 200.00, "payment_method": "card", "transaction_id": "txn_idem"}
    headers = {"Authorization": f"Bearer {token}"}

    r1 = client.post(f"/reservations/{res.id}/confirm", json=payload, headers=headers)
    assert r1.status_code == 200
    assert r1.json()["already_confirmed"] is False

    r2 = client.post(f"/reservations/{res.id}/confirm", json=payload, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["already_confirmed"] is True


def test_confirm_payment_requires_auth(client, db_session):
    r = client.post("/reservations/any-id/confirm", json={
        "amount": 100.00,
        "payment_method": "card",
        "transaction_id": "txn_noauth",
    })
    assert r.status_code == 401


def test_confirm_payment_already_confirmed_different_charge(client, db_session):
    """A second charge on an already-confirmed reservation is rejected."""
    token = _login(client)
    from app.models.user import User as UserModel
    user = db_session.query(UserModel).filter_by(email="pay@test.com").first()
    hotel = Hotel(name="H4", address="1 St", city="SF", country="US",
                  star_rating=3, is_active=True)
    db_session.add(hotel)
    db_session.flush()
    room = Room(hotel_id=hotel.id, room_number="104", room_type="double",
                price_per_night=100, max_guests=2)
    db_session.add(room)
    db_session.flush()
    res = Reservation(user_id=user.id, room_id=room.id,
                      check_in_date=date(2030,5,1), check_out_date=date(2030,5,3),
                      num_guests=1, total_price=200, status="pending")
    db_session.add(res)
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    client.post(f"/reservations/{res.id}/confirm",
                json={"amount": 200.00, "payment_method": "card", "transaction_id": "txn_first"},
                headers=headers)

    r = client.post(f"/reservations/{res.id}/confirm",
                    json={"amount": 200.00, "payment_method": "card", "transaction_id": "txn_second"},
                    headers=headers)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "duplicate_payment"
