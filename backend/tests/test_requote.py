"""2.3.2 Price re-quote on change (US2.3)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Hotel, Payment, Reservation, Room, User
from app.requote.service import (
    InvalidChange,
    NotChangeable,
    RoomNotFound,
    RoomUnavailable,
    quote_change,
)
from app.security import issue_tokens
from app.services.booking_availability import place_hold

TODAY = datetime.now(timezone.utc).date()


def day(n):
    return TODAY + timedelta(days=n)


def make_user(db, email):
    user = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(user)
    db.commit()
    return user


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


def make_room(db, *, rate=100, max_guests=2, hotel=None, active=True, available=True, number="101"):
    if hotel is None:
        hotel = Hotel(name="H", address="1 Main", city="San Jose", country="US", is_active=active)
        db.add(hotel)
        db.flush()
    room = Room(hotel_id=hotel.id, room_number=number, price_per_night=rate,
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


def reserve(db, user, room, *, check_in=None, nights=3, status="confirmed", paid=None, total=None):
    check_in = check_in or day(10)
    reservation = Reservation(
        user_id=user.id, room_id=room.id, check_in_date=check_in,
        check_out_date=check_in + timedelta(days=nights),
        total_price=total if total is not None else Decimal(str(room.price_per_night)) * nights,
        status=status,
    )
    db.add(reservation)
    db.flush()
    if paid is not None:
        db.add(Payment(reservation_id=reservation.id, amount=paid, payment_method="card",
                       transaction_id=f"txn_{reservation.id}", status="succeeded"))
    db.commit()
    return reservation


@pytest.fixture
def booking(db_session, user, room):
    """Confirmed, paid: 3 nights from day 10 at $100 = $300."""
    return reserve(db_session, user, room, paid=300)


def quote(db, user, reservation, **change):
    return quote_change(db, reservation_id=reservation.id, user_id=user.id, **change)


def D(value):
    return Decimal(value)


# 1. Same room, new dates.

def test_longer_stay_costs_more(db_session, user, booking):
    q = quote(db_session, user, booking, check_out=day(15))
    assert q.proposed.nights == 5
    assert q.proposed.total == D("500.00")
    assert q.difference == D("200.00")
    assert q.balance_due == D("200.00")
    assert q.refund_due == D("0.00")
    assert q.changed is True


def test_shorter_stay_is_refunded(db_session, user, booking):
    q = quote(db_session, user, booking, check_out=day(11))
    assert q.proposed.total == D("100.00")
    assert q.difference == D("-200.00")
    assert q.balance_due == D("0.00")
    assert q.refund_due == D("200.00")


def test_shifting_by_a_day_does_not_overlap_itself(db_session, user, booking):
    q = quote(db_session, user, booking, check_in=day(11), check_out=day(14))
    assert q.proposed.total == D("300.00")
    assert q.difference == D("0.00")
    assert q.changed is True


def test_only_moving_check_in_keeps_check_out(db_session, user, booking):
    q = quote(db_session, user, booking, check_in=day(12))
    assert (q.proposed.check_in, q.proposed.check_out) == (day(12), day(13))
    assert q.refund_due == D("200.00")


# 2. A different room.

def test_a_pricier_room_reprices_the_whole_stay(db_session, user, booking, room):
    suite = make_room(db_session, rate=180, number="501")
    q = quote(db_session, user, booking, room_id=suite.id)
    assert q.proposed.room_id == suite.id
    assert q.proposed.total == D("540.00")
    assert q.balance_due == D("240.00")


def test_a_room_at_another_hotel(db_session, user, booking):
    elsewhere = make_room(db_session, rate=79.99, number="12")
    q = quote(db_session, user, booking, room_id=elsewhere.id, check_out=day(12))
    assert q.proposed.total == D("159.98")
    assert q.refund_due == D("140.02")


# 3. Today's rate.

def test_a_change_is_priced_at_the_current_rate(db_session, user, booking, room):
    room.price_per_night = 120
    db_session.commit()
    q = quote(db_session, user, booking, check_out=day(14))
    assert q.proposed.total == D("480.00")  # 4 nights at today's $120


def test_no_change_keeps_the_price_already_booked_even_if_the_rate_moved(db_session, user, booking, room):
    room.price_per_night = 120
    db_session.commit()
    q = quote(db_session, user, booking)
    assert q.changed is False
    assert q.proposed.total == D("300.00")
    assert q.difference == D("0.00")


def test_the_quote_equals_what_a_new_hold_would_store(db_session, user, other, booking):
    odd = make_room(db_session, rate=99.99, number="7")
    q = quote(db_session, user, booking, room_id=odd.id, check_in=day(20), check_out=day(27))
    fresh = place_hold(db_session, user_id=other.id, room_id=odd.id, check_in=day(40), check_out=day(47))
    assert q.proposed.total == Decimal(str(fresh.total_price)) == D("699.93")


# 4. Paid vs unpaid.

def test_an_unpaid_hold_owes_the_whole_new_total(db_session, user, room):
    hold = reserve(db_session, user, room, status="pending")
    q = quote(db_session, user, hold, check_out=day(14))
    assert q.amount_paid == D("0.00")
    assert q.balance_due == D("400.00")
    assert q.refund_due == D("0.00")


def test_failed_payments_do_not_count_as_paid(db_session, user, booking):
    db_session.add(Payment(reservation_id=booking.id, amount=999, payment_method="card",
                           transaction_id="txn_declined", status="failed"))
    db_session.commit()
    assert quote(db_session, user, booking).amount_paid == D("300.00")


# 5. No change.

def test_an_empty_request_is_no_change(db_session, user, booking):
    q = quote(db_session, user, booking)
    assert q.changed is False
    assert q.proposed == q.current
    assert q.balance_due == D("0.00") and q.refund_due == D("0.00")


def test_changing_only_the_guest_count_is_a_change_at_the_same_price(db_session, user, booking):
    q = quote(db_session, user, booking, num_guests=2)
    assert q.changed is True
    assert q.proposed.num_guests == 2
    assert q.difference == D("0.00")


# 6. Availability.

def test_another_guests_booking_blocks_the_new_dates(db_session, user, other, room, booking):
    reserve(db_session, other, room, check_in=day(13), nights=2)
    with pytest.raises(RoomUnavailable):
        quote(db_session, user, booking, check_out=day(14))


def test_back_to_back_is_fine(db_session, user, other, room, booking):
    reserve(db_session, other, room, check_in=day(14), nights=2)
    assert quote(db_session, user, booking, check_out=day(14)).proposed.nights == 4


def test_a_cancelled_booking_does_not_block(db_session, user, other, room, booking):
    reserve(db_session, other, room, check_in=day(13), nights=2, status="cancelled")
    assert quote(db_session, user, booking, check_out=day(15)).proposed.nights == 5


def test_a_pending_hold_by_someone_else_blocks(db_session, user, other, room, booking):
    reserve(db_session, other, room, check_in=day(13), nights=2, status="pending")
    with pytest.raises(RoomUnavailable):
        quote(db_session, user, booking, check_out=day(15))


def test_my_own_other_booking_still_blocks(db_session, user, room, booking):
    reserve(db_session, user, room, check_in=day(14), nights=2)
    with pytest.raises(RoomUnavailable):
        quote(db_session, user, booking, check_out=day(15))


def test_moving_to_a_room_that_is_taken(db_session, user, other, booking):
    taken = make_room(db_session, number="202")
    reserve(db_session, other, taken, check_in=day(9), nights=2)
    with pytest.raises(RoomUnavailable):
        quote(db_session, user, booking, room_id=taken.id)


# 7. Validation.

@pytest.mark.parametrize("change,field", [
    ({"check_out": day(10)}, "check_out"),                    # same day as check-in
    ({"check_out": day(9)}, "check_out"),                     # before check-in
    ({"check_in": day(14)}, "check_out"),                     # moved past the old check-out
    ({"check_in": day(-1), "check_out": day(2)}, "check_in"),  # in the past
    ({"num_guests": 3}, "num_guests"),                         # room sleeps 2
    ({"num_guests": 0}, "num_guests"),
])
def test_invalid_changes_name_the_field(db_session, user, booking, change, field):
    with pytest.raises(InvalidChange) as error:
        quote(db_session, user, booking, **change)
    assert error.value.field == field


def test_too_many_guests_for_the_new_room(db_session, user, booking):
    small = make_room(db_session, max_guests=1, number="1")
    with pytest.raises(InvalidChange) as error:
        quote(db_session, user, booking, room_id=small.id, num_guests=2)
    assert error.value.field == "num_guests"


@pytest.mark.parametrize("kind", ["unknown", "inactive_hotel", "unavailable_room"])
def test_a_room_that_cannot_be_booked_is_not_found(db_session, user, booking, kind):
    if kind == "unknown":
        room_id = "no-such-room"
    elif kind == "inactive_hotel":
        room_id = make_room(db_session, active=False, number="9").id
    else:
        room_id = make_room(db_session, available=False, number="9").id
    with pytest.raises(RoomNotFound):
        quote(db_session, user, booking, room_id=room_id)


# 8. Status and timing.

@pytest.mark.parametrize("status", ["cancelled", "completed"])
def test_closed_reservations_cannot_be_changed(db_session, user, room, status):
    r = reserve(db_session, user, room, status=status)
    with pytest.raises(NotChangeable):
        quote(db_session, user, r, check_out=day(15))


def test_a_stay_that_has_started_cannot_be_changed(db_session, user, room):
    r = reserve(db_session, user, room, check_in=day(-1))
    with pytest.raises(NotChangeable):
        quote(db_session, user, r, check_out=day(5))


def test_can_still_change_on_the_check_in_day(db_session, user, room):
    r = reserve(db_session, user, room, check_in=TODAY)
    assert quote(db_session, user, r, check_out=day(4)).proposed.nights == 4


def test_the_timing_rule_uses_the_today_argument(db_session, user, booking):
    with pytest.raises(NotChangeable):
        quote_change(db_session, reservation_id=booking.id, user_id=user.id,
                     check_out=day(15), today=day(11))


# 9. Access, through the endpoint.

def post(client, user, reservation_id, body):
    headers = auth(user) if user else {}
    return client.post(f"/reservations/{reservation_id}/quote-change", json=body, headers=headers)


def test_endpoint_returns_the_quote(client, user, booking):
    response = post(client, user, booking.id, {"check_out": str(day(15))})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "current": {"room_id": booking.room_id, "check_in": str(day(10)), "check_out": str(day(13)),
                    "nights": 3, "num_guests": 1, "total": 300.0},
        "proposed": {"room_id": booking.room_id, "check_in": str(day(10)), "check_out": str(day(15)),
                     "nights": 5, "num_guests": 1, "total": 500.0},
        "difference": 200.0,
        "amount_paid": 300.0,
        "balance_due": 200.0,
        "refund_due": 0.0,
        "changed": True,
    }


def test_endpoint_requires_login(client, booking):
    assert post(client, None, booking.id, {}).status_code == 401


def test_someone_elses_reservation_is_404(client, other, booking):
    response = post(client, other, booking.id, {"check_out": str(day(15))})
    assert response.status_code == 404
    assert response.json()["detail"][0] == {
        "type": "not_found", "loc": ["path", "reservation_id"], "msg": "Reservation not found.",
    }


def test_unknown_reservation_is_404(client, user):
    assert post(client, user, "nope", {}).status_code == 404


@pytest.mark.parametrize("body,code,kind,field", [
    ({"check_out": str(day(9))}, 422, "invalid_change", "check_out"),
    ({"room_id": "nope"}, 404, "not_found", "room_id"),
])
def test_endpoint_errors_name_the_field(client, user, booking, body, code, kind, field):
    response = post(client, user, booking.id, body)
    assert response.status_code == code
    error = response.json()["detail"][0]
    assert (error["type"], error["loc"]) == (kind, ["body", field])


def test_endpoint_conflicts(client, db_session, user, other, room, booking):
    reserve(db_session, other, room, check_in=day(13), nights=2)
    response = post(client, user, booking.id, {"check_out": str(day(14))})
    assert response.status_code == 409
    assert response.json()["detail"][0]["type"] == "room_unavailable"


def test_endpoint_rejects_a_closed_reservation(client, db_session, user, room):
    r = reserve(db_session, user, room, status="cancelled")
    response = post(client, user, r.id, {})
    assert response.status_code == 409
    assert response.json()["detail"][0]["type"] == "not_changeable"


@pytest.mark.parametrize("body", [{"num_guests": 0}, {"num_guests": 11}, {"check_in": "not-a-date"}])
def test_malformed_bodies_are_422(client, user, booking, body):
    assert post(client, user, booking.id, body).status_code == 422


def test_get_is_not_allowed(client, user, booking):
    assert client.get(f"/reservations/{booking.id}/quote-change", headers=auth(user)).status_code == 405


# 10. Read-only.

def test_quoting_changes_nothing(client, db_session, user, room, booking):
    other_room = make_room(db_session, rate=250, number="9")
    before = (booking.room_id, booking.check_in_date, booking.check_out_date,
              booking.num_guests, booking.total_price, booking.status)
    post(client, user, booking.id, {"room_id": other_room.id, "check_out": str(day(16)), "num_guests": 2})

    db_session.expire_all()
    after = db_session.get(Reservation, booking.id)
    assert (after.room_id, after.check_in_date, after.check_out_date,
            after.num_guests, after.total_price, after.status) == before
    assert db_session.query(Payment).count() == 1
