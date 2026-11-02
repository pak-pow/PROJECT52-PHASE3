"""Unit tests for EntitlementsService plan resolution, features, and limits."""

import sqlite3

import pytest

from app.services.entitlements_service import EntitlementsService
from data.seed import seed_demo_user


@pytest.fixture
def entitlements_service(db_conn: sqlite3.Connection) -> EntitlementsService:
    seed_demo_user(db_conn)
    return EntitlementsService(db_conn)


def test_get_active_subscription_demo_user(
    entitlements_service: EntitlementsService,
):
    """Verify demo user Alice resolves her active Pro subscription."""
    sub = entitlements_service.get_active_subscription("usr_demo_alice")
    assert sub is not None
    assert sub.plan_id == "plan_pro"
    assert sub.status == "active"


def test_get_user_plan_subscribed_and_free(
    entitlements_service: EntitlementsService,
):
    """Verify subscriber resolves Pro plan, while guest resolves Free plan."""
    # Alice (Pro)
    plan_alice, sub_alice = entitlements_service.get_user_plan("usr_demo_alice")
    assert plan_alice.tier == "pro"
    assert sub_alice is not None

    # Unknown or non-subscriber (Free fallback)
    plan_anon, sub_anon = entitlements_service.get_user_plan("usr_unknown_guest")
    assert plan_anon.tier == "free"
    assert sub_anon is None


def test_check_feature_access(entitlements_service: EntitlementsService):
    """Verify feature flag entitlement checks against tier configuration."""
    # Alice on Pro has custom domains, export data, basic analytics
    assert (
        entitlements_service.check_feature_access("usr_demo_alice", "custom_domains")
        is True
    )
    assert (
        entitlements_service.check_feature_access("usr_demo_alice", "export_data")
        is True
    )
    # Alice on Pro does NOT have enterprise features (e.g., sso, dedicated_sla)
    assert entitlements_service.check_feature_access("usr_demo_alice", "sso") is False

    # Unsubscribed user on Free plan
    assert (
        entitlements_service.check_feature_access("usr_free_user", "basic_analytics")
        is True
    )
    assert (
        entitlements_service.check_feature_access("usr_free_user", "custom_domains")
        is False
    )


def test_can_consume_metric(entitlements_service: EntitlementsService):
    """Verify metric consumption checks against plan limits."""
    # Alice has unlimited projects on Pro (-1)
    allowed, data = entitlements_service.can_consume_metric(
        "usr_demo_alice", "max_projects", requested_units=10
    )
    assert allowed is True
    assert data["unlimited"] is True

    # Alice has 50,000 monthly API calls. 1420 used in seed.
    allowed_api, api_data = entitlements_service.can_consume_metric(
        "usr_demo_alice", "monthly_api_calls", requested_units=500
    )
    assert allowed_api is True
    assert api_data["usage"] >= 1420

    # Requesting over the remaining limit fails
    allowed_excess, _ = entitlements_service.can_consume_metric(
        "usr_demo_alice", "monthly_api_calls", requested_units=60000
    )
    assert allowed_excess is False


def test_get_user_entitlements_snapshot(
    entitlements_service: EntitlementsService,
):
    """Verify comprehensive user entitlements diagnostic payload."""
    snapshot = entitlements_service.get_user_entitlements("usr_demo_alice")
    assert snapshot["user_id"] == "usr_demo_alice"
    assert snapshot["plan"]["tier"] == "pro"
    assert "custom_domains" in snapshot["features"]
    assert "monthly_api_calls" in snapshot["usage_summary"]
    assert "max_projects" in snapshot["usage_summary"]
