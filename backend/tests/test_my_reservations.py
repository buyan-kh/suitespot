"""4.1.1 My reservations endpoint: upcoming + past (US4.1)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.images.models import HotelImage
from app.models import Hotel, Payment, Reservation, Room, User
from app.my_reservations.service import my_reservations
from app.security import issue_tokens
from app.services.booking_availability import HOLD_MINUTES
from app.services.booking_confirmation import confirm_booking
from tests.conftest import engine

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TODAY = NOW.date()
BASE = "http://test/"


def day(n):
    return TODAY + timedelta(days=n)


def make_user(db, email):
    user = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(user)
    db.commit()
    return user


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


@pytest.fixture
def user(db_session):
    return make_user(db_session, "me@x.com")


@pytest.fixture
def other(db_session):
    return make_user(db_session, "other@x.com")


def make_room(db, *, hotel_name="H", city="San Jose", active=True, number="101", rate=100):
    hotel = Hotel(name=hotel_name, address="1 Main", city=city, country="US", is_active=active)
    db.add(hotel)
    db.flush()
    room = Room(hotel_id=hotel.id, room_number=number, room_type="double",
                price_per_night=rate, max_guests=2)
    db.add(room)
    db.commit()
    return room


@pytest.fixture
def room(db_session):
    return make_room(db_session)


def reserve(db, user, room, *, status="confirmed", check_in=None, check_out=None,
            total=300, created_at=None, paid=None):
    check_in = check_in or day(10)
    check_out = check_out or check_in + timedelta(days=3)
    reservation = Reservation(
        user_id=user.id, room_id=room.id, check_in_date=check_in, check_out_date=check_out,
        total_price=total, status=status,
    )
    if created_at is not None:
        reservation.created_at = created_at
    db.add(reservation)
    db.flush()
    if paid is not None:
        db.add(Payment(reservation_id=reservation.id, amount=paid, payment_method="card",
                       transaction_id=f"txn_{reservation.id}", status="succeeded"))
    db.commit()
    return reservation


def grouped(db, user, now=NOW):
    db.expire_all()
    return my_reservations(db, user_id=user.id, base_url=BASE, now=now)


def ids(cards):
    return [card["id"] for card in cards]


def where(db, user, reservation, now=NOW):
    """Which group a reservation landed in, or None if hidden."""
    g = grouped(db, user, now)
    for name in ("upcoming", "past", "cancelled"):
        for card in getattr(g, name):
            if card["id"] == reservation.id:
                return name, card["status"]
    return None


# 1-2. Access.

def test_requires_login(client):
    assert client.get("/me/reservations").status_code == 401


@pytest.mark.parametrize("header", ["Bearer garbage", "Bearer ", "nonsense"])
def test_bad_token_is_rejected(client, header):
    assert client.get("/me/reservations", headers={"Authorization": header}).status_code == 401


def test_only_my_reservations_are_listed(client, db_session, user, other, room):
    mine = reserve(db_session, user, room, paid=300)
    reserve(db_session, other, room, check_in=day(20), paid=300)
    body = client.get("/me/reservations", headers=auth(user)).json()
    assert ids(body["upcoming"]) == [mine.id]
    assert body["past"] == [] and body["cancelled"] == []


# 3. Every grouping rule.

def test_live_hold_is_upcoming_awaiting_payment(db_session, user, room):
    r = reserve(db_session, user, room, status="pending", created_at=NOW - timedelta(minutes=5))
    assert where(db_session, user, r) == ("upcoming", "awaiting_payment")


def test_expired_hold_is_hidden(db_session, user, room):
    r = reserve(db_session, user, room, status="pending",
                created_at=NOW - timedelta(minutes=HOLD_MINUTES + 1))
    assert where(db_session, user, r) is None


def test_confirmed_future_stay_is_upcoming(db_session, user, room):
    r = reserve(db_session, user, room, paid=300)
    assert where(db_session, user, r) == ("upcoming", "confirmed")


def test_stay_in_progress_is_still_upcoming(db_session, user, room):
    r = reserve(db_session, user, room, check_in=day(-1), check_out=day(2), paid=300)
    assert where(db_session, user, r) == ("upcoming", "confirmed")


@pytest.mark.parametrize("check_out", [0, -1, -30])
def test_confirmed_stay_that_has_ended_is_past_completed(db_session, user, room, check_out):
    r = reserve(db_session, user, room, check_in=day(check_out - 3), check_out=day(check_out), paid=300)
    assert where(db_session, user, r) == ("past", "completed")


def test_completed_stay_is_past(db_session, user, room):
    r = reserve(db_session, user, room, status="completed",
                check_in=day(-5), check_out=day(-2), paid=300)
    assert where(db_session, user, r) == ("past", "completed")


def test_cancelled_after_paying_is_in_cancelled(db_session, user, room):
    r = reserve(db_session, user, room, status="cancelled", paid=300)
    assert where(db_session, user, r) == ("cancelled", "cancelled")


def test_cancelled_without_ever_paying_is_hidden(db_session, user, room):
    r = reserve(db_session, user, room, status="cancelled")
    assert where(db_session, user, r) is None


def test_a_failed_payment_does_not_count_as_paid(db_session, user, room):
    r = reserve(db_session, user, room, status="cancelled")
    db_session.add(Payment(reservation_id=r.id, amount=300, payment_method="card",
                           transaction_id="txn_failed", status="failed"))
    db_session.commit()
    assert where(db_session, user, r) is None


# 4. Hold expiry boundary.

def test_hold_expires_at_is_created_plus_hold_minutes(db_session, user, room):
    created = NOW - timedelta(minutes=1)
    r = reserve(db_session, user, room, status="pending", created_at=created)
    expires = created + timedelta(minutes=HOLD_MINUTES)

    card = grouped(db_session, user).upcoming[0]
    assert card["hold_expires_at"] == expires
    assert where(db_session, user, r, now=expires - timedelta(seconds=1)) == ("upcoming", "awaiting_payment")
    assert where(db_session, user, r, now=expires) is None


def test_hold_expires_at_is_only_set_while_awaiting_payment(db_session, user, room):
    reserve(db_session, user, room, paid=300)
    assert grouped(db_session, user).upcoming[0]["hold_expires_at"] is None


# 5. Sort order.

def test_upcoming_is_soonest_first(db_session, user, room):
    later = reserve(db_session, user, room, check_in=day(30), paid=300)
    sooner = reserve(db_session, user, room, check_in=day(5), paid=300)
    middle = reserve(db_session, user, room, check_in=day(15), paid=300)
    assert ids(grouped(db_session, user).upcoming) == [sooner.id, middle.id, later.id]


def test_past_is_most_recent_first(db_session, user, room):
    old = reserve(db_session, user, room, check_in=day(-40), check_out=day(-37), paid=300)
    recent = reserve(db_session, user, room, check_in=day(-5), check_out=day(-2), paid=300)
    assert ids(grouped(db_session, user).past) == [recent.id, old.id]


def test_cancelled_is_latest_cancellation_first(db_session, user, room):
    first = reserve(db_session, user, room, status="cancelled", paid=300)
    second = reserve(db_session, user, room, status="cancelled", check_in=day(40), paid=300)
    first.updated_at = NOW - timedelta(days=2)
    second.updated_at = NOW - timedelta(days=1)
    db_session.commit()
    assert ids(grouped(db_session, user).cancelled) == [second.id, first.id]


# 6. Card contents.

def test_card_fields(db_session, user):
    room = make_room(db_session, hotel_name="Bay Suites", city="Oakland", number="204", rate=99.99)
    r = reserve(db_session, user, room, check_in=day(3), check_out=day(6), total="299.97", paid="299.97")
    card = grouped(db_session, user).upcoming[0]
    assert card == {
        "id": r.id,
        "status": "confirmed",
        "hotel": {"id": room.hotel_id, "name": "Bay Suites", "city": "Oakland", "image": None},
        "room": {"id": room.id, "room_type": "double", "room_number": "204"},
        "check_in": day(3),
        "check_out": day(6),
        "nights": 3,
        "num_guests": 1,
        "total_price": 299.97,
        "amount_paid": 299.97,
        "hold_expires_at": None,
    }


def test_unpaid_hold_shows_nothing_paid_yet(db_session, user, room):
    reserve(db_session, user, room, status="pending", created_at=NOW)
    assert grouped(db_session, user).upcoming[0]["amount_paid"] == 0.0


def test_amount_paid_counts_only_succeeded_payments(db_session, user, room):
    r = reserve(db_session, user, room, paid=300)
    db_session.add(Payment(reservation_id=r.id, amount=300, payment_method="card",
                           transaction_id="txn_declined", status="failed"))
    db_session.commit()
    assert grouped(db_session, user).upcoming[0]["amount_paid"] == 300.0


def test_card_uses_the_hotels_cover_photo(db_session, user, room):
    db_session.add_all([
        HotelImage(hotel_id=room.hotel_id, room_type="double", position=0,
                   file="h/room.jpg", alt="Room", width=4000, height=3000),
        HotelImage(hotel_id=room.hotel_id, room_type=None, position=1,
                   file="h/lobby.jpg", alt="Lobby", width=4000, height=3000),
        HotelImage(hotel_id=room.hotel_id, room_type=None, position=0,
                   file="h/front.jpg", alt="Front", width=4000, height=3000),
    ])
    db_session.commit()
    reserve(db_session, user, room, paid=300)

    image = grouped(db_session, user).upcoming[0]["hotel"]["image"]
    assert image["alt"] == "Front"  # hotel-wide photos first, then by position
    assert image["url"].startswith("http://test/media/")
    assert set(image["sizes"]) == {"thumb", "medium", "large"}


# 7. Counts and the empty state.

def test_counts_match_the_lists(client, db_session, user, room):
    reserve(db_session, user, room, check_in=day(5), paid=300)
    reserve(db_session, user, room, check_in=day(20), paid=300)
    reserve(db_session, user, room, check_in=day(-10), check_out=day(-7), paid=300)
    reserve(db_session, user, room, status="cancelled", check_in=day(40), paid=300)
    reserve(db_session, user, room, status="cancelled", check_in=day(50))  # hidden

    body = client.get("/me/reservations", headers=auth(user)).json()
    assert body["counts"] == {"upcoming": 2, "past": 1, "cancelled": 1}
    for name, count in body["counts"].items():
        assert len(body[name]) == count


def test_no_bookings_is_three_empty_lists(client, user):
    response = client.get("/me/reservations", headers=auth(user))
    assert response.status_code == 200
    assert response.json() == {
        "upcoming": [], "past": [], "cancelled": [],
        "counts": {"upcoming": 0, "past": 0, "cancelled": 0},
    }


# 8. Inactive hotels.

def test_a_booking_at_an_inactive_hotel_still_appears(db_session, user):
    room = make_room(db_session, active=False)
    r = reserve(db_session, user, room, check_in=day(-10), check_out=day(-7), paid=300)
    assert where(db_session, user, r) == ("past", "completed")


# 9. End to end through the real endpoints.

def test_book_pay_cancel_moves_the_card(client, db_session, user, room):
    body = {"room_id": room.id, "check_in": str(day(10)), "check_out": str(day(13))}
    hold = client.post("/reservations", json=body, headers=auth(user)).json()

    listed = client.get("/me/reservations", headers=auth(user)).json()
    assert [(c["id"], c["status"]) for c in listed["upcoming"]] == [(hold["id"], "awaiting_payment")]

    db_session.expire_all()
    confirm_booking(db_session, reservation_id=hold["id"], amount=hold["total_price"],
                    payment_method="card", transaction_id="txn_e2e")
    listed = client.get("/me/reservations", headers=auth(user)).json()
    assert [(c["id"], c["status"]) for c in listed["upcoming"]] == [(hold["id"], "confirmed")]
    assert listed["upcoming"][0]["amount_paid"] == hold["total_price"]

    assert client.post(f"/reservations/{hold['id']}/cancel", headers=auth(user)).status_code == 200
    listed = client.get("/me/reservations", headers=auth(user)).json()
    assert listed["upcoming"] == []
    assert [(c["id"], c["status"]) for c in listed["cancelled"]] == [(hold["id"], "cancelled")]


# 10. Query count does not grow with the number of bookings.

def count_queries(fn):
    statements = []

    def before(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return len(statements)


def test_query_count_does_not_grow_with_bookings(db_session, user, other):
    def setup(owner, n):
        for i in range(n):
            room = make_room(db_session, hotel_name=f"H{owner.email}{i}", number=str(i))
            db_session.add(HotelImage(hotel_id=room.hotel_id, file=f"h{i}.jpg",
                                      width=100, height=100))
            reserve(db_session, owner, room, paid=300)

    setup(user, 1)
    setup(other, 10)
    one = count_queries(lambda: grouped(db_session, user))
    ten = count_queries(lambda: grouped(db_session, other))
    assert ten == one
