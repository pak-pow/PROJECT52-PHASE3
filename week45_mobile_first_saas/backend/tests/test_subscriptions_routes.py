"""Integration tests for subscription management, tier changes, and proration routes."""

import pytest

from app import create_app
from app.db.connection import get_db_connection, init_db
from data.seed import seed_demo_user


@pytest.fixture
def sub_client(tmp_path):
    """Create Flask test client with an isolated temporary SQLite database."""
    test_db = tmp_path / "test_subs.db"
    init_db(db_path=test_db, seed_defaults=True)

    conn = get_db_connection(test_db)
    seed_demo_user(conn)
    conn.close()

    app = create_app(
        {
            "TESTING": True,
            "DB_PATH": test_db,
        }
    )
    with app.test_client() as client:
        yield client


def test_get_current_subscription_demo_user(sub_client):
    """Verify endpoint returns active Pro subscription for Alice."""
    res = sub_client.get(
        "/api/v1/subscriptions/current",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["subscription"]["plan_id"] == "plan_pro"
    assert data["subscription"]["status"] == "active"
    assert data["plan"]["tier"] == "pro"
    assert data["is_active"] is True
    assert data["days_remaining"] >= 0


def test_get_current_subscription_unsubscribed_user(sub_client):
    """Verify user without active subscription resolves to Free plan."""
    res = sub_client.get(
        "/api/v1/subscriptions/current",
        headers={"X-User-ID": "usr_new_unsubscribed"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["subscription"] is None
    assert data["plan"]["tier"] == "free"
    assert data["is_active"] is False


def test_subscribe_success_and_duplicate_prevention(sub_client):
    """Verify subscribing creates subscription + invoice, and duplicate returns 409."""
    reg_res = sub_client.post(
        "/api/v1/auth/register",
        json={
            "email": "buyer@pulsesub.io",
            "password": "BuyerPassword2026",
            "full_name": "Buyer User",
        },
    )
    assert reg_res.status_code == 201
    user_id = reg_res.get_json()["user"]["id"]

    # 1. First subscription succeeds
    res = sub_client.post(
        "/api/v1/subscriptions/subscribe",
        headers={"X-User-ID": user_id},
        json={
            "plan_id": "plan_starter",
            "billing_interval": "monthly",
        },
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["subscription"]["plan_id"] == "plan_starter"
    assert data["subscription"]["status"] == "active"
    assert data["invoice"]["amount_paid_cents"] == 1900
    assert data["invoice"]["status"] == "paid"

    # 2. Duplicate subscription attempt fails with 409
    res_dup = sub_client.post(
        "/api/v1/subscriptions/subscribe",
        headers={"X-User-ID": user_id},
        json={"plan_id": "plan_pro"},
    )
    assert res_dup.status_code == 409
    assert res_dup.get_json()["error"] == "already_subscribed"


def test_subscribe_validation_errors(sub_client):
    """Verify subscription validation errors (missing plan, bad interval)."""
    user_id = "usr_validator"

    # Missing plan_id
    res = sub_client.post(
        "/api/v1/subscriptions/subscribe",
        headers={"X-User-ID": user_id},
        json={},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_payload"

    # Invalid interval
    res = sub_client.post(
        "/api/v1/subscriptions/subscribe",
        headers={"X-User-ID": user_id},
        json={"plan_id": "plan_starter", "billing_interval": "weekly"},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_interval"

    # Nonexistent plan
    res = sub_client.post(
        "/api/v1/subscriptions/subscribe",
        headers={"X-User-ID": user_id},
        json={"plan_id": "plan_phantom"},
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "plan_not_found"


def test_change_tier_preview_and_execute(sub_client):
    """Verify change-tier preview calculation and actual upgrade execution."""
    user_id = "usr_demo_alice"  # Currently on Pro monthly (4900 cents)

    # 1. Preview upgrade to Enterprise
    preview_res = sub_client.post(
        "/api/v1/subscriptions/change-tier",
        headers={"X-User-ID": user_id},
        json={
            "new_plan_id": "plan_enterprise",
            "preview_only": True,
        },
    )
    assert preview_res.status_code == 200
    preview_data = preview_res.get_json()
    assert preview_data["preview_only"] is True
    assert preview_data["proration"]["new_plan_id"] == "plan_enterprise"
    assert preview_data["proration"]["is_upgrade"] is True
    assert preview_data["proration"]["net_amount_due_cents"] > 0

    # Verify database was NOT modified during preview
    current_res = sub_client.get(
        "/api/v1/subscriptions/current",
        headers={"X-User-ID": user_id},
    )
    assert current_res.get_json()["subscription"]["plan_id"] == "plan_pro"

    # 2. Execute tier change
    exec_res = sub_client.post(
        "/api/v1/subscriptions/change-tier",
        headers={"X-User-ID": user_id},
        json={
            "new_plan_id": "plan_enterprise",
            "preview_only": False,
        },
    )
    assert exec_res.status_code == 200
    exec_data = exec_res.get_json()
    assert exec_data["subscription"]["plan_id"] == "plan_enterprise"
    assert "invoice" in exec_data
    assert exec_data["invoice"]["status"] == "paid"


def test_change_tier_same_plan_and_no_subscription(sub_client):
    """Verify attempting to change to the same plan or with no subscription fails."""
    # Same plan
    res_same = sub_client.post(
        "/api/v1/subscriptions/change-tier",
        headers={"X-User-ID": "usr_demo_alice"},
        json={"new_plan_id": "plan_pro", "new_interval": "monthly"},
    )
    assert res_same.status_code == 400
    assert res_same.get_json()["error"] == "same_plan"

    # No subscription
    res_none = sub_client.post(
        "/api/v1/subscriptions/change-tier",
        headers={"X-User-ID": "usr_nobody"},
        json={"new_plan_id": "plan_pro"},
    )
    assert res_none.status_code == 404
    assert res_none.get_json()["error"] == "no_active_subscription"


def test_cancel_and_resume_subscription(sub_client):
    """Verify canceling at period end, immediate cancel, and resumption."""
    user_id = "usr_demo_alice"

    # 1. Schedule cancel at period end
    cancel_res = sub_client.post(
        "/api/v1/subscriptions/cancel",
        headers={"X-User-ID": user_id},
        json={"immediate": False},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.get_json()["subscription"]["cancel_at_period_end"] is True
    assert cancel_res.get_json()["subscription"]["status"] == "active"

    # 2. Resume scheduled cancellation
    resume_res = sub_client.post(
        "/api/v1/subscriptions/resume",
        headers={"X-User-ID": user_id},
    )
    assert resume_res.status_code == 200
    assert resume_res.get_json()["subscription"]["cancel_at_period_end"] is False

    # 3. Cancel immediately
    imm_cancel_res = sub_client.post(
        "/api/v1/subscriptions/cancel",
        headers={"X-User-ID": user_id},
        json={"immediate": True},
    )
    assert imm_cancel_res.status_code == 200
    assert imm_cancel_res.get_json()["subscription"]["status"] == "canceled"
