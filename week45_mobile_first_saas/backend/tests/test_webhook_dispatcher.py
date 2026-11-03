"""Unit tests for WebhookDispatcher event routing and idempotent deduplication."""

import sqlite3

import pytest

from app.billing.webhook_dispatcher import WebhookDispatcher
from app.models.schemas import SubscriptionStatus
from data.seed import seed_demo_user


@pytest.fixture
def dispatcher(db_conn: sqlite3.Connection) -> WebhookDispatcher:
    seed_demo_user(db_conn)
    return WebhookDispatcher(db_conn)


def test_dispatch_subscription_created(
    dispatcher: WebhookDispatcher, db_conn: sqlite3.Connection
):
    """Verify customer.subscription.created inserts new subscription."""
    payload = {
        "id": "evt_sub_created_01",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_wh_new_01",
                "customer": "usr_demo_alice",
                "plan": {"id": "plan_enterprise"},
                "interval": "annual",
                "current_period_start": "2026-11-01 00:00:00",
                "current_period_end": "2027-11-01 00:00:00",
            }
        },
    }

    res = dispatcher.dispatch(
        "evt_sub_created_01", "customer.subscription.created", payload
    )
    assert res["status"] == "processed"

    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM subscriptions WHERE id = 'sub_wh_new_01';")
    row = cursor.fetchone()
    assert row is not None
    assert row["plan_id"] == "plan_enterprise"
    assert row["billing_interval"] == "annual"
    cursor.close()


def test_dispatch_subscription_updated_tier_and_status(
    dispatcher: WebhookDispatcher, db_conn: sqlite3.Connection
):
    """Verify customer.subscription.updated adjusts tier, interval, and status."""
    payload = {
        "id": "evt_sub_updated_01",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_demo_alice_pro",
                "plan": {"id": "plan_starter"},
                "interval": "monthly",
                "status": "past_due",
            }
        },
    }

    res = dispatcher.dispatch(
        "evt_sub_updated_01", "customer.subscription.updated", payload
    )
    assert res["status"] == "processed"

    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM subscriptions WHERE id = 'sub_demo_alice_pro';")
    row = cursor.fetchone()
    assert row["plan_id"] == "plan_starter"
    assert row["status"] == "past_due"
    cursor.close()


def test_dispatch_subscription_deleted(
    dispatcher: WebhookDispatcher, db_conn: sqlite3.Connection
):
    """Verify customer.subscription.deleted cancels active subscription."""
    payload = {
        "id": "evt_sub_deleted_01",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_demo_alice_pro",
            }
        },
    }

    res = dispatcher.dispatch(
        "evt_sub_deleted_01", "customer.subscription.deleted", payload
    )
    assert res["status"] == "processed"

    cursor = db_conn.cursor()
    cursor.execute("SELECT status FROM subscriptions WHERE id = 'sub_demo_alice_pro';")
    row = cursor.fetchone()
    assert row["status"] == SubscriptionStatus.CANCELED.value
    cursor.close()


def test_dispatch_invoice_paid_reactivates_past_due(
    dispatcher: WebhookDispatcher, db_conn: sqlite3.Connection
):
    """Verify invoice.paid marks invoice as paid and reactivates subscription."""
    # First set subscription to past_due
    cursor = db_conn.cursor()
    cursor.execute(
        "UPDATE subscriptions SET status = 'past_due' WHERE id = 'sub_demo_alice_pro';"
    )
    db_conn.commit()

    payload = {
        "id": "evt_inv_paid_01",
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": "inv_demo_2026_0001",
                "subscription": "sub_demo_alice_pro",
            }
        },
    }

    res = dispatcher.dispatch("evt_inv_paid_01", "invoice.paid", payload)
    assert res["status"] == "processed"

    cursor.execute("SELECT status FROM subscriptions WHERE id = 'sub_demo_alice_pro';")
    row = cursor.fetchone()
    assert row["status"] == SubscriptionStatus.ACTIVE.value
    cursor.close()


def test_dispatch_invoice_payment_failed(
    dispatcher: WebhookDispatcher, db_conn: sqlite3.Connection
):
    """Verify invoice.payment_failed marks invoice as failed and status past_due."""
    payload = {
        "id": "evt_inv_failed_01",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "id": "inv_demo_2026_0001",
                "subscription": "sub_demo_alice_pro",
            }
        },
    }

    res = dispatcher.dispatch("evt_inv_failed_01", "invoice.payment_failed", payload)
    assert res["status"] == "processed"

    cursor = db_conn.cursor()
    cursor.execute("SELECT status FROM subscriptions WHERE id = 'sub_demo_alice_pro';")
    sub_row = cursor.fetchone()
    assert sub_row["status"] == SubscriptionStatus.PAST_DUE.value

    cursor.execute(
        "SELECT payment_attempt_count FROM invoices WHERE id = 'inv_demo_2026_0001';"
    )
    inv_row = cursor.fetchone()
    assert inv_row["payment_attempt_count"] >= 2
    cursor.close()


def test_dispatch_idempotency_duplicate_events(dispatcher: WebhookDispatcher):
    """Verify re-sending event with identical event_id returns already_processed."""
    payload = {
        "id": "evt_idem_001",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_demo_alice_pro",
                "cancel_at_period_end": True,
            }
        },
    }

    # First dispatch
    res1 = dispatcher.dispatch("evt_idem_001", "customer.subscription.updated", payload)
    assert res1["status"] == "processed"

    # Second dispatch with identical ID
    res2 = dispatcher.dispatch("evt_idem_001", "customer.subscription.updated", payload)
    assert res2["status"] == "already_processed"
    assert res2["event_id"] == "evt_idem_001"


def test_dispatch_unhandled_event(dispatcher: WebhookDispatcher):
    """Verify unhandled event types process safely with unhandled_event action."""
    payload = {
        "id": "evt_unknown_999",
        "type": "charge.dispute.created",
        "data": {"object": {}},
    }
    res = dispatcher.dispatch("evt_unknown_999", "charge.dispute.created", payload)
    assert res["status"] == "processed"
    assert res["result"]["action"] == "unhandled_event"
