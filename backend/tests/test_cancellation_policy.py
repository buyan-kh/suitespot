"""Tests for US3.3, task 3.3.1 — Tiered cancellation fee rules engine."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.cancellation_policy import (
    TIER_FREE,
    TIER_FULL,
    TIER_PARTIAL,
    cancellation_refund,
    cancellation_tier,
)

TODAY = date(2024, 11, 15)


# ── Tier boundary tests ───────────────────────────────────────────────────────

def test_more_than_7_days_is_free():
    assert cancellation_tier(TODAY + timedelta(days=8), TODAY) == TIER_FREE

def test_exactly_7_days_is_free():
    assert cancellation_tier(TODAY + timedelta(days=7), TODAY) == TIER_FREE

def test_6_days_is_partial():
    assert cancellation_tier(TODAY + timedelta(days=6), TODAY) == TIER_PARTIAL

def test_exactly_2_days_is_partial():
    assert cancellation_tier(TODAY + timedelta(days=2), TODAY) == TIER_PARTIAL

def test_1_day_is_full():
    assert cancellation_tier(TODAY + timedelta(days=1), TODAY) == TIER_FULL

def test_today_checkin_is_full():
    assert cancellation_tier(TODAY, TODAY) == TIER_FULL

def test_past_checkin_is_full():
    assert cancellation_tier(TODAY - timedelta(days=1), TODAY) == TIER_FULL


# ── Refund quote tests ────────────────────────────────────────────────────────

def test_free_tier_full_refund():
    q = cancellation_refund(200, TODAY + timedelta(days=10), TODAY)
    assert q.tier == TIER_FREE
    assert q.fee_amount == Decimal("0.00")
    assert q.refund_amount == Decimal("200.00")

def test_partial_tier_half_refund():
    q = cancellation_refund(200, TODAY + timedelta(days=5), TODAY)
    assert q.tier == TIER_PARTIAL
    assert q.fee_amount == Decimal("100.00")
    assert q.refund_amount == Decimal("100.00")

def test_full_tier_no_refund():
    q = cancellation_refund(200, TODAY + timedelta(days=1), TODAY)
    assert q.tier == TIER_FULL
    assert q.fee_amount == Decimal("200.00")
    assert q.refund_amount == Decimal("0.00")

def test_amounts_always_sum_to_total():
    for days in [0, 1, 2, 3, 7, 8, 30]:
        q = cancellation_refund("123.45", TODAY + timedelta(days=days), TODAY)
        assert q.fee_amount + q.refund_amount == q.total_charged

def test_odd_total_rounds_correctly():
    # $1.00 at 50% → fee $0.50, refund $0.50
    q = cancellation_refund("1.00", TODAY + timedelta(days=5), TODAY)
    assert q.fee_amount == Decimal("0.50")
    assert q.refund_amount == Decimal("0.50")

def test_odd_total_pennies():
    # $1.01 at 50% → fee $0.51 (round half up), refund $0.50
    q = cancellation_refund("1.01", TODAY + timedelta(days=5), TODAY)
    assert q.fee_amount == Decimal("0.51")
    assert q.refund_amount == Decimal("0.50")
    assert q.fee_amount + q.refund_amount == q.total_charged

def test_accepts_float_total():
    q = cancellation_refund(150.75, TODAY + timedelta(days=5), TODAY)
    assert q.total_charged == Decimal("150.75")

def test_days_until_checkin_field():
    q = cancellation_refund(100, TODAY + timedelta(days=3), TODAY)
    assert q.days_until_checkin == 3

def test_fee_rate_field():
    assert cancellation_refund(100, TODAY + timedelta(days=10), TODAY).fee_rate == Decimal("0.00")
    assert cancellation_refund(100, TODAY + timedelta(days=5),  TODAY).fee_rate == Decimal("0.50")
    assert cancellation_refund(100, TODAY + timedelta(days=1),  TODAY).fee_rate == Decimal("1.00")
