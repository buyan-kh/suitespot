"""One place that works out what a stay costs (US3.2, task 3.2.2)"""

from decimal import Decimal

_CENT = Decimal("0.01")


class TotalMismatch(Exception):  # -> 409
    def __init__(self, expected: Decimal, displayed: Decimal):
        super().__init__(f"Displayed {displayed} but the total is {expected}.")
        self.expected = expected
        self.displayed = displayed


def money(value) -> Decimal:
    """Any number-like value as an exact amount in cents."""
    return Decimal(str(value)).quantize(_CENT)


def stay_total(price_per_night, nights: int) -> Decimal:
    """What a stay costs: the nightly rate times the number of nights."""
    return money(Decimal(str(price_per_night)) * nights)


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