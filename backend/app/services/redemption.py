"""US7.3, task 7.3.1 — Points redemption rules.

Conversion rate : 100 points  = $1.00
Minimum redemption : 500 points ($5.00)
Maximum per booking : user's current balance, capped to the reservation total.

Public API
----------
redemption_quote(db, *, user_id, reservation, points_requested) -> RedemptionQuote
    Validates the request and returns a fully-computed quote.  Raises
    ValueError with a human-readable message on any constraint violation.

apply_redemption(db, *, user_id, reservation, points_requested) -> RedemptionQuote
    Calls redemption_quote, then writes a "points_redeemed" ledger row,
    updates reservation.total_price to the discounted amount, and returns
    the quote so the caller can see the discount applied.

Bugs fixed
----------
1. apply_redemption now updates reservation.total_price so the charge uses
   the discounted amount (previously points were spent but price unchanged).
2. Redeeming twice on one booking now returns 409 (AlreadyRedeemed) instead
   of a 500 from the DB unique constraint.
3. Cancelled/completed reservations cannot be redeemed against (NotRedeemable).
4. reverse_points (in points.py) now also returns any "points_redeemed" rows
   so a refund gives the user their points back.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.points import PointsLedger
from app.models.reservation import Reservation
from app.services.points import get_balance

# ── constants ──────────────────────────────────────────────────────────────
POINTS_PER_DOLLAR: int = 100  # 100 pts = $1.00
MIN_REDEMPTION_POINTS: int = 500  # floor: 500 pts = $5.00

# Statuses on which redemption is allowed (pending hold or confirmed booking).
_REDEEMABLE_STATUSES = {"pending", "confirmed"}


# ── custom exceptions ──────────────────────────────────────────────────────
class AlreadyRedeemed(ValueError):
    """The reservation already has a points_redeemed ledger row."""


class NotRedeemable(ValueError):
    """The reservation is cancelled or completed and cannot be redeemed against."""


def _cents_to_decimal(points: int) -> Decimal:
    """Convert whole points to a dollar Decimal (2 dp)."""
    return (Decimal(points) / Decimal(POINTS_PER_DOLLAR)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


# ── result type ────────────────────────────────────────────────────────────
@dataclass
class RedemptionQuote:
    points_requested: int       # what the caller asked for
    points_applied: int         # what was actually usable (≤ requested)
    dollar_discount: Decimal    # points_applied / 100, rounded to 2 dp
    new_total: Decimal          # reservation.total_price - dollar_discount
    balance_before: int         # user's balance before spending
    balance_after: int          # balance_before - points_applied


# ── validation helpers ─────────────────────────────────────────────────────
def _validate(
    points_requested: int,
    balance: int,
    reservation_total: Decimal,
) -> int:
    """Return the validated (possibly clamped) points_applied.

    Raises ValueError for hard violations; silently clamps to the maximum
    useful amount so callers that pass 'all my points' still get a sensible
    result.
    """
    if points_requested <= 0:
        raise ValueError("points_requested must be a positive integer.")

    if points_requested < MIN_REDEMPTION_POINTS:
        raise ValueError(
            f"Minimum redemption is {MIN_REDEMPTION_POINTS} points "
            f"(${_cents_to_decimal(MIN_REDEMPTION_POINTS):.2f})."
        )

    if balance < MIN_REDEMPTION_POINTS:
        raise ValueError(
            f"Insufficient points balance. You have {balance} points; "
            f"the minimum redemption is {MIN_REDEMPTION_POINTS} points."
        )

    # Maximum useful points: can't discount more than the reservation total.
    max_from_total = int(
        (reservation_total * POINTS_PER_DOLLAR).to_integral_value(
            rounding=ROUND_HALF_UP
        )
    )
    max_points = min(balance, max_from_total)

    # Clamp silently — user asked for more than allowed.
    return min(points_requested, max_points)


# ── public functions ───────────────────────────────────────────────────────
def redemption_quote(
    db: Session,
    *,
    user_id: str,
    reservation: Reservation,
    points_requested: int,
) -> RedemptionQuote:
    """Compute a redemption quote without writing anything to the database."""
    balance = get_balance(db, user_id=user_id)
    total = Decimal(str(reservation.total_price))

    points_applied = _validate(points_requested, balance, total)
    discount = _cents_to_decimal(points_applied)
    new_total = (total - discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # Clamp new_total to zero (edge case: points cover entire stay).
    new_total = max(Decimal("0.00"), new_total)

    return RedemptionQuote(
        points_requested=points_requested,
        points_applied=points_applied,
        dollar_discount=discount,
        new_total=new_total,
        balance_before=balance,
        balance_after=balance - points_applied,
    )


def apply_redemption(
    db: Session,
    *,
    user_id: str,
    reservation: Reservation,
    points_requested: int,
) -> RedemptionQuote:
    """Validate, write a ledger row, update the reservation total, and return the quote.

    Raises
    ------
    NotRedeemable   – reservation is cancelled or completed.
    AlreadyRedeemed – a points_redeemed row already exists for this reservation.
    ValueError      – points validation failed (too few, below minimum, etc.).
    """
    # Bug fix 3: block redemption on closed reservations.
    if reservation.status not in _REDEEMABLE_STATUSES:
        raise NotRedeemable(
            f"Redemption is not allowed on a {reservation.status!r} reservation."
        )

    # Bug fix 2: guard against double-redemption (the DB UniqueConstraint would
    # raise an IntegrityError; we raise a clean exception instead).
    already = db.execute(
        select(PointsLedger).where(
            PointsLedger.reservation_id == reservation.id,
            PointsLedger.reason == "points_redeemed",
        )
    ).scalar_one_or_none()
    if already is not None:
        raise AlreadyRedeemed(
            "Points have already been redeemed for this reservation."
        )

    quote = redemption_quote(
        db, user_id=user_id, reservation=reservation,
        points_requested=points_requested,
    )

    # Bug fix 1: update total_price so the subsequent charge uses the discounted
    # amount.  Without this the guest loses the points and still pays full price.
    reservation.total_price = quote.new_total
    db.add(reservation)

    entry = PointsLedger(
        user_id=user_id,
        reservation_id=reservation.id,
        delta=-quote.points_applied,
        reason="points_redeemed",
        note=f"Redeemed {quote.points_applied} pts for ${quote.dollar_discount:.2f} discount",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return quote
