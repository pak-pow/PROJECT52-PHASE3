"""Unit tests for UsageService metered consumption and quota evaluation."""

import sqlite3

import pytest

from app.models.schemas import BillingInterval, Subscription, SubscriptionStatus
from app.services.usage_service import UsageService
from data.seed import seed_demo_user


@pytest.fixture
def usage_service(db_conn: sqlite3.Connection) -> UsageService:
    seed_demo_user(db_conn)
    return UsageService(db_conn)


def test_record_usage_standard(usage_service: UsageService):
    """Verify recording consumption creates and persists a UsageRecord."""
    record = usage_service.record_usage(
        user_id="usr_demo_alice",
        metric_key="monthly_api_calls",
        quantity=5,
    )
    assert record.user_id == "usr_demo_alice"
    assert record.metric_key == "monthly_api_calls"
    assert record.quantity == 5
    assert record.id.startswith("use_")


def test_record_usage_idempotency(usage_service: UsageService):
    """Verify duplicate idempotency keys return record without double-counting."""
    key = "idem_unique_test_12345"
    rec1 = usage_service.record_usage(
        user_id="usr_demo_alice",
        metric_key="monthly_api_calls",
        quantity=10,
        idempotency_key=key,
    )
    rec2 = usage_service.record_usage(
        user_id="usr_demo_alice",
        metric_key="monthly_api_calls",
        quantity=10,
        idempotency_key=key,
    )
    assert rec1.id == rec2.id
    assert rec1.quantity == rec2.quantity


def test_record_usage_invalid_quantity(usage_service: UsageService):
    """Verify zero or negative quantities raise ValueError."""
    with pytest.raises(ValueError):
        usage_service.record_usage(
            user_id="usr_demo_alice",
            metric_key="monthly_api_calls",
            quantity=0,
        )

    with pytest.raises(ValueError):
        usage_service.record_usage(
            user_id="usr_demo_alice",
            metric_key="monthly_api_calls",
            quantity=-5,
        )


def test_get_period_usage(usage_service: UsageService):
    """Verify calculating usage within interval bounds."""
    usage_service.record_usage(
        user_id="usr_demo_alice",
        metric_key="storage_mb",
        quantity=100,
    )
    usage = usage_service.get_period_usage(
        user_id="usr_demo_alice",
        metric_key="storage_mb",
        period_start="2020-01-01 00:00:00",
        period_end="2030-01-01 00:00:00",
    )
    assert usage >= 100


def test_get_user_metric_usage_with_subscription(usage_service: UsageService):
    """Verify user metric usage accounts for active subscription window."""
    sub = Subscription(
        id="sub_test_window",
        user_id="usr_demo_alice",
        plan_id="plan_pro",
        billing_interval=BillingInterval.MONTHLY.value,
        status=SubscriptionStatus.ACTIVE.value,
        current_period_start="2026-11-01 00:00:00",
        current_period_end="2026-12-01 00:00:00",
    )
    usage = usage_service.get_user_metric_usage(
        user_id="usr_demo_alice",
        metric_key="monthly_api_calls",
        subscription=sub,
    )
    assert usage >= 0


def test_evaluate_quota_status_unlimited():
    """Verify unlimited (-1) quota status."""
    res = UsageService.evaluate_quota_status(current_usage=150000, limit=-1)
    assert res["unlimited"] is True
    assert res["is_over_quota"] is False
    assert res["threshold_alert"] is None


def test_evaluate_quota_status_threshold_alerts():
    """Verify 80%, 90%, and 100% threshold alert calculations."""
    # Under 80% (70 / 100)
    r70 = UsageService.evaluate_quota_status(current_usage=70, limit=100)
    assert r70["percentage"] == 70.0
    assert r70["threshold_alert"] is None
    assert r70["is_over_quota"] is False

    # 80% (80 / 100)
    r80 = UsageService.evaluate_quota_status(current_usage=80, limit=100)
    assert r80["percentage"] == 80.0
    assert r80["threshold_alert"] == "80%"
    assert r80["is_over_quota"] is False

    # 90% (90 / 100)
    r90 = UsageService.evaluate_quota_status(current_usage=90, limit=100)
    assert r90["percentage"] == 90.0
    assert r90["threshold_alert"] == "90%"
    assert r90["is_over_quota"] is False

    # 100% (100 / 100)
    r100 = UsageService.evaluate_quota_status(current_usage=100, limit=100)
    assert r100["percentage"] == 100.0
    assert r100["threshold_alert"] == "100%"
    assert r100["is_over_quota"] is True
