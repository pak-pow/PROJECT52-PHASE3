"""Unit tests for InvoiceService numbering, settlement, and lifecycle operations."""

import sqlite3
from datetime import datetime, timezone

import pytest

from app.billing.invoice_service import InvoiceService
from app.billing.proration import ProrationResult
from app.models.schemas import InvoiceStatus
from data.seed import seed_demo_user


@pytest.fixture
def invoice_service(db_conn: sqlite3.Connection) -> InvoiceService:
    seed_demo_user(db_conn)
    return InvoiceService(db_conn)


def test_sequential_invoice_numbering(invoice_service: InvoiceService):
    """Verify sequential numbering creates incrementing INV-YYYY-XXXX codes."""
    now = datetime(2026, 11, 2, 0, 0, 0, tzinfo=timezone.utc)
    num1 = invoice_service._generate_invoice_number(now)
    # Demo seed created INV-2026-0001, so next should be INV-2026-0002
    assert num1 == "INV-2026-0002"

    inv = invoice_service.create_invoice(
        user_id="usr_demo_alice",
        subscription_id="sub_demo_alice_pro",
        line_items=[{"unit_amount_cents": 1000, "quantity": 1}],
    )
    assert inv.invoice_number == "INV-2026-0002"

    num2 = invoice_service._generate_invoice_number(now)
    assert num2 == "INV-2026-0003"


def test_create_auto_pay_invoice(invoice_service: InvoiceService):
    """Verify auto_pay immediately settles invoice with paid status."""
    inv = invoice_service.create_invoice(
        user_id="usr_demo_alice",
        subscription_id="sub_demo_alice_pro",
        line_items=[{"unit_amount_cents": 4900, "quantity": 1}],
        auto_pay=True,
    )
    assert inv.status == InvoiceStatus.PAID.value
    assert inv.amount_paid_cents == 4900
    assert inv.paid_at is not None
    assert inv.payment_attempt_count == 1


def test_create_open_invoice(invoice_service: InvoiceService):
    """Verify non auto-pay invoice creates OPEN status and 0 amount paid."""
    inv = invoice_service.create_invoice(
        user_id="usr_demo_alice",
        subscription_id="sub_demo_alice_pro",
        line_items=[{"unit_amount_cents": 4900, "quantity": 1}],
        auto_pay=False,
    )
    assert inv.status == InvoiceStatus.OPEN.value
    assert inv.amount_paid_cents == 0
    assert inv.paid_at is None


def test_create_proration_invoice(invoice_service: InvoiceService):
    """Verify creating invoice from ProrationResult embeds line items."""
    proration = ProrationResult(
        current_plan_id="plan_starter",
        new_plan_id="plan_pro",
        current_plan_name="Starter",
        new_plan_name="Pro",
        current_price_cents=1900,
        new_price_cents=4900,
        billing_interval="monthly",
        period_start="2026-11-01 00:00:00",
        period_end="2026-12-01 00:00:00",
        effective_timestamp="2026-11-15 00:00:00",
        total_period_seconds=2592000.0,
        remaining_seconds=1296000.0,
        remaining_ratio=0.5,
        unused_credit_cents=950,
        new_plan_charge_cents=2450,
        net_amount_due_cents=1500,
        credit_remaining_cents=0,
        is_upgrade=True,
    )

    inv = invoice_service.create_proration_invoice(
        user_id="usr_demo_alice",
        subscription_id="sub_demo_alice_pro",
        proration_result=proration,
    )

    assert inv.amount_due_cents == 1500
    assert len(inv.line_items) == 2
    assert inv.status == InvoiceStatus.PAID.value


def test_mark_as_paid(invoice_service: InvoiceService):
    """Verify marking an open invoice as paid sets settlement timestamps."""
    inv = invoice_service.create_invoice(
        user_id="usr_demo_alice",
        subscription_id="sub_demo_alice_pro",
        line_items=[{"unit_amount_cents": 2000, "quantity": 1}],
        auto_pay=False,
    )
    paid_inv = invoice_service.mark_as_paid(inv.id)
    assert paid_inv.status == InvoiceStatus.PAID.value
    assert paid_inv.amount_paid_cents == 2000
    assert paid_inv.paid_at is not None


def test_mark_as_failed_and_uncollectible(invoice_service: InvoiceService):
    """Verify repeated failed attempts transition invoice to UNCOLLECTIBLE."""
    inv = invoice_service.create_invoice(
        user_id="usr_demo_alice",
        subscription_id="sub_demo_alice_pro",
        line_items=[{"unit_amount_cents": 2000, "quantity": 1}],
        auto_pay=False,
    )

    # Attempt 1
    f1 = invoice_service.mark_as_failed(inv.id)
    assert f1.status == InvoiceStatus.OPEN.value
    assert f1.payment_attempt_count == 1

    # Attempt 2
    f2 = invoice_service.mark_as_failed(inv.id)
    assert f2.status == InvoiceStatus.UNCOLLECTIBLE.value
    assert f2.payment_attempt_count == 2


def test_void_invoice(invoice_service: InvoiceService):
    """Verify voiding an invoice sets VOID status."""
    inv = invoice_service.create_invoice(
        user_id="usr_demo_alice",
        subscription_id="sub_demo_alice_pro",
        line_items=[{"unit_amount_cents": 2000, "quantity": 1}],
        auto_pay=False,
    )
    voided = invoice_service.void_invoice(inv.id)
    assert voided.status == InvoiceStatus.VOID.value


def test_get_invoices_by_user(invoice_service: InvoiceService):
    """Verify retrieving list of invoices for a user."""
    invoices = invoice_service.get_invoices_by_user("usr_demo_alice")
    assert len(invoices) >= 1
    assert any(i.invoice_number == "INV-2026-0001" for i in invoices)


def test_nonexistent_invoice_operations(invoice_service: InvoiceService):
    """Verify operations on non-existent invoice return None or raise ValueError."""
    assert invoice_service.get_invoice_by_id("inv_does_not_exist") is None

    with pytest.raises(ValueError):
        invoice_service.mark_as_paid("inv_does_not_exist")

    with pytest.raises(ValueError):
        invoice_service.mark_as_failed("inv_does_not_exist")

    with pytest.raises(ValueError):
        invoice_service.void_invoice("inv_does_not_exist")
