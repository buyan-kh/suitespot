from datetime import datetime, timedelta, timezone

import pytest

from app.models import Hotel, Payment, Reservation, Room, User
from app.security import issue_tokens
from app.services.availability import is_room_available
from app.services.booking_availability import place_hold
from app.services.pricing import stay_total

TODAY = datetime.now(timezone.utc).date()
D = lambda n: TODAY + timedelta(days=n)
IN, OUT = D(10), D(13)  # 3 nights x 100 = 300


def make_user(db, email):
    u = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(u)
    db.commit()
    return u


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


def make_room(db, price=100, number="101", max_guests=2, active=True, available=True, hotel=None):
    if hotel is None:
        hotel = Hotel(name=f"H{number}", address="1 Main", city="San Jose", country="US", is_active=active)
        db.add(hotel)
        db.flush()
    room = Room(hotel_id=hotel.id, room_number=number, price_per_night=price,
                max_guests=max_guests, is_available=available)
    db.add(room)
    db.commit()
    return room


@pytest.fixture
def user(db_session):
    return make_user(db_session, "me@x.com")


@pytest.fixture
def other(db_session):
    return make_user(db_session, "other@x.com")


@pytest.fixture
def room(db_session):
    return make_room(db_session)


@pytest.fixture
def booking(db_session, user, room):
    return place_hold(db_session, user_id=user.id, room_id=room.id, check_in=IN, check_out=OUT)


def patch(client, reservation_id, headers, **changes):
    body = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in changes.items()}
    return client.patch(f"/reservations/{reservation_id}", json=body, headers=headers)


def stored(db, reservation):
    db.expire_all()
    return db.get(Reservation, reservation.id)


# --- changing dates ---------------------------------------------------------

def test_change_dates_requotes_the_total(client, db_session, user, booking):
    response = patch(client, booking.id, auth(user), check_in=D(20), check_out=D(25))
    assert response.status_code == 200
    body = response.json()
    assert (body["check_in"], body["check_out"]) == (D(20).isoformat(), D(25).isoformat())
    assert body["total_price"] == 500.0 and body["changed"] is True
    assert body["price_change"] == {"old_total": 300.0, "new_total": 500.0, "difference": 200.0}
    row = stored(db_session, booking)
    assert row.check_in_date == D(20) and float(row.total_price) == 500.0


def test_a_shorter_stay_costs_less(client, user, booking):
    body = patch(client, booking.id, auth(user), check_out=D(12)).json()
    assert body["price_change"] == {"old_total": 300.0, "new_total": 200.0, "difference": -100.0}


def test_sending_only_one_date_keeps_the_other(client, db_session, user, booking):
    body = patch(client, booking.id, auth(user), check_out=D(15)).json()
    assert body["check_in"] == IN.isoformat() and body["check_out"] == D(15).isoformat()
    assert body["total_price"] == 500.0


def test_dates_can_overlap_the_reservations_own_old_dates(client, user, booking):
    """Extending or shifting a stay must not conflict with the stay itself."""
    assert patch(client, booking.id, auth(user), check_out=D(14)).status_code == 200
    assert patch(client, booking.id, auth(user), check_in=D(11), check_out=D(14)).status_code == 200
    assert patch(client, booking.id, auth(user), check_in=D(9), check_out=D(12)).status_code == 200


def test_the_new_total_matches_what_verify_and_charge_will_use(client, db_session, user, booking):
    patch(client, booking.id, auth(user), check_in=D(20), check_out=D(24))
    assert float(stored(db_session, booking).total_price) == float(stay_total(100, 4))


# --- changing the room ------------------------------------------------------

def test_change_room_uses_the_new_rooms_price(client, db_session, user, booking):
    pricier = make_room(db_session, price=150, number="202")
    body = patch(client, booking.id, auth(user), room_id=pricier.id).json()
    assert body["room_id"] == pricier.id
    assert body["price_change"] == {"old_total": 300.0, "new_total": 450.0, "difference": 150.0}
    assert stored(db_session, booking).room_id == pricier.id


def test_change_room_and_dates_together(client, db_session, user, booking):
    pricier = make_room(db_session, price=150, number="202")
    body = patch(client, booking.id, auth(user), room_id=pricier.id, check_in=D(30), check_out=D(32)).json()
    assert body["total_price"] == 300.0 and body["room_id"] == pricier.id


def test_party_size_can_change(client, user, booking):
    assert patch(client, booking.id, auth(user), num_guests=2).json()["num_guests"] == 2


# --- the room and dates must really be free ---------------------------------

def test_dates_taken_by_someone_else_are_refused_and_nothing_changes(client, db_session, user, other, room, booking):
    place_hold(db_session, user_id=other.id, room_id=room.id, check_in=D(20), check_out=D(23))
    response = patch(client, booking.id, auth(user), check_in=D(21), check_out=D(24))
    assert response.status_code == 409
    assert response.json()["detail"][0]["type"] == "room_unavailable"
    row = stored(db_session, booking)
    assert (row.check_in_date, row.check_out_date, row.status) == (IN, OUT, "pending")


def test_a_failed_move_does_not_free_the_old_dates_for_others(client, db_session, user, other, room, booking):
    place_hold(db_session, user_id=other.id, room_id=room.id, check_in=D(20), check_out=D(23))
    patch(client, booking.id, auth(user), check_in=D(21), check_out=D(24))  # refused
    assert is_room_available(db_session, room.id, IN, OUT) is False
    assert stored(db_session, booking).status == "pending"


def test_a_successful_move_frees_the_old_dates(client, db_session, user, other, room, booking):
    patch(client, booking.id, auth(user), check_in=D(20), check_out=D(23))
    assert is_room_available(db_session, room.id, IN, OUT) is True
    assert place_hold(db_session, user_id=other.id, room_id=room.id, check_in=IN, check_out=OUT).status == "pending"


def test_a_booked_room_cannot_be_moved_into(client, db_session, user, other, booking):
    taken = make_room(db_session, number="303")
    place_hold(db_session, user_id=other.id, room_id=taken.id, check_in=IN, check_out=OUT)
    assert patch(client, booking.id, auth(user), room_id=taken.id).status_code == 409


def test_back_to_back_with_another_guest_is_fine(client, db_session, user, other, room, booking):
    place_hold(db_session, user_id=other.id, room_id=room.id, check_in=D(13), check_out=D(15))
    assert patch(client, booking.id, auth(user), check_in=D(11), check_out=D(13)).status_code == 200


def test_room_in_a_deactivated_hotel_is_not_found(client, db_session, user, booking):
    closed = make_room(db_session, number="404", active=False)
    response = patch(client, booking.id, auth(user), room_id=closed.id)
    assert response.status_code == 404
    assert response.json()["detail"][0]["loc"] == ["body", "room_id"]


def test_room_marked_unavailable_is_refused(client, db_session, user, booking):
    off = make_room(db_session, number="505", available=False)
    assert patch(client, booking.id, auth(user), room_id=off.id).status_code == 409


def test_unknown_room_is_not_found(client, user, booking):
    assert patch(client, booking.id, auth(user), room_id="nope").status_code == 404


def test_too_many_guests_for_the_new_room(client, db_session, user, booking):
    small = make_room(db_session, number="606", max_guests=1)
    response = patch(client, booking.id, auth(user), room_id=small.id, num_guests=2)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "num_guests"]


# --- bad requests -----------------------------------------------------------

@pytest.mark.parametrize("changes,field", [
    (dict(check_out=D(10)), "check_out"),   # same day as check-in
    (dict(check_out=D(9)), "check_out"),    # before check-in
    (dict(check_in=D(13)), "check_out"),    # new check-in on/after the old check-out
    (dict(check_in=D(-3), check_out=D(-1)), "check_in"),
])
def test_invalid_dates_are_refused_naming_the_field(client, db_session, user, booking, changes, field):
    response = patch(client, booking.id, auth(user), **changes)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert stored(db_session, booking).check_in_date == IN


def test_an_empty_request_is_refused(client, user, booking):
    assert client.patch(f"/reservations/{booking.id}", json={}, headers=auth(user)).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("total_price", 1), ("status", "confirmed"), ("user_id", "someone"), ("id", "x"), ("special_requests", "hi"),
])
def test_fields_that_may_not_be_changed_are_refused(client, db_session, user, booking, field, value):
    response = client.patch(
        f"/reservations/{booking.id}", json={"num_guests": 2, field: value}, headers=auth(user)
    )
    assert response.status_code == 422
    row = stored(db_session, booking)
    assert row.num_guests == 1 and row.status == "pending" and float(row.total_price) == 300.0


@pytest.mark.parametrize("guests", [0, -1, 11, "two"])
def test_bad_guest_counts_are_refused(client, user, booking, guests):
    assert client.patch(f"/reservations/{booking.id}", json={"num_guests": guests}, headers=auth(user)).status_code == 422


# --- who and what can be changed --------------------------------------------

def test_requires_login(client, booking):
    assert client.patch(f"/reservations/{booking.id}", json={"num_guests": 2}).status_code == 401


def test_someone_elses_reservation_looks_like_it_does_not_exist(client, db_session, other, booking):
    response = patch(client, booking.id, auth(other), num_guests=2)
    assert response.status_code == 404
    assert stored(db_session, booking).num_guests == 1


def test_unknown_reservation(client, user):
    response = patch(client, "does-not-exist", auth(user), num_guests=2)
    assert response.status_code == 404
    assert response.json()["detail"][0]["loc"] == ["path", "reservation_id"]


@pytest.mark.parametrize("status", ["cancelled", "completed"])
def test_a_reservation_that_is_over_cannot_be_changed(client, db_session, user, booking, status):
    booking.status = status
    db_session.commit()
    response = patch(client, booking.id, auth(user), num_guests=2)
    assert response.status_code == 409
    assert response.json()["detail"][0]["type"] == "not_modifiable"


def test_a_stay_that_already_started_cannot_be_changed(client, db_session, user, room):
    started = Reservation(user_id=user.id, room_id=room.id, check_in_date=D(-1), check_out_date=D(2),
                          total_price=300, status="confirmed")
    db_session.add(started)
    db_session.commit()
    assert patch(client, started.id, auth(user), check_out=D(4)).status_code == 409


def test_a_stay_starting_today_can_still_be_changed(client, db_session, user, room):
    today_stay = Reservation(user_id=user.id, room_id=room.id, check_in_date=D(0), check_out_date=D(2),
                             total_price=200, status="confirmed")
    db_session.add(today_stay)
    db_session.commit()
    assert patch(client, today_stay.id, auth(user), check_out=D(3)).status_code == 200


def test_an_expired_unpaid_hold_cannot_be_changed(client, db_session, user, booking):
    booking.created_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    db_session.commit()
    assert patch(client, booking.id, auth(user), num_guests=2).status_code == 409
    assert stored(db_session, booking).status == "cancelled"


@pytest.mark.parametrize("status", ["pending", "confirmed"])
def test_the_status_is_unchanged_by_a_modification(client, db_session, user, booking, status):
    booking.status = status
    db_session.commit()
    assert patch(client, booking.id, auth(user), check_in=D(20), check_out=D(22)).json()["status"] == status
    assert stored(db_session, booking).status == status


def test_asking_for_what_is_already_there_changes_nothing(client, db_session, user, booking):
    body = patch(client, booking.id, auth(user), check_in=IN, check_out=OUT, num_guests=1).json()
    assert body["changed"] is False
    assert body["price_change"]["difference"] == 0.0


def test_payments_are_not_touched_money_belongs_to_3_x(client, db_session, user, booking):
    booking.status = "confirmed"
    payment = Payment(reservation_id=booking.id, amount=300, payment_method="card", status="succeeded")
    db_session.add(payment)
    db_session.commit()
    patch(client, booking.id, auth(user), check_in=D(20), check_out=D(25))
    db_session.expire_all()
    assert float(db_session.get(Payment, payment.id).amount) == 300.0
    assert db_session.get(Payment, payment.id).status == "succeeded"


def test_only_that_reservation_changes(client, db_session, user, room, booking):
    later = place_hold(db_session, user_id=user.id, room_id=room.id, check_in=D(40), check_out=D(42))
    patch(client, booking.id, auth(user), check_in=D(20), check_out=D(22))
    assert stored(db_session, later).check_in_date == D(40)


def test_get_and_put_are_not_allowed(client, user, booking):
    assert client.put(f"/reservations/{booking.id}", json={"num_guests": 2}, headers=auth(user)).status_code == 405


# --- how a modified reservation fits the rest of the app --------------------

def test_verify_total_follows_the_new_total(client, user, booking):
    patch(client, booking.id, auth(user), check_in=D(20), check_out=D(25))  # 5 nights = 500
    url = f"/reservations/{booking.id}/verify-total"
    assert client.post(url, json={"displayed_total": 500}, headers=auth(user)).status_code == 200
    stale = client.post(url, json={"displayed_total": 300}, headers=auth(user))
    assert stale.status_code == 409
    assert stale.json()["detail"][0]["ctx"]["expected_total"] == "500.00"


def test_a_charge_must_match_the_new_total_not_the_old_one(db_session, client, user, booking):
    from app.services.booking_confirmation import AmountMismatch, confirm_booking

    patch(client, booking.id, auth(user), check_in=D(20), check_out=D(25))
    db_session.expire_all()  # the PATCH ran in its own session, as every real request does
    with pytest.raises(AmountMismatch):
        confirm_booking(db_session, reservation_id=booking.id, amount=300,
                        payment_method="card", transaction_id="txn_old")
    result = confirm_booking(db_session, reservation_id=booking.id, amount=500,
                             payment_method="card", transaction_id="txn_new")
    assert result.reservation.status == "confirmed"


def test_my_reservations_shows_the_change(client, db_session, user, booking):
    pricier = make_room(db_session, price=150, number="707")
    patch(client, booking.id, auth(user), room_id=pricier.id, check_in=D(20), check_out=D(24))
    groups = client.get("/me/reservations", headers=auth(user)).json()
    card = next(c for key in ("upcoming", "past", "cancelled") for c in groups[key] if c["id"] == booking.id)
    assert card["check_in"] == D(20).isoformat() and card["check_out"] == D(24).isoformat()
    assert card["nights"] == 4 and card["total_price"] == 600.0 and card["room"]["id"] == pricier.id
