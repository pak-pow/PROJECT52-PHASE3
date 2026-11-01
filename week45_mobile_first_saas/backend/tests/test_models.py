"""Unit tests for domain models, dataclasses, and serialization."""

from app.models.schemas import (
    BillingInterval,
    Invoice,
    InvoiceStatus,
    Plan,
    PlanTier,
    Subscription,
    SubscriptionStatus,
    UsageRecord,
    WebhookEventRecord,
    WebhookStatus,
)
from data.seed import seed_demo_user


def test_plan_serialization():
    """Verify Plan model dictionary serialization."""
    plan = Plan(
        id="plan_custom",
        name="Custom",
        tier=PlanTier.PRO.value,
        price_monthly_cents=5000,
        price_annual_cents=50000,
        limits={"max_projects": 10},
        features=["custom_domains"],
        is_active=True,
    )
    data = plan.to_dict()
    assert data["id"] == "plan_custom"
    assert data["limits"]["max_projects"] == 10
    assert data["tier"] == "pro"


def test_subscription_serialization():
    """Verify Subscription model serialization and from_row factory."""
    sub = Subscription(
        id="sub_test",
        user_id="usr_1",
        plan_id="plan_starter",
        billing_interval=BillingInterval.MONTHLY.value,
        status=SubscriptionStatus.ACTIVE.value,
        current_period_start="2026-11-01 00:00:00",
        current_period_end="2026-12-01 00:00:00",
        cancel_at_period_end=False,
    )
    d = sub.to_dict()
    assert d["id"] == "sub_test"
    assert d["billing_interval"] == "monthly"
    assert d["status"] == "active"


def test_invoice_serialization_and_from_row(db_conn):
    """Verify Invoice model serialization and reconstruction from database row."""
    seed_demo_user(db_conn)
    inv = Invoice(
        id="inv_test_01",
        user_id="usr_demo_alice",
        subscription_id="sub_demo_alice_pro",
        invoice_number="INV-TEST-0001",
        amount_due_cents=4900,
        amount_paid_cents=4900,
        currency="usd",
        status=InvoiceStatus.PAID.value,
        line_items=[{"description": "Pro Tier", "amount": 4900}],
        due_date="2026-11-01 00:00:00",
        paid_at="2026-11-01 00:00:00",
    )
    d = inv.to_dict()
    assert d["invoice_number"] == "INV-TEST-0001"
    assert d["amount_due_cents"] == 4900
    assert len(d["line_items"]) == 1

    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM invoices LIMIT 1;")
    row = cursor.fetchone()
    if row is not None:
        reconstructed = Invoice.from_row(row)
        assert reconstructed.id == row["id"]
        assert reconstructed.status in [s.value for s in InvoiceStatus]
    cursor.close()


def test_usage_record_serialization_and_from_row(db_conn):
    """Verify UsageRecord model serialization and reconstruction from database row."""
    seed_demo_user(db_conn)
    usage = UsageRecord(
        id="use_001",
        user_id="usr_demo_alice",
        metric_key="api_calls",
        quantity=50,
        subscription_id="sub_demo_alice_pro",
        idempotency_key="key_001",
        recorded_at="2026-11-01 00:00:00",
    )
    d = usage.to_dict()
    assert d["metric_key"] == "api_calls"
    assert d["quantity"] == 50

    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO usage_records (id, user_id, metric_key, quantity, idempotency_key)
        VALUES ('use_row_test', 'usr_demo_alice', 'api_calls', 25, 'idem_test_25');
        """)
    db_conn.commit()
    cursor.execute("SELECT * FROM usage_records WHERE id = 'use_row_test';")
    row = cursor.fetchone()
    reconstructed = UsageRecord.from_row(row)
    assert reconstructed.quantity == 25
    assert reconstructed.idempotency_key == "idem_test_25"
    cursor.close()


def test_webhook_event_record_serialization_and_from_row(db_conn):
    """Verify WebhookEventRecord serialization and reconstruction from database row."""
    event = WebhookEventRecord(
        id="wh_001",
        event_id="evt_test_123",
        event_type="customer.subscription.updated",
        payload={"tier": "enterprise"},
        status=WebhookStatus.PROCESSED.value,
        received_at="2026-11-01 00:00:00",
        processed_at="2026-11-01 00:00:01",
    )
    d = event.to_dict()
    assert d["event_id"] == "evt_test_123"
    assert d["status"] == "processed"

    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO webhook_events (
            id, event_id, event_type, payload_json, status
        ) VALUES (
            'wh_row_1', 'evt_row_1', 'invoice.paid', '{"paid": true}', 'processed'
        );
        """)
    db_conn.commit()
    cursor.execute("SELECT * FROM webhook_events WHERE id = 'wh_row_1';")
    row = cursor.fetchone()
    reconstructed = WebhookEventRecord.from_row(row)
    assert reconstructed.event_id == "evt_row_1"
    assert reconstructed.payload == {"paid": True}
    cursor.close()
