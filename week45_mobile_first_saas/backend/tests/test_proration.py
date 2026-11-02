"""Unit tests for linear proration mathematics and invoice line generation."""

from datetime import datetime, timedelta, timezone

import pytest

from app.billing.proration import calculate_proration
from app.models.schemas import BillingInterval, Plan, Subscription


@pytest.fixture
def plan_starter() -> Plan:
    return Plan(
        id="plan_starter",
        name="Starter",
        tier="starter",
        price_monthly_cents=1900,
        price_annual_cents=19000,
        limits={"max_projects": 5},
        features=["export_data"],
    )


@pytest.fixture
def plan_pro() -> Plan:
    return Plan(
        id="plan_pro",
        name="Pro",
        tier="pro",
        price_monthly_cents=4900,
        price_annual_cents=49000,
        limits={"max_projects": -1},
        features=["custom_domains"],
    )


@pytest.fixture
def plan_free() -> Plan:
    return Plan(
        id="plan_free",
        name="Free",
        tier="free",
        price_monthly_cents=0,
        price_annual_cents=0,
        limits={"max_projects": 1},
        features=[],
    )


def test_proration_mid_cycle_upgrade(plan_starter: Plan, plan_pro: Plan):
    """Verify upgrade from Starter ($19) to Pro ($49) at exactly 50% period."""
    start = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
    # Midpoint: exactly halfway
    mid = start + (end - start) / 2

    fmt = "%Y-%m-%d %H:%M:%S"
    sub = Subscription(
        id="sub_test",
        user_id="usr_test",
        plan_id="plan_starter",
        billing_interval="monthly",
        status="active",
        current_period_start=start.strftime(fmt),
        current_period_end=end.strftime(fmt),
    )

    result = calculate_proration(
        current_plan=plan_starter,
        new_plan=plan_pro,
        subscription=sub,
        effective_at=mid,
    )

    assert result.is_upgrade is True
    assert pytest.approx(result.remaining_ratio, 0.001) == 0.5
    assert result.unused_credit_cents == 950  # 1900 * 0.5
    assert result.new_plan_charge_cents == 2450  # 4900 * 0.5
    assert result.net_amount_due_cents == 1500  # 2450 - 950
    assert result.credit_remaining_cents == 0

    items = result.to_line_items()
    assert len(items) == 2
    assert items[0]["unit_amount_cents"] == -950
    assert items[1]["unit_amount_cents"] == 2450


def test_proration_mid_cycle_downgrade(plan_starter: Plan, plan_pro: Plan):
    """Verify mid-cycle downgrade creates remaining credit balance."""
    start = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
    mid = start + (end - start) / 2
    fmt = "%Y-%m-%d %H:%M:%S"

    sub = Subscription(
        id="sub_test",
        user_id="usr_test",
        plan_id="plan_pro",
        billing_interval="monthly",
        status="active",
        current_period_start=start.strftime(fmt),
        current_period_end=end.strftime(fmt),
    )

    result = calculate_proration(
        current_plan=plan_pro,
        new_plan=plan_starter,
        subscription=sub,
        effective_at=mid,
    )

    assert result.is_upgrade is False
    assert result.unused_credit_cents == 2450  # 4900 * 0.5
    assert result.new_plan_charge_cents == 950  # 1900 * 0.5
    assert result.net_amount_due_cents == 0
    assert result.credit_remaining_cents == 1500  # 2450 - 950


def test_proration_at_start_of_period(plan_starter: Plan, plan_pro: Plan):
    """Verify upgrade at 0 seconds into period results in full price difference."""
    start = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
    fmt = "%Y-%m-%d %H:%M:%S"

    sub = Subscription(
        id="sub_test",
        user_id="usr_test",
        plan_id="plan_starter",
        billing_interval="monthly",
        status="active",
        current_period_start=start.strftime(fmt),
        current_period_end=end.strftime(fmt),
    )

    result = calculate_proration(
        current_plan=plan_starter,
        new_plan=plan_pro,
        subscription=sub,
        effective_at=start,
    )

    assert pytest.approx(result.remaining_ratio, 0.001) == 1.0
    assert result.unused_credit_cents == 1900
    assert result.new_plan_charge_cents == 4900
    assert result.net_amount_due_cents == 3000


def test_proration_at_end_of_period(plan_starter: Plan, plan_pro: Plan):
    """Verify upgrade at period end has zero remaining time and zero net amount."""
    start = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
    fmt = "%Y-%m-%d %H:%M:%S"

    sub = Subscription(
        id="sub_test",
        user_id="usr_test",
        plan_id="plan_starter",
        billing_interval="monthly",
        status="active",
        current_period_start=start.strftime(fmt),
        current_period_end=end.strftime(fmt),
    )

    result = calculate_proration(
        current_plan=plan_starter,
        new_plan=plan_pro,
        subscription=sub,
        effective_at=end + timedelta(hours=1),
    )

    assert result.remaining_ratio == 0.0
    assert result.unused_credit_cents == 0
    assert result.new_plan_charge_cents == 0
    assert result.net_amount_due_cents == 0
    assert result.credit_remaining_cents == 0


def test_proration_free_tier_transitions(plan_free: Plan, plan_pro: Plan):
    """Verify transitions to and from $0 free tier."""
    start = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
    mid = start + (end - start) / 2
    fmt = "%Y-%m-%d %H:%M:%S"

    sub = Subscription(
        id="sub_free",
        user_id="usr_test",
        plan_id="plan_free",
        billing_interval="monthly",
        status="active",
        current_period_start=start.strftime(fmt),
        current_period_end=end.strftime(fmt),
    )

    # Free to Pro
    res = calculate_proration(plan_free, plan_pro, sub, effective_at=mid)
    assert res.unused_credit_cents == 0
    assert res.new_plan_charge_cents == 2450
    assert res.net_amount_due_cents == 2450

    # Free to Free (zero items default)
    res_free = calculate_proration(plan_free, plan_free, sub, effective_at=mid)
    items = res_free.to_line_items()
    assert len(items) == 1
    assert items[0]["unit_amount_cents"] == 0


def test_proration_monthly_to_annual_interval(plan_starter: Plan):
    """Verify switching interval from Monthly ($19/mo) to Annual ($190/yr)."""
    start = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
    mid = start + (end - start) / 2
    fmt = "%Y-%m-%d %H:%M:%S"

    sub = Subscription(
        id="sub_test",
        user_id="usr_test",
        plan_id="plan_starter",
        billing_interval="monthly",
        status="active",
        current_period_start=start.strftime(fmt),
        current_period_end=end.strftime(fmt),
    )

    res = calculate_proration(
        current_plan=plan_starter,
        new_plan=plan_starter,
        subscription=sub,
        effective_at=mid,
        target_interval=BillingInterval.ANNUAL,
    )

    assert res.billing_interval == "annual"
    assert res.unused_credit_cents == 950  # 1900 * 0.5
    assert res.new_plan_charge_cents == 9500  # 19000 * 0.5
    assert res.net_amount_due_cents == 8550  # 9500 - 950
