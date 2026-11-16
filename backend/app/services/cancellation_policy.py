"""US3.3, task 3.3.1 — Tiered cancellation fee rules engine.

Three tiers based on how far in advance the guest cancels:

  > 7 days before check-in   → full refund (0 % fee)
  2–7 days before check-in   → 50 % of the reservation total kept as a fee
  < 48 hours before check-in → no refund (100 % fee)

The tier boundary is measured against today's date (or an injectable `today`
for testing).  The router (3.3.3) will call `cancellation_refund()` to get the
amounts and then process the actual charge/refund with the payment provider.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


# ── Tier constants ────────────────────────────────────────────────────────────

TIER_FREE = "free"          # > 7 days  → full refund
TIER_PARTIAL = "partial"    # 2–7 days  → 50 % fee
TIER_FULL = "full"          # < 48 h    → no refund

# How many days before check-in each tier boundary falls.
_PARTIAL_DAYS = 7   # inside this  → at most partial refund
_FULL_DAYS    = 2   # inside this  → no refund at all

# Fee rate per tier (fraction of the total kept by the hotel).
_FEE_RATE = {
    TIER_FREE:    Decimal("0.00"),
    TIER_PARTIAL: Decimal("0.50"),
    TIER_FULL:    Decimal("1.00"),
}


# ── Public interface ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CancellationQuote:
    tier: str                 # one of the TIER_* constants
    days_until_checkin: int   # negative when check-in is in the past
    fee_rate: Decimal         # fraction kept by the hotel
    total_charged: Decimal    # what the guest originally paid
    fee_amount: Decimal       # amount the hotel keeps
    refund_amount: Decimal    # amount returned to the guest


def cancellation_tier(check_in: date, today: date | None = None) -> str:
    """Return the cancellation tier for a check-in date.

    >>> from datetime import date, timedelta
    >>> today = date(2024, 11, 1)
    >>> cancellation_tier(today + timedelta(days=10), today)
    'free'
    >>> cancellation_tier(today + timedelta(days=5), today)
    'partial'
    >>> cancellation_tier(today + timedelta(days=1), today)
    'full'
    """
    today = today or datetime.now(timezone.utc).date()
    days_left = (check_in - today).days
    if days_left >= _PARTIAL_DAYS:
        return TIER_FREE
    if days_left >= _FULL_DAYS:
        return TIER_PARTIAL
    return TIER_FULL


def cancellation_refund(
    total_price,
    check_in: date,
    today: date | None = None,
) -> CancellationQuote:
    """Return a full breakdown of what the guest owes and gets back.

    *total_price* is the reservation's ``total_price`` field (Decimal, float,
    or str — anything ``Decimal()`` accepts).
    """
    today = today or datetime.now(timezone.utc).date()
    tier = cancellation_tier(check_in, today)
    days_left = (check_in - today).days

    total = Decimal(str(total_price)).quantize(_CENT)
    fee_rate = _FEE_RATE[tier]
    fee_amount = (total * fee_rate).quantize(_CENT, rounding=ROUND_HALF_UP)
    refund_amount = total - fee_amount

    return CancellationQuote(
        tier=tier,
        days_until_checkin=days_left,
        fee_rate=fee_rate,
        total_charged=total,
        fee_amount=fee_amount,
        refund_amount=refund_amount,
    )
