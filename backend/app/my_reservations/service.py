"""Group a guest's reservations into upcoming, past and cancelled (4.1.1).

Rules (stored status -> group / badge):
- pending, hold still live        -> upcoming / awaiting_payment
- pending, hold expired           -> hidden (the guest walked away from checkout)
- confirmed, check-out after today -> upcoming / confirmed (includes a stay in progress)
- confirmed, check-out today or before -> past / completed
- completed                       -> past / completed
- cancelled, was paid             -> cancelled / cancelled
- cancelled, never paid           -> hidden (a lapsed or abandoned hold)
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.images.models import HotelImage
from app.images.service import serialize
from app.models import Reservation, Room
from app.services.booking_availability import HOLD_MINUTES
from app.services.pricing import money

PAYMENT_SUCCEEDED = "succeeded"


@dataclass
class Grouped:
    upcoming: list[dict]
    past: list[dict]
    cancelled: list[dict]


def _utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _amount_paid(reservation: Reservation) -> Decimal:
    return money(sum(
        (Decimal(str(p.amount)) for p in reservation.payments if p.status == PAYMENT_SUCCEEDED),
        Decimal("0"),
    ))


def _hold_expires_at(reservation: Reservation) -> datetime | None:
    if reservation.created_at is None:
        return None
    return _utc(reservation.created_at) + timedelta(minutes=HOLD_MINUTES)


def _classify(reservation: Reservation, today: date, now: datetime) -> tuple[str, str] | None:
    """Return (group, badge), or None to hide the reservation."""
    status = reservation.status
    if status == "pending":
        expires = _hold_expires_at(reservation)
        if expires is not None and now < expires:
            return "upcoming", "awaiting_payment"
        return None
    if status == "confirmed":
        if reservation.check_out_date > today:
            return "upcoming", "confirmed"
        return "past", "completed"
    if status == "completed":
        return "past", "completed"
    if status == "cancelled":
        if _amount_paid(reservation) > 0:
            return "cancelled", "cancelled"
        return None
    return None  # an unknown status is not shown rather than guessed at


def _cover_photos(db: Session, hotel_ids: set[str], base_url: str) -> dict[str, dict]:
    """First photo per hotel, in the same order as GET /hotels/{id}/images."""
    if not hotel_ids:
        return {}
    rows = db.scalars(
        select(HotelImage)
        .where(HotelImage.hotel_id.in_(hotel_ids))
        .order_by(HotelImage.hotel_id, HotelImage.room_type.is_not(None), HotelImage.position)
    ).all()
    covers: dict[str, dict] = {}
    for row in rows:
        covers.setdefault(row.hotel_id, serialize(row, base_url))
    return covers


def _card(reservation: Reservation, badge: str, cover: dict | None) -> dict:
    room, hotel = reservation.room, reservation.room.hotel
    return {
        "id": reservation.id,
        "status": badge,
        "hotel": {"id": hotel.id, "name": hotel.name, "city": hotel.city, "image": cover},
        "room": {"id": room.id, "room_type": room.room_type, "room_number": room.room_number},
        "check_in": reservation.check_in_date,
        "check_out": reservation.check_out_date,
        "nights": (reservation.check_out_date - reservation.check_in_date).days,
        "num_guests": reservation.num_guests,
        "total_price": float(money(reservation.total_price)),
        "amount_paid": float(_amount_paid(reservation)),
        "hold_expires_at": _hold_expires_at(reservation) if badge == "awaiting_payment" else None,
    }


def my_reservations(
    db: Session,
    *,
    user_id: str,
    base_url: str,
    now: datetime | None = None,
) -> Grouped:
    now = now or datetime.now(timezone.utc)
    today = now.date()

    reservations = db.scalars(
        select(Reservation)
        .where(Reservation.user_id == user_id)
        .options(
            selectinload(Reservation.room).selectinload(Room.hotel),
            selectinload(Reservation.payments),
        )
    ).all()

    placed: list[tuple[str, str, Reservation]] = []
    for reservation in reservations:
        result = _classify(reservation, today, now)
        if result is not None:
            placed.append((*result, reservation))

    covers = _cover_photos(db, {r.room.hotel_id for _, _, r in placed}, base_url)
    groups: dict[str, list[tuple[Reservation, dict]]] = {"upcoming": [], "past": [], "cancelled": []}
    for group, badge, reservation in placed:
        groups[group].append((reservation, _card(reservation, badge, covers.get(reservation.room.hotel_id))))

    # Soonest stay first; most recent past stay first; latest cancellation first.
    groups["upcoming"].sort(key=lambda pair: (pair[0].check_in_date, pair[0].id))
    groups["past"].sort(key=lambda pair: (pair[0].check_out_date, pair[0].id), reverse=True)
    groups["cancelled"].sort(
        key=lambda pair: (_utc(pair[0].updated_at) if pair[0].updated_at else now, pair[0].id),
        reverse=True,
    )
    return Grouped(**{name: [card for _, card in pairs] for name, pairs in groups.items()})
