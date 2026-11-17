"""The price the modify form quotes (2.3.2) must be what modify (2.3.1) applies.

If the two ever disagree, the guest sees one total and gets another. Every scenario
is sent to both endpoints: they must make the same yes/no decision and, when
both say yes, agree on the new total and the price difference.

Skipped until the quote endpoint (#59) is merged, then it runs on its own.
"""

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("app.requote.router", reason="needs the quote endpoint from #59")

from app.models import Hotel, Payment, Room, User  # noqa: E402
from app.security import issue_tokens  # noqa: E402
from app.services.booking_availability import place_hold  # noqa: E402

TODAY = datetime.now(timezone.utc).date()
D = lambda n: TODAY + timedelta(days=n)  # noqa: E731
IN, OUT = D(10), D(13)  # 3 nights x 100 = 300


def make_user(db, email):
    u = User(email=email, hashed_password="x", first_name="T", last_name="U")
    db.add(u)
    db.commit()
    return u


def auth(user):
    return {"Authorization": f"Bearer {issue_tokens(user.id)['access_token']}"}


def make_room(db, price=100, number="1", guests=2, active=True, available=True):
    hotel = Hotel(name=f"H{number}", address="1", city="SJ", country="US", is_active=active)
    db.add(hotel)
    db.flush()
    room = Room(hotel_id=hotel.id, room_number=number, price_per_night=price,
                max_guests=guests, is_available=available)
    db.add(room)
    db.commit()
    return room


def paid(c):
    c["booking"].status = "confirmed"
    c["db"].add(Payment(reservation_id=c["booking"].id, amount=300, payment_method="card", status="succeeded"))
    c["db"].commit()


def started(c):
    b = c["booking"]
    b.check_in_date, b.check_out_date, b.status = D(-1), D(2), "confirmed"
    c["db"].commit()


def with_status(status):
    def setup(c):
        c["booking"].status = status
        c["db"].commit()
        return {"num_guests": 2}
    return setup


SCENARIOS = {
    "extend a night": lambda c: {"check_out": D(14)},
    "shorten a night": lambda c: {"check_out": D(12)},
    "shift later": lambda c: {"check_in": D(20), "check_out": D(23)},
    "overlap own old dates": lambda c: {"check_in": D(11), "check_out": D(14)},
    "pricier room": lambda c: {"room_id": make_room(c["db"], 150, "2").id},
    "cheaper room": lambda c: {"room_id": make_room(c["db"], 60, "2").id},
    "room and dates": lambda c: {"room_id": make_room(c["db"], 150, "2").id, "check_in": D(30), "check_out": D(32)},
    "more guests": lambda c: {"num_guests": 2},
    "too many guests": lambda c: {"num_guests": 5},
    "zero guests": lambda c: {"num_guests": 0},
    "dates taken by someone else": lambda c: (
        place_hold(c["db"], user_id=c["other"].id, room_id=c["room"].id, check_in=D(20), check_out=D(23)),
        {"check_in": D(21), "check_out": D(24)})[1],
    "room booked by someone else": lambda c: (
        lambda r: (place_hold(c["db"], user_id=c["other"].id, room_id=r.id, check_in=IN, check_out=OUT),
                   {"room_id": r.id})[1])(make_room(c["db"], 100, "2")),
    "deactivated hotel": lambda c: {"room_id": make_room(c["db"], 100, "2", active=False).id},
    "unknown room": lambda c: {"room_id": "nope"},
    "check-out before check-in": lambda c: {"check_out": D(9)},
    "check-in in the past": lambda c: {"check_in": D(-3), "check_out": D(-1)},
    "same values": lambda c: {"check_in": IN, "check_out": OUT},
    "cancelled": with_status("cancelled"),
    "completed": with_status("completed"),
    "stay already started": lambda c: (started(c), {"check_out": D(4)})[1],
    "paid, two more nights": lambda c: (paid(c), {"check_out": D(15)})[1],
    "paid, one night less": lambda c: (paid(c), {"check_out": D(12)})[1],
    "empty request": lambda c: {},
    "unknown field": lambda c: {"num_guests": 2, "total_price": 1},
    "expired unpaid hold": lambda c: (
        c["booking"].__setattr__("created_at", datetime.now(timezone.utc) - timedelta(minutes=16)),
        c["db"].commit(), {"num_guests": 2})[2],
}


# Known differences, tracked until the quote endpoint is aligned (they start passing,
# and pytest reports XPASS, once Darren's quote is fixed; then drop the entry).
KNOWN_DIFFERENCES = {
    "empty request": "quote treats {} as 'no change'; modify refuses it",
    "unknown field": "quote ignores unknown fields; modify refuses them",
    "expired unpaid hold": "quote prices a hold that has expired; modify refuses it",
}
PARAMS = [
    pytest.param(name, marks=pytest.mark.xfail(reason=KNOWN_DIFFERENCES[name]))
    if name in KNOWN_DIFFERENCES else name
    for name in SCENARIOS
]


@pytest.mark.parametrize("name", PARAMS)
def test_modify_decides_and_prices_like_the_quote(client, db_session, name):
    me, other = make_user(db_session, "me@x.com"), make_user(db_session, "other@x.com")
    room = make_room(db_session, 100, "1")
    booking = place_hold(db_session, user_id=me.id, room_id=room.id, check_in=IN, check_out=OUT)
    ctx = {"db": db_session, "other": other, "room": room, "booking": booking}
    changes = SCENARIOS[name](ctx)
    body = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in changes.items()}

    quote = client.post(f"/reservations/{booking.id}/quote-change", json=body, headers=auth(me))
    modify = client.patch(f"/reservations/{booking.id}", json=body, headers=auth(me))

    assert (quote.status_code == 200) == (modify.status_code == 200), (quote.json(), modify.json())
    if modify.status_code == 200:
        assert quote.json()["proposed"]["total"] == modify.json()["total_price"]
        assert quote.json()["difference"] == modify.json()["price_change"]["difference"]
