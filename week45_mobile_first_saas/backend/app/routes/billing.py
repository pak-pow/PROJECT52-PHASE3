"""Customer billing, invoice statements, and printable receipt routes."""

from flask import Blueprint, Response, current_app, jsonify

from app.billing.invoice_service import InvoiceService
from app.billing.subscription_fsm import SubscriptionFSM
from app.config.settings import Config
from app.db.connection import get_db_connection
from app.models.schemas import Invoice, InvoiceStatus, Subscription, SubscriptionStatus
from app.services.auth_service import AuthService
from app.services.decorators import _resolve_user_id

billing_bp = Blueprint("billing", __name__, url_prefix="/api/v1/billing")


def _format_currency(cents: int) -> str:
    """Format integer cents into a human-readable USD string."""
    is_negative = cents < 0
    abs_cents = abs(cents)
    formatted = f"${abs_cents / 100:.2f}"
    return f"-{formatted}" if is_negative else formatted


def _render_receipt_html(
    invoice: Invoice,
    user_name: str,
    user_email: str,
) -> str:
    """Render a clean, modern, print-ready HTML receipt."""
    status_class = (
        "status-paid" if invoice.status == InvoiceStatus.PAID.value else "status-open"
    )
    status_label = invoice.status.upper()
    balance_due = max(0, invoice.amount_due_cents - invoice.amount_paid_cents)
    date_str = str(invoice.created_at)[:10]

    rows_html = ""
    for item in invoice.line_items:
        desc = item.get("description", "Subscription Fee")
        qty = item.get("quantity", 1)
        unit_cents = item.get("unit_amount_cents", 0)
        total_cents = unit_cents * qty
        rows_html += f"""
        <tr>
          <td class="desc">{desc}</td>
          <td class="qty">{qty}</td>
          <td class="price">{_format_currency(unit_cents)}</td>
          <td class="total">{_format_currency(total_cents)}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Receipt - {invoice.invoice_number}</title>
  <style>
    :root {{
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --border: #334155;
      --primary: #3b82f6;
      --success: #10b981;
      --warning: #f59e0b;
    }}
    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #f8fafc;
        --card-bg: #ffffff;
        --text: #0f172a;
        --text-muted: #64748b;
        --border: #e2e8f0;
        --primary: #2563eb;
      }}
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: var(--font-family);
      background-color: var(--bg);
      color: var(--text);
      padding: 32px 16px;
      line-height: 1.5;
    }}
    .receipt-container {{
      max-width: 680px;
      margin: 0 auto;
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 36px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 28px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 24px;
    }}
    .brand h1 {{
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }}
    .brand p {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
    }}
    .status-badge {{
      display: inline-block;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
    .status-paid {{
      background-color: rgba(16, 185, 129, 0.15);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}
    .status-open {{
      background-color: rgba(245, 158, 11, 0.15);
      color: var(--warning);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}
    .details-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 32px;
      font-size: 14px;
    }}
    .details-block h3 {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 6px;
    }}
    .details-block p {{
      font-weight: 500;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 32px;
    }}
    th {{
      text-align: left;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      padding: 10px 8px;
    }}
    td {{
      padding: 12px 8px;
      font-size: 14px;
      border-bottom: 1px solid var(--border);
    }}
    .qty, .price, .total {{
      text-align: right;
    }}
    .summary {{
      margin-left: auto;
      max-width: 280px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 14px;
    }}
    .summary-row {{
      display: flex;
      justify-content: space-between;
    }}
    .summary-row.final {{
      border-top: 2px solid var(--border);
      padding-top: 10px;
      font-size: 16px;
      font-weight: 700;
    }}
    .actions {{
      margin-top: 36px;
      display: flex;
      justify-content: flex-end;
      gap: 12px;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      padding: 8px 18px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      border: 1px solid var(--border);
      background-color: var(--card-bg);
      color: var(--text);
    }}
    .btn-primary {{
      background-color: var(--primary);
      color: #ffffff;
      border-color: var(--primary);
    }}
    @media print {{
      body {{
        background-color: #ffffff !important;
        color: #000000 !important;
        padding: 0;
      }}
      .receipt-container {{
        box-shadow: none !important;
        border: none !important;
        max-width: 100% !important;
        padding: 0;
      }}
      .no-print {{
        display: none !important;
      }}
    }}
  </style>
</head>
<body>
  <div class="receipt-container">
    <div class="header">
      <div class="brand">
        <h1>PulseSub</h1>
        <p>Subscription & Entitlements Platform</p>
      </div>
      <div>
        <span class="status-badge {status_class}">{status_label}</span>
      </div>
    </div>

    <div class="details-grid">
      <div class="details-block">
        <h3>Billed To</h3>
        <p>{user_name}</p>
        <p style="color: var(--text-muted); font-size: 13px;">{user_email}</p>
      </div>
      <div class="details-block" style="text-align: right;">
        <h3>Invoice Number</h3>
        <p>{invoice.invoice_number}</p>
        <p style="color: var(--text-muted); font-size: 13px;">Date: {date_str}</p>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Description</th>
          <th class="qty">Qty</th>
          <th class="price">Unit Price</th>
          <th class="total">Amount</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>

    <div class="summary">
      <div class="summary-row">
        <span>Amount Due:</span>
        <span>{_format_currency(invoice.amount_due_cents)}</span>
      </div>
      <div class="summary-row">
        <span>Amount Paid:</span>
        <span>{_format_currency(invoice.amount_paid_cents)}</span>
      </div>
      <div class="summary-row final">
        <span>Balance Due:</span>
        <span>{_format_currency(balance_due)}</span>
      </div>
    </div>

    <div class="actions no-print">
      <button class="btn btn-primary" onclick="window.print()">Print Receipt</button>
    </div>
  </div>
</body>
</html>
"""


@billing_bp.route("/invoices", methods=["GET"])
def list_invoices():
    """Retrieve billing history and past invoice statements for authenticated user."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        invoice_service = InvoiceService(conn)
        invoices = invoice_service.get_invoices_by_user(user_id)
        return (
            jsonify(
                {
                    "user_id": user_id,
                    "invoices": [inv.to_dict() for inv in invoices],
                    "total": len(invoices),
                }
            ),
            200,
        )
    finally:
        conn.close()


@billing_bp.route("/invoices/<invoice_id>", methods=["GET"])
def get_invoice(invoice_id: str):
    """Retrieve line item details and settlement status for an individual invoice."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        invoice_service = InvoiceService(conn)
        invoice = invoice_service.get_invoice_by_id(invoice_id)
        if not invoice or invoice.user_id != user_id:
            return (
                jsonify(
                    {
                        "error": "invoice_not_found",
                        "message": f"Invoice '{invoice_id}' not found.",
                    }
                ),
                404,
            )

        return jsonify({"invoice": invoice.to_dict()}), 200
    finally:
        conn.close()


@billing_bp.route("/invoices/<invoice_id>/receipt", methods=["GET"])
def get_invoice_receipt(invoice_id: str):
    """Retrieve structured receipt metadata suitable for frontend display."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        invoice_service = InvoiceService(conn)
        invoice = invoice_service.get_invoice_by_id(invoice_id)
        if not invoice or invoice.user_id != user_id:
            return (
                jsonify(
                    {
                        "error": "invoice_not_found",
                        "message": f"Invoice '{invoice_id}' not found.",
                    }
                ),
                404,
            )

        auth_service = AuthService(conn)
        user = auth_service.get_user_by_id(user_id) or {
            "full_name": "Valued Customer",
            "email": "",
        }

        return (
            jsonify(
                {
                    "invoice_number": invoice.invoice_number,
                    "customer_name": user.get("full_name"),
                    "customer_email": user.get("email"),
                    "amount_due_formatted": _format_currency(invoice.amount_due_cents),
                    "amount_paid_formatted": _format_currency(
                        invoice.amount_paid_cents
                    ),
                    "status": invoice.status,
                    "created_at": invoice.created_at,
                    "paid_at": invoice.paid_at,
                    "line_items": invoice.line_items,
                }
            ),
            200,
        )
    finally:
        conn.close()


@billing_bp.route("/invoices/<invoice_id>/html", methods=["GET"])
def get_invoice_html(invoice_id: str):
    """Render a standalone, responsive, print-ready HTML invoice receipt."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        invoice_service = InvoiceService(conn)
        invoice = invoice_service.get_invoice_by_id(invoice_id)
        if not invoice or invoice.user_id != user_id:
            return Response("<h1>404 Not Found</h1>", status=404, mimetype="text/html")

        auth_service = AuthService(conn)
        user = auth_service.get_user_by_id(user_id) or {
            "full_name": "Customer",
            "email": "customer@pulsesub.io",
        }

        html = _render_receipt_html(
            invoice=invoice,
            user_name=user.get("full_name", "Customer"),
            user_email=user.get("email", ""),
        )
        return Response(html, mimetype="text/html")
    finally:
        conn.close()


@billing_bp.route("/invoices/<invoice_id>/pay", methods=["POST"])
def pay_invoice(invoice_id: str):
    """Simulate settlement of open invoice and reactivate past due subscription."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        invoice_service = InvoiceService(conn)
        invoice = invoice_service.get_invoice_by_id(invoice_id)
        if not invoice or invoice.user_id != user_id:
            return (
                jsonify(
                    {
                        "error": "invoice_not_found",
                        "message": f"Invoice '{invoice_id}' not found.",
                    }
                ),
                404,
            )

        updated_invoice = invoice_service.mark_as_paid(invoice_id)

        # If linked to a past-due subscription, activate it
        sub_updated = None
        if updated_invoice.subscription_id:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM subscriptions WHERE id = ?;",
                (updated_invoice.subscription_id,),
            )
            sub_row = cursor.fetchone()
            cursor.close()
            if sub_row:
                sub = Subscription.from_row(sub_row)
                if sub.status == SubscriptionStatus.PAST_DUE.value:
                    fsm = SubscriptionFSM(sub, conn)
                    sub_updated = fsm.activate()

        return (
            jsonify(
                {
                    "invoice": updated_invoice.to_dict(),
                    "subscription_reactivated": sub_updated is not None,
                    "message": "Invoice settled successfully.",
                }
            ),
            200,
        )
    finally:
        conn.close()
