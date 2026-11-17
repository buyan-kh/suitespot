"""3.2.3 Price breakdown: testing and debugging (US3.2).

test_verify_total.py (3.2.2) checks the endpoint on its own. These check the
promise US3.2 makes end to end: the total the guest is shown, the total
verify-total accepts and the amount a charge is accepted for are one number,
whatever the stay.
"""
import calendar
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Hotel, Room, User
from app.security import issue_tokens
from app.services.booking_availability import HOLD_MINUTES, place_hold, release_expired_holds
from app.services.booking_confirmation import AmountMismatch, confirm_booking
from app.services.pricing import stay_total

TODAY = datetime.now(timezone.utc).date()


def next_leap_feb_28() -> date:
    """Feb 28 of the next leap year that is still in the future."""
    year = TODAY.year
    while True:
        if calendar.isleap(year) and date(year, 2, 28) > TODAY:
            return date(year, 2, 28)
        year += 1


LEAP_IN = next_leap_feb_28()
LEAP_OUT = LEAP_IN + timedelta(days=2)  # Feb 28 -> Mar 1 is 2 nights: Feb 28 and Feb 29
YEAR_END_IN = date(TODAY.year if date(TODAY.year, 12, 30) > TODAY else TODAY.year + 1, 12, 30)


def make_user(db, email):
    user = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(user)
    db.commit()
    return user


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


def make_room(db, rate):
    hotel = Hotel(name="H", address="1 Main", city="San Jose", country="US")
    db.add(hotel)
    db.flush()
    room = Room(hotel_id=hotel.id, room_number="101", price_per_night=rate, max_guests=2)
    db.add(room)
    db.commit()
    return room


@pytest.fixture
def user(db_session):
    return make_user(db_session, "me@x.com")


def verify(client, user, reservation_id, shown):
    return client.post(
        f"/reservations/{reservation_id}/verify-total",
        json={"displayed_total": str(shown)}, headers=auth(user),
    )


def pay(db, reservation_id, amount, txn="txn_1"):
    db.expire_all()  # a real charge runs in a fresh session
    return confirm_booking(
        db, reservation_id=reservation_id, amount=amount,
        payment_method="card", transaction_id=txn,
    )


# 1. Shown total == verified total == charged total, for different stays.

STAYS = {
    "1 night": (TODAY + timedelta(days=5), TODAY + timedelta(days=6)),
    "7 nights": (TODAY + timedelta(days=5), TODAY + timedelta(days=12)),
    "30 nights": (TODAY + timedelta(days=5), TODAY + timedelta(days=35)),
    "across a year end": (YEAR_END_IN, YEAR_END_IN + timedelta(days=3)),  # Dec 30 -> Jan 2
    "leap day": (LEAP_IN, LEAP_OUT),
}


@pytest.mark.parametrize("rate", [100, 99.99, 19.99])
@pytest.mark.parametrize("stay", STAYS, ids=list(STAYS))
def test_the_verified_total_is_exactly_what_a_charge_is_accepted_for(
    client, db_session, user, rate, stay
):
    check_in, check_out = STAYS[stay]
    room = make_room(db_session, rate)
    hold = place_hold(db_session, user_id=user.id, room_id=room.id,
                      check_in=check_in, check_out=check_out)
    nights = (check_out - check_in).days
    total = Decimal(str(hold.total_price))

    assert total == stay_total(rate, nights)
    response = verify(client, user, hold.id, total)
    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()["total"])) == total

    confirmation = pay(db_session, hold.id, total)
    assert confirmation.reservation.status == "confirmed"
    assert Decimal(str(confirmation.payment.amount)) == total


def test_leap_day_stay_counts_two_nights(db_session, user):
    room = make_room(db_session, 100)
    hold = place_hold(db_session, user_id=user.id, room_id=room.id,
                      check_in=LEAP_IN, check_out=LEAP_OUT)
    assert Decimal(str(hold.total_price)) == Decimal("200.00")


def test_a_total_verify_refuses_is_also_refused_as_a_charge(client, db_session, user):
    room = make_room(db_session, 99.99)
    hold = place_hold(db_session, user_id=user.id, room_id=room.id,
                      check_in=TODAY + timedelta(days=5), check_out=TODAY + timedelta(days=8))
    wrong = Decimal(str(hold.total_price)) - Decimal("0.01")

    response = verify(client, user, hold.id, wrong)
    assert response.status_code == 409
    expected = Decimal(response.json()["detail"][0]["ctx"]["expected_total"])
    assert expected == Decimal("299.97")

    with pytest.raises(AmountMismatch):
        pay(db_session, hold.id, wrong)
    # The number verify-total sends back is the one a charge accepts.
    assert pay(db_session, hold.id, expected).reservation.status == "confirmed"


# 2. The rate changes after the hold: the guest pays what they were quoted.

def test_rate_change_after_the_hold_keeps_the_quoted_total(client, db_session, user):
    room = make_room(db_session, 100)
    hold = place_hold(db_session, user_id=user.id, room_id=room.id,
                      check_in=TODAY + timedelta(days=5), check_out=TODAY + timedelta(days=8))
    room.price_per_night = 150
    db_session.commit()

    assert verify(client, user, hold.id, "300.00").status_code == 200
    assert verify(client, user, hold.id, "450.00").status_code == 409
    assert pay(db_session, hold.id, "300.00").reservation.status == "confirmed"


# 3. Expired holds.

def test_an_expired_hold_not_yet_released_still_verifies_like_a_late_payment(
    client, db_session, user
):
    # confirm_booking accepts a late payment until the hold is released
    # (test_booking_confirmation.py), so verify-total must agree.
    room = make_room(db_session, 100)
    long_ago = datetime.now(timezone.utc) - timedelta(minutes=HOLD_MINUTES + 5)
    hold = place_hold(db_session, user_id=user.id, room_id=room.id,
                      check_in=TODAY + timedelta(days=5), check_out=TODAY + timedelta(days=6),
                      now=long_ago)
    hold.created_at = long_ago
    db_session.commit()

    assert verify(client, user, hold.id, "100.00").status_code == 200
    assert pay(db_session, hold.id, "100.00").reservation.status == "confirmed"


def test_a_released_hold_is_not_payable(client, db_session, user):
    room = make_room(db_session, 100)
    hold = place_hold(db_session, user_id=user.id, room_id=room.id,
                      check_in=TODAY + timedelta(days=5), check_out=TODAY + timedelta(days=6))
    later = datetime.now(timezone.utc) + timedelta(minutes=HOLD_MINUTES + 1)
    assert release_expired_holds(db_session, now=later) == 1

    response = verify(client, user, hold.id, "100.00")
    assert response.status_code == 409
    assert response.json()["detail"][0]["type"] == "not_payable"


# 4. Very large amounts are a clean 409 or 422, never a 500.

@pytest.mark.parametrize("shown,code", [
    ("9999999999.99", 409),   # 12 digits: allowed, just wrong
    ("99999999999.99", 422),  # 13 digits: over the schema limit
    ("1e20", 422),
])
def test_huge_amounts_are_handled(client, db_session, user, shown, code):
    room = make_room(db_session, 100)
    hold = place_hold(db_session, user_id=user.id, room_id=room.id,
                      check_in=TODAY + timedelta(days=5), check_out=TODAY + timedelta(days=6))
    assert verify(client, user, hold.id, shown).status_code == code


# 5. The backend total matches what PriceBreakdown.tsx works out.

def frontend_stay_total(rate: float, nights: int) -> Decimal:
    """PriceBreakdown.tsx: toCents(rate) * nights, with JS Math.round."""
    cents = math.floor(rate * 100 + 0.5) * nights
    return Decimal(cents) / 100


@pytest.mark.parametrize("rate,nights", [
    (19.99, 7), (99.99, 3), (250.5, 2), (0.01, 365), (0.1, 3), (189, 3), (1234.56, 30),
])
def test_backend_and_frontend_agree_to_the_cent(rate, nights):
    assert stay_total(rate, nights) == frontend_stay_total(rate, nights)


# 6. Fees and taxes (3.4.1) are not part of the total yet.

@pytest.mark.xfail(strict=True, reason="Fees and taxes arrive with 3.4.1 (Vincent).")
def test_the_total_includes_fees_and_taxes(db_session, user):
    room = make_room(db_session, 100)
    hold = place_hold(db_session, user_id=user.id, room_id=room.id,
                      check_in=TODAY + timedelta(days=5), check_out=TODAY + timedelta(days=8))
    assert Decimal(str(hold.total_price)) > Decimal("300.00")
