"""One place that works out what a stay costs (US3.2, task 3.2.2)"""

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")

# ── Fee rules (must stay in sync with breakdown.py display) ───────────────────
# (label, kind, value)
#   kind "pct"   → fraction of subtotal
#   kind "night" → flat amount per night
#   kind "stay"  → flat amount for the whole stay
_TAX_RATE = Decimal("0.12")
_FEE_RULES = [
    ("Service fee",  "pct",   Decimal("0.10")),
    ("Resort fee",   "night", Decimal("15.00")),
    ("Cleaning fee", "stay",  Decimal("40.00")),
]


class TotalMismatch(Exception):  # -> 409
    def __init__(self, expected: Decimal, displayed: Decimal):
        super().__init__(f"Displayed {displayed} but the total is {expected}.")
        self.expected = expected
        self.displayed = displayed


def money(value) -> Decimal:
    """Any number-like value as an exact amount in cents."""
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def stay_total(price_per_night, nights: int) -> Decimal:
    """Nightly subtotal only (rate × nights). Does NOT include fees or tax."""
    return money(Decimal(str(price_per_night)) * nights)


def full_stay_total(price_per_night, nights: int) -> Decimal:
    """Total amount the guest is charged: subtotal + fees + tax.

    This is what gets stored in ``Reservation.total_price`` so the breakdown
    endpoint and the payment-confirmation service always agree.

    Fee rules
    ---------
    - Service fee: 10 % of subtotal
    - Resort fee:  $15 per night
    - Cleaning fee: $40 flat per stay
    - Tax: 12 % of (subtotal + fees)
    """
    subtotal = stay_total(price_per_night, nights)

    fee_total = Decimal("0.00")
    for _label, kind, value in _FEE_RULES:
        if kind == "pct":
            fee_total += money(subtotal * value)
        elif kind == "night":
            fee_total += money(value * nights)
        else:  # stay
            fee_total += money(value)

    pre_tax = subtotal + fee_total
    tax = money(pre_tax * _TAX_RATE)
    return pre_tax + tax


def verify_displayed_total(reservation, displayed_total) -> Decimal:
    """Return the reservation's total if the displayed one matches it to the cent.

    Raises TotalMismatch otherwise, carrying the real total so the screen can
    refresh itself instead of charging a different number than the guest saw.
    """
    expected = money(reservation.total_price)
    displayed = money(displayed_total)
    if displayed != expected:
        raise TotalMismatch(expected, displayed)
    return expected