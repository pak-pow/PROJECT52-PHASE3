"""Integration tests for billing, invoices, receipts, and HTML generation."""

import pytest

from app import create_app
from app.db.connection import get_db_connection, init_db
from app.models.schemas import SubscriptionStatus
from data.seed import seed_demo_user


@pytest.fixture
def bill_client(tmp_path):
    """Create Flask test client with an isolated temporary SQLite database."""
    test_db = tmp_path / "test_billing_routes.db"
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
        yield client, test_db


def test_list_invoices_for_user(bill_client):
    """Verify listing invoices returns user's historical statements."""
    client, _ = bill_client
    res = client.get(
        "/api/v1/billing/invoices",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "invoices" in data
    assert data["total"] >= 1
    assert data["invoices"][0]["user_id"] == "usr_demo_alice"


def test_get_invoice_detail(bill_client):
    """Verify retrieving single invoice details by ID."""
    client, _ = bill_client
    list_res = client.get(
        "/api/v1/billing/invoices",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    invoice_id = list_res.get_json()["invoices"][0]["id"]

    res = client.get(
        f"/api/v1/billing/invoices/{invoice_id}",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["invoice"]["id"] == invoice_id
    assert "amount_due_cents" in data["invoice"]


def test_get_invoice_receipt_json(bill_client):
    """Verify structured receipt JSON endpoint returns customer and line items."""
    client, _ = bill_client
    list_res = client.get(
        "/api/v1/billing/invoices",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    invoice_id = list_res.get_json()["invoices"][0]["id"]

    res = client.get(
        f"/api/v1/billing/invoices/{invoice_id}/receipt",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "invoice_number" in data
    assert data["customer_email"] == "alice@pulsesub.io"
    assert "amount_paid_formatted" in data


def test_get_invoice_html_receipt(bill_client):
    """Verify printable HTML receipt generation returns valid HTML with print styles."""
    client, _ = bill_client
    list_res = client.get(
        "/api/v1/billing/invoices",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    invoice_id = list_res.get_json()["invoices"][0]["id"]

    res = client.get(
        f"/api/v1/billing/invoices/{invoice_id}/html",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res.status_code == 200
    assert "text/html" in res.content_type
    html_text = res.get_data(as_text=True)
    assert "<!DOCTYPE html>" in html_text
    assert "PulseSub" in html_text
    assert "@media print" in html_text
    assert "window.print()" in html_text


def test_get_nonexistent_invoice_returns_404(bill_client):
    """Verify non-existent invoice ID returns 404 for JSON and HTML."""
    client, _ = bill_client
    res_json = client.get(
        "/api/v1/billing/invoices/inv_fake",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res_json.status_code == 404

    res_html = client.get(
        "/api/v1/billing/invoices/inv_fake/html",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res_html.status_code == 404


def test_pay_invoice_and_reactivate_subscription(bill_client):
    """Verify paying open invoice settles it and reactivates past_due subscription."""
    client, test_db = bill_client

    # 1. Put demo subscription in past_due status and create an open invoice
    conn = get_db_connection(test_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE subscriptions SET status = ? WHERE user_id = ?;",
        (SubscriptionStatus.PAST_DUE.value, "usr_demo_alice"),
    )
    conn.commit()

    from app.billing.invoice_service import InvoiceService

    inv_service = InvoiceService(conn)
    open_inv = inv_service.create_invoice(
        user_id="usr_demo_alice",
        subscription_id="sub_demo_alice_pro",
        line_items=[{"description": "Past Due Recovery", "unit_amount_cents": 4900}],
        auto_pay=False,
    )
    conn.close()

    # 2. Pay the invoice via HTTP POST
    res = client.post(
        f"/api/v1/billing/invoices/{open_inv.id}/pay",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["invoice"]["status"] == "paid"
    assert data["subscription_reactivated"] is True

    # 3. Verify subscription is now active
    sub_res = client.get(
        "/api/v1/subscriptions/current",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert sub_res.get_json()["subscription"]["status"] == "active"
