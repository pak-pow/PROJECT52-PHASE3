"""End-to-end subscriber lifecycle, concurrency, and webhook chaos test suite."""

import concurrent.futures
import json
import time
from pathlib import Path

import pytest

from app import create_app
from app.billing.webhook_security import generate_webhook_signature
from app.db.connection import get_db_connection, init_db
from app.services.usage_service import UsageService
from data.seed import seed_demo_user


@pytest.fixture
def e2e_env(tmp_path: Path):
    """Create Flask application and client with an isolated temporary database."""
    db_file = tmp_path / "test_e2e_lifecycle.db"
    init_db(db_path=db_file, seed_defaults=True)

    app_instance = create_app(
        {
            "TESTING": True,
            "DB_PATH": str(db_file),
            "SECRET_KEY": "e2e_test_secret_key_2026",
            "WEBHOOK_SIGNING_SECRET": "whsec_e2e_chaos_secret_2026",
        }
    )
    with app_instance.test_client() as test_client:
        yield test_client, app_instance, db_file


def test_end_to_end_subscriber_lifecycle(e2e_env):
    """Execute complete subscriber journey: registration, tier change, cancel."""
    client, app, _ = e2e_env
    secret = app.config["WEBHOOK_SIGNING_SECRET"]

    # 1. Register a new user
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "diana@pulsesub.io",
            "password": "DianaPassword2026!",
            "full_name": "Diana Prince",
        },
    )
    assert reg_res.status_code == 201
    reg_data = reg_res.get_json()
    token = reg_data["token"]
    user_id = reg_data["user"]["id"]
    auth_headers = {
        "Authorization": f"Bearer {token}",
        "X-User-ID": user_id,
    }

    # 2. Check initial subscription state (defaults to Free tier)
    sub_res = client.get("/api/v1/subscriptions/current", headers=auth_headers)
    assert sub_res.status_code == 200
    sub_data = sub_res.get_json()
    assert sub_data["plan"]["tier"] == "free"
    assert sub_data["subscription"] is None
    assert sub_data["is_active"] is False

    # 3. Verify initial entitlements via /my-features
    ent_res = client.get("/api/v1/entitlements/my-features", headers=auth_headers)
    assert ent_res.status_code == 200
    ent_data = ent_res.get_json()
    assert ent_data["limits"]["monthly_api_calls"] == 100
    assert ent_data["limits"]["team_seats"] == 1
    assert ent_data["limits"]["storage_mb"] == 50
    assert "basic_analytics" in ent_data["features"]
    assert "custom_domains" not in ent_data["features"]

    # Check individual feature check
    chk_res = client.get(
        "/api/v1/entitlements/check?feature=custom_domains",
        headers=auth_headers,
    )
    assert chk_res.status_code == 200
    assert chk_res.get_json()["allowed"] is False

    # 4. Record metered resource consumption and verify threshold alerts
    # 75 calls -> 75% (normal)
    r1 = client.post(
        "/api/v1/usage/record",
        headers=auth_headers,
        json={"metric_key": "monthly_api_calls", "quantity": 75},
    )
    assert r1.status_code == 201
    assert r1.headers["X-Quota-Alert"] == "normal"

    # 10 calls -> 85 calls total (85%, threshold >= 80% warning)
    r2 = client.post(
        "/api/v1/usage/record",
        headers=auth_headers,
        json={"metric_key": "monthly_api_calls", "quantity": 10},
    )
    assert r2.status_code == 201
    assert r2.headers["X-Quota-Alert"] == "80%"

    # 6 calls -> 91 calls total (91%, threshold >= 90% critical)
    r3 = client.post(
        "/api/v1/usage/record",
        headers=auth_headers,
        json={"metric_key": "monthly_api_calls", "quantity": 6},
    )
    assert r3.status_code == 201
    assert r3.headers["X-Quota-Alert"] == "90%"

    # 10 calls -> 101 calls total (101%, threshold >= 100% exceeded)
    r4 = client.post(
        "/api/v1/usage/record",
        headers=auth_headers,
        json={"metric_key": "monthly_api_calls", "quantity": 10},
    )
    assert r4.status_code == 201
    assert r4.headers["X-Quota-Alert"] == "100%"

    # Verify summary reflects usage and alert
    summary_res = client.get("/api/v1/usage/summary", headers=auth_headers)
    assert summary_res.status_code == 200
    s_data = summary_res.get_json()["usage_summary"]["monthly_api_calls"]
    assert s_data["usage"] == 101
    assert s_data["threshold_alert"] == "100%"

    # 5. Subscribe to Pro Monthly tier
    sub_create_res = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=auth_headers,
        json={"plan_id": "plan_pro", "billing_interval": "monthly"},
    )
    assert sub_create_res.status_code == 201
    created_sub = sub_create_res.get_json()["subscription"]
    sub_id = created_sub["id"]
    assert created_sub["status"] == "active"
    assert created_sub["plan_id"] == "plan_pro"

    # Verify entitlements expanded
    ent_pro = client.get(
        "/api/v1/entitlements/my-features",
        headers=auth_headers,
    ).get_json()
    assert ent_pro["limits"]["monthly_api_calls"] == 50000
    assert ent_pro["limits"]["team_seats"] == 5
    assert "custom_domains" in ent_pro["features"]

    # 6. Preview proration upgrade to Enterprise Annual
    preview_res = client.post(
        "/api/v1/subscriptions/change-tier",
        headers=auth_headers,
        json={
            "new_plan_id": "plan_enterprise",
            "new_interval": "annual",
            "preview_only": True,
        },
    )
    assert preview_res.status_code == 200
    proration_preview = preview_res.get_json()["proration"]
    assert proration_preview["unused_credit_cents"] >= 0
    assert proration_preview["new_plan_charge_cents"] > 0
    assert proration_preview["net_amount_due_cents"] > 0

    # 7. Execute upgrade to Enterprise Annual
    upgrade_res = client.post(
        "/api/v1/subscriptions/change-tier",
        headers=auth_headers,
        json={
            "new_plan_id": "plan_enterprise",
            "new_interval": "annual",
            "preview_only": False,
        },
    )
    assert upgrade_res.status_code == 200
    upgraded_sub = upgrade_res.get_json()["subscription"]
    sub_id = upgraded_sub["id"]
    assert upgraded_sub["plan_id"] == "plan_enterprise"
    assert upgraded_sub["billing_interval"] == "annual"

    # Verify invoice was issued for upgrade
    invoices_res = client.get("/api/v1/billing/invoices", headers=auth_headers)
    assert invoices_res.status_code == 200
    inv_list = invoices_res.get_json()["invoices"]
    assert len(inv_list) >= 2
    latest_inv_id = inv_list[0]["id"]

    # Verify structured receipt JSON
    receipt_res = client.get(
        f"/api/v1/billing/invoices/{latest_inv_id}/receipt",
        headers=auth_headers,
    )
    assert receipt_res.status_code == 200
    assert "customer_email" in receipt_res.get_json()

    # Verify printable HTML invoice
    html_res = client.get(
        f"/api/v1/billing/invoices/{latest_inv_id}/html",
        headers=auth_headers,
    )
    assert html_res.status_code == 200
    assert "<!DOCTYPE html>" in html_res.get_data(as_text=True)

    # 8. Webhook billing lifecycle: invoice.payment_failed -> past_due
    fail_payload = json.dumps(
        {
            "id": "evt_e2e_fail_001",
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": latest_inv_id,
                    "subscription": sub_id,
                }
            },
        }
    )
    fail_sig = generate_webhook_signature(
        fail_payload, secret, timestamp=int(time.time())
    )
    wh_fail_res = client.post(
        "/api/v1/webhooks/stripe",
        data=fail_payload,
        headers={"Stripe-Signature": fail_sig},
        content_type="application/json",
    )
    assert wh_fail_res.status_code == 200

    # Subscription must now be past_due
    curr_sub_res = client.get("/api/v1/subscriptions/current", headers=auth_headers)
    assert curr_sub_res.get_json()["subscription"]["status"] == "past_due"

    # 9. Webhook recovery: invoice.paid -> active
    paid_payload = json.dumps(
        {
            "id": "evt_e2e_paid_001",
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": latest_inv_id,
                    "subscription": sub_id,
                }
            },
        }
    )
    paid_sig = generate_webhook_signature(
        paid_payload, secret, timestamp=int(time.time())
    )
    wh_paid_res = client.post(
        "/api/v1/webhooks/stripe",
        data=paid_payload,
        headers={"Stripe-Signature": paid_sig},
        content_type="application/json",
    )
    assert wh_paid_res.status_code == 200

    # Subscription restored to active
    restored_res = client.get("/api/v1/subscriptions/current", headers=auth_headers)
    assert restored_res.get_json()["subscription"]["status"] == "active"

    # 10. Cancellation lifecycle: schedule at period end -> resume -> immediate cancel
    cancel_sched_res = client.post(
        "/api/v1/subscriptions/cancel",
        headers=auth_headers,
        json={"immediate": False},
    )
    assert cancel_sched_res.status_code == 200
    sched_sub = cancel_sched_res.get_json()["subscription"]
    assert sched_sub["status"] == "active"
    assert sched_sub["cancel_at_period_end"] is True

    # Resume
    resume_res = client.post(
        "/api/v1/subscriptions/resume",
        headers=auth_headers,
        json={},
    )
    assert resume_res.status_code == 200
    resumed_sub = resume_res.get_json()["subscription"]
    assert resumed_sub["cancel_at_period_end"] is False
    assert resumed_sub["status"] == "active"

    # Cancel immediately
    cancel_imm_res = client.post(
        "/api/v1/subscriptions/cancel",
        headers=auth_headers,
        json={"immediate": True},
    )
    assert cancel_imm_res.status_code == 200
    assert cancel_imm_res.get_json()["subscription"]["status"] == "canceled"

    # Entitlements revert to Free tier
    ent_canceled = client.get(
        "/api/v1/entitlements/my-features",
        headers=auth_headers,
    ).get_json()
    assert ent_canceled["plan"]["tier"] == "free"
    assert ent_canceled["limits"]["monthly_api_calls"] == 100


def test_wal_multithreaded_concurrency_stress(tmp_path: Path):
    """Verify SQLite WAL mode concurrency under 50 simultaneous worker threads."""
    stress_db = tmp_path / "wal_stress_test.db"
    init_db(db_path=stress_db, seed_defaults=True)

    # Seed demo user
    conn = get_db_connection(stress_db)
    seed_demo_user(conn)
    initial_service = UsageService(conn)
    initial_usage = initial_service.get_user_metric_usage(
        "usr_demo_alice", "monthly_api_calls"
    )
    conn.close()

    total_threads = 50
    increment_per_thread = 5
    user_id = "usr_demo_alice"
    metric_key = "monthly_api_calls"

    def record_worker(worker_idx: int) -> int:
        worker_conn = get_db_connection(stress_db)
        try:
            service = UsageService(worker_conn)
            service.record_usage(
                user_id=user_id,
                metric_key=metric_key,
                quantity=increment_per_thread,
                idempotency_key=f"idem_stress_{worker_idx}",
            )
            return increment_per_thread
        finally:
            worker_conn.close()

    # Launch 50 concurrent worker threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = [executor.submit(record_worker, i) for i in range(total_threads)]
        results = [
            future.result(timeout=15.0)
            for future in concurrent.futures.as_completed(futures)
        ]

    assert len(results) == total_threads
    assert sum(results) == total_threads * increment_per_thread

    # Verify exact sum in database
    verify_conn = get_db_connection(stress_db)
    try:
        service = UsageService(verify_conn)
        accumulated = service.get_user_metric_usage(user_id, metric_key)
        assert accumulated == initial_usage + (total_threads * increment_per_thread)
    finally:
        verify_conn.close()


def test_webhook_security_chaos_and_idempotency(e2e_env):
    """Execute chaos edge cases on Stripe webhook verification and idempotency."""
    client, app, _ = e2e_env
    secret = app.config["WEBHOOK_SIGNING_SECRET"]
    valid_payload = json.dumps(
        {
            "id": "evt_chaos_test_001",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_demo_alice_pro"}},
        }
    )

    # 1. Missing signature header -> 400
    res_missing = client.post(
        "/api/v1/webhooks/stripe",
        data=valid_payload,
        content_type="application/json",
    )
    assert res_missing.status_code == 400
    assert res_missing.get_json()["error"] == "missing_signature"

    # 2. Tampered signature (payload altered after signature generated) -> 400
    correct_sig = generate_webhook_signature(
        valid_payload, secret, timestamp=int(time.time())
    )
    tampered_payload = valid_payload.replace("sub_demo_alice_pro", "sub_hacked")
    res_tampered = client.post(
        "/api/v1/webhooks/stripe",
        data=tampered_payload,
        headers={"Stripe-Signature": correct_sig},
        content_type="application/json",
    )
    assert res_tampered.status_code == 400
    assert res_tampered.get_json()["error"] == "invalid_signature"

    # 3. Expired timestamp (> 300 seconds ago) -> 400
    stale_timestamp = int(time.time()) - 600
    stale_sig = generate_webhook_signature(
        valid_payload, secret, timestamp=stale_timestamp
    )
    res_stale = client.post(
        "/api/v1/webhooks/stripe",
        data=valid_payload,
        headers={"Stripe-Signature": stale_sig},
        content_type="application/json",
    )
    assert res_stale.status_code == 400
    assert res_stale.get_json()["error"] == "invalid_signature"

    # 4. Malformed signature header format -> 400
    res_malformed = client.post(
        "/api/v1/webhooks/stripe",
        data=valid_payload,
        headers={"Stripe-Signature": "t=not_a_number,v1=bad_hash"},
        content_type="application/json",
    )
    assert res_malformed.status_code == 400
    assert res_malformed.get_json()["error"] == "invalid_signature"

    # 5. Idempotent duplicate event delivery
    event_id = "evt_chaos_idempotent_042"
    idem_payload = json.dumps(
        {
            "id": event_id,
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_demo_alice_pro",
                    "cancel_at_period_end": True,
                }
            },
        }
    )
    idem_sig = generate_webhook_signature(
        idem_payload, secret, timestamp=int(time.time())
    )

    # First delivery: processed
    res_first = client.post(
        "/api/v1/webhooks/stripe",
        data=idem_payload,
        headers={"Stripe-Signature": idem_sig},
        content_type="application/json",
    )
    assert res_first.status_code == 200
    assert res_first.get_json()["status"] == "processed"

    # Second delivery: deduplicated idempotently without reprocessing
    res_second = client.post(
        "/api/v1/webhooks/stripe",
        data=idem_payload,
        headers={"Stripe-Signature": idem_sig},
        content_type="application/json",
    )
    assert res_second.status_code == 200
    assert res_second.get_json()["status"] == "already_processed"

    # 6. Unknown / unhandled event type gracefully handled -> 200
    unhandled_payload = json.dumps(
        {
            "id": "evt_chaos_unhandled_999",
            "type": "account.external_account.created",
            "data": {"object": {}},
        }
    )
    unhandled_sig = generate_webhook_signature(
        unhandled_payload, secret, timestamp=int(time.time())
    )
    res_unhandled = client.post(
        "/api/v1/webhooks/stripe",
        data=unhandled_payload,
        headers={"Stripe-Signature": unhandled_sig},
        content_type="application/json",
    )
    assert res_unhandled.status_code == 200
    assert res_unhandled.get_json()["status"] == "processed"
    assert res_unhandled.get_json()["result"]["action"] == "unhandled_event"
