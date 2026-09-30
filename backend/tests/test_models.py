import uuid
from datetime import date

from app.models import Hotel, Payment, Reservation, Room, User


def test_create_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        email="test@example.com",
        hashed_password="hashed",
        first_name="John",
        last_name="Doe",
        role="guest",
    )
    db_session.add(user)
    db_session.commit()

    fetched = db_session.query(User).filter_by(email="test@example.com").first()
    assert fetched is not None
    assert fetched.first_name == "John"
    assert fetched.role == "guest"
    assert fetched.is_active is True


def test_create_hotel_with_rooms(db_session):
    hotel = Hotel(
        id=str(uuid.uuid4()),
        name="Test Hotel",
        address="123 Main St",
        city="San Jose",
        country="US",
        star_rating=4,
    )
    db_session.add(hotel)
    db_session.commit()

    room = Room(
        id=str(uuid.uuid4()),
        hotel_id=hotel.id,
        room_number="101",
        room_type="double",
        price_per_night=150.00,
        max_guests=2,
    )
    db_session.add(room)
    db_session.commit()

    fetched_hotel = db_session.query(Hotel).first()
    assert len(fetched_hotel.rooms) == 1
    assert fetched_hotel.rooms[0].room_number == "101"


def test_create_reservation(db_session):
    user = User(
        id=str(uuid.uuid4()),
        email="guest@example.com",
        hashed_password="hashed",
        first_name="Jane",
        last_name="Doe",
    )
    hotel = Hotel(
        id=str(uuid.uuid4()),
        name="Resort",
        address="456 Beach Rd",
        city="Miami",
        country="US",
    )
    db_session.add_all([user, hotel])
    db_session.commit()

    room = Room(
        id=str(uuid.uuid4()),
        hotel_id=hotel.id,
        room_number="201",
        room_type="suite",
        price_per_night=300.00,
    )
    db_session.add(room)
    db_session.commit()

    reservation = Reservation(
        id=str(uuid.uuid4()),
        user_id=user.id,
        room_id=room.id,
        check_in_date=date(2026, 10, 1),
        check_out_date=date(2026, 10, 5),
        num_guests=2,
        total_price=1200.00,
        status="confirmed",
    )
    db_session.add(reservation)
    db_session.commit()

    fetched = db_session.query(Reservation).first()
    assert fetched.user.email == "guest@example.com"
    assert fetched.room.hotel.name == "Resort"
    assert fetched.status == "confirmed"


def test_create_payment(db_session):
    user = User(
        id=str(uuid.uuid4()),
        email="pay@example.com",
        hashed_password="hashed",
        first_name="Pay",
        last_name="User",
    )
    hotel = Hotel(
        id=str(uuid.uuid4()),
        name="Pay Hotel",
        address="789 St",
        city="NYC",
        country="US",
    )
    db_session.add_all([user, hotel])
    db_session.commit()

    room = Room(
        id=str(uuid.uuid4()),
        hotel_id=hotel.id,
        room_number="301",
        room_type="single",
        price_per_night=100.00,
    )
    db_session.add(room)
    db_session.commit()

    reservation = Reservation(
        id=str(uuid.uuid4()),
        user_id=user.id,
        room_id=room.id,
        check_in_date=date(2026, 11, 1),
        check_out_date=date(2026, 11, 3),
        num_guests=1,
        total_price=200.00,
    )
    db_session.add(reservation)
    db_session.commit()

    payment = Payment(
        id=str(uuid.uuid4()),
        reservation_id=reservation.id,
        amount=200.00,
        payment_method="credit_card",
        transaction_id="txn_abc123",
        status="completed",
    )
    db_session.add(payment)
    db_session.commit()

    fetched = db_session.query(Payment).first()
    assert fetched.amount == 200.00
    assert fetched.reservation.user.email == "pay@example.com"


def test_unique_email_constraint(db_session):
    user1 = User(
        id=str(uuid.uuid4()),
        email="dup@example.com",
        hashed_password="h1",
        first_name="A",
        last_name="B",
    )
    user2 = User(
        id=str(uuid.uuid4()),
        email="dup@example.com",
        hashed_password="h2",
        first_name="C",
        last_name="D",
    )
    db_session.add(user1)
    db_session.commit()
    db_session.add(user2)
    try:
        db_session.commit()
        assert False, "Should have raised IntegrityError"
    except Exception:
        db_session.rollback()
