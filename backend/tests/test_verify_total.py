from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Hotel, Reservation, Room, User
from app.security import issue_tokens
from app.services.booking_availability import place_hold
from app.services.pricing import TotalMismatch, money, stay_total, verify_displayed_total

TODAY = datetime.now(timezone.utc).date()
IN, OUT = TODAY + timedelta(days=10), TODAY + timedelta(days=13)  # 3 nights x 100 = 300


def make_user(db, email):
    u = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(u)
    db.commit()
    return u


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


@pytest.fixture
def user(db_session):
    return make_user(db_session, "me@x.com")


@pytest.fixture
def other(db_session):
    return make_user(db_session, "other@x.com")


def make_room(db, price=100, number="101"):
    hotel = Hotel(name=f"H{number}", address="1 Main", city="San Jose", country="US")
    db.add(hotel)
    db.flush()
    room = Room(hotel_id=hotel.id, room_number=number, price_per_night=price, max_guests=2)
    db.add(room)
    db.commit()
    return room


@pytest.fixture
def room(db_session):
    return make_room(db_session)


@pytest.fixture
def hold(db_session, user, room):
    return place_hold(db_session, user_id=user.id, room_id=room.id, check_in=IN, check_out=OUT)


def verify(client, reservation_id, headers, displayed_total):
    return client.post(
        f"/reservations/{reservation_id}/verify-total",
        json={"displayed_total": displayed_total}, headers=headers,
    )


# --- the endpoint -----------------------------------------------------------

def test_matching_total_is_confirmed(client, user, hold):
    response = verify(client, hold.id, auth(user), 300)
    assert response.status_code == 200
    assert response.json() == {"matches": True, "total": 300.0}


@pytest.mark.parametrize("shown", [300, 300.0, "300", "300.00", "300.0"])
def test_every_way_of_writing_the_same_total_matches(client, user, hold, shown):
    assert verify(client, hold.id, auth(user), shown).status_code == 200


@pytest.mark.parametrize("shown", [299.99, 300.01, 0, 100, 3000, "299.99"])
def test_a_different_total_is_refused_with_the_real_one(client, user, hold, shown):
    response = verify(client, hold.id, auth(user), shown)
    assert response.status_code == 409
    error = response.json()["detail"][0]
    assert error["type"] == "total_mismatch"
    assert error["loc"] == ["body", "displayed_total"]
    assert error["ctx"]["expected_total"] == "300.00"


@pytest.mark.parametrize("shown", [-1, -0.01, "NaN", "Infinity", "-Infinity", "abc", "", None, [], {}, 300.001])
def test_unusable_amounts_are_rejected_before_any_comparison(client, user, hold, shown):
    response = verify(client, hold.id, auth(user), shown)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "displayed_total"]


def test_missing_total_is_rejected(client, user, hold):
    response = client.post(f"/reservations/{hold.id}/verify-total", json={}, headers=auth(user))
    assert response.status_code == 422


def test_requires_login(client, hold):
    response = client.post(f"/reservations/{hold.id}/verify-total", json={"displayed_total": 300})
    assert response.status_code == 401


def test_someone_elses_reservation_looks_like_it_does_not_exist(client, other, hold):
    response = verify(client, hold.id, auth(other), 300)
    assert response.status_code == 404
    assert "ctx" not in response.json()["detail"][0]  # no leaked total


def test_unknown_reservation(client, user):
    response = verify(client, "does-not-exist", auth(user), 300)
    assert response.status_code == 404
    assert response.json()["detail"][0]["loc"] == ["path", "reservation_id"]


@pytest.mark.parametrize("status", ["cancelled", "completed"])
def test_a_reservation_that_cannot_be_paid_is_refused(client, db_session, user, hold, status):
    hold.status = status
    db_session.commit()
    response = verify(client, hold.id, auth(user), 300)
    assert response.status_code == 409
    assert response.json()["detail"][0]["type"] == "not_payable"


def test_a_confirmed_reservation_can_still_be_checked(client, db_session, user, hold):
    hold.status = "confirmed"
    db_session.commit()
    assert verify(client, hold.id, auth(user), 300).status_code == 200


def test_checking_changes_nothing(client, db_session, user, hold):
    verify(client, hold.id, auth(user), 12345)
    verify(client, hold.id, auth(user), 300)
    db_session.expire_all()
    stored = db_session.get(Reservation, hold.id)
    assert stored.status == "pending" and float(stored.total_price) == 300.0


def test_get_is_not_allowed(client, user, hold):
    assert client.get(f"/reservations/{hold.id}/verify-total", headers=auth(user)).status_code == 405


def test_response_has_nothing_extra(client, user, hold):
    assert set(verify(client, hold.id, auth(user), 300).json()) == {"matches", "total"}


# --- one source of truth for the total --------------------------------------

@pytest.mark.parametrize("rate,nights,expected", [
    (100, 3, "300.00"),
    (99.99, 3, "299.97"),
    (19.99, 7, "139.93"),     # float math would give 139.92999999999998
    (0.10, 3, "0.30"),
    (1234.56, 1, "1234.56"),
])
def test_stay_total_is_exact_to_the_cent(rate, nights, expected):
    assert stay_total(rate, nights) == Decimal(expected)


def test_money_ignores_float_noise():
    assert money(0.1 + 0.2) == Decimal("0.30")


@pytest.mark.parametrize("rate,nights", [(100, 3), (99.99, 3), (19.99, 7), (250.5, 2)])
def test_the_hold_stores_exactly_the_total_the_screen_can_verify(client, db_session, user, rate, nights):
    room = make_room(db_session, price=rate, number=f"r{rate}")
    reservation = place_hold(
        db_session, user_id=user.id, room_id=room.id,
        check_in=IN, check_out=IN + timedelta(days=nights),
    )
    total = stay_total(rate, nights)
    assert money(reservation.total_price) == total
    assert verify(client, reservation.id, auth(user), str(total)).status_code == 200
    assert verify(client, reservation.id, auth(user), str(total + Decimal("0.01"))).status_code == 409


def test_verify_displayed_total_unit(hold):
    assert verify_displayed_total(hold, "300.00") == Decimal("300.00")
    with pytest.raises(TotalMismatch) as error:
        verify_displayed_total(hold, 299)
    assert error.value.expected == Decimal("300.00") and error.value.displayed == Decimal("299.00")

def test_the_hold_uses_the_shared_pricing_function(db_session, user, room, monkeypatch):
    """Fees added to stay_total() must flow into the hold, the check and the charge."""
    from app.services import booking_availability

    monkeypatch.setattr(booking_availability, "stay_total", lambda rate, nights: Decimal("123.45"))
    reservation = place_hold(db_session, user_id=user.id, room_id=room.id, check_in=IN, check_out=OUT)
    assert money(reservation.total_price) == Decimal("123.45")
