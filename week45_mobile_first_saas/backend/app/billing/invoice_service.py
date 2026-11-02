"""Invoice generation, settlement, and lifecycle service for PulseSub."""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.billing.proration import ProrationResult
from app.models.schemas import Invoice, InvoiceStatus


class InvoiceService:
    """Service managing invoice issuance, numbering, and settlement."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _generate_invoice_number(self, now: datetime) -> str:
        """Generate collision-free sequential invoice number (INV-YYYY-XXXX)."""
        year = now.strftime("%Y")
        prefix = f"INV-{year}-"

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT invoice_number FROM invoices
            WHERE invoice_number LIKE ?
            ORDER BY invoice_number DESC
            LIMIT 1;
            """,
            (f"{prefix}%",),
        )
        row = cursor.fetchone()
        cursor.close()

        if row and row["invoice_number"]:
            try:
                last_seq = int(row["invoice_number"].replace(prefix, ""))
                next_seq = last_seq + 1
            except ValueError:
                next_seq = 1
        else:
            next_seq = 1

        return f"{prefix}{next_seq:04d}"

    def create_invoice(
        self,
        user_id: str,
        subscription_id: Optional[str],
        line_items: List[Dict[str, Any]],
        currency: str = "usd",
        due_days: int = 0,
        auto_pay: bool = False,
    ) -> Invoice:
        """Create and persist a new customer invoice statement."""
        now = datetime.now(timezone.utc)
        fmt = "%Y-%m-%d %H:%M:%S"
        iso_now = now.strftime(fmt)
        due_date = (now + timedelta(days=due_days)).strftime(fmt)

        total_due = sum(
            int(item.get("unit_amount_cents", 0)) * int(item.get("quantity", 1))
            for item in line_items
        )
        amount_due = max(0, total_due)

        invoice_id = f"inv_{uuid.uuid4().hex[:12]}"
        invoice_number = self._generate_invoice_number(now)

        if auto_pay or amount_due == 0:
            status = InvoiceStatus.PAID.value
            amount_paid = amount_due
            paid_at = iso_now
        else:
            status = InvoiceStatus.OPEN.value
            amount_paid = 0
            paid_at = None

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (
                id, user_id, subscription_id, invoice_number,
                amount_due_cents, amount_paid_cents, currency,
                status, line_items_json, payment_attempt_count,
                due_date, paid_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                invoice_id,
                user_id,
                subscription_id,
                invoice_number,
                amount_due,
                amount_paid,
                currency,
                status,
                json.dumps(line_items),
                1 if auto_pay else 0,
                due_date,
                paid_at,
                iso_now,
            ),
        )
        self.conn.commit()
        cursor.close()

        return Invoice(
            id=invoice_id,
            user_id=user_id,
            subscription_id=subscription_id,
            invoice_number=invoice_number,
            amount_due_cents=amount_due,
            amount_paid_cents=amount_paid,
            currency=currency,
            status=status,
            line_items=line_items,
            payment_attempt_count=1 if auto_pay else 0,
            due_date=due_date,
            paid_at=paid_at,
            created_at=iso_now,
        )

    def create_proration_invoice(
        self,
        user_id: str,
        subscription_id: str,
        proration_result: ProrationResult,
        auto_pay: bool = True,
    ) -> Invoice:
        """Generate and record a prorated invoice for tier changes."""
        line_items = proration_result.to_line_items()
        return self.create_invoice(
            user_id=user_id,
            subscription_id=subscription_id,
            line_items=line_items,
            due_days=0,
            auto_pay=auto_pay,
        )

    def mark_as_paid(
        self,
        invoice_id: str,
        paid_at: Optional[datetime] = None,
    ) -> Invoice:
        """Mark an open invoice as successfully settled."""
        now = paid_at or datetime.now(timezone.utc)
        iso_paid = now.strftime("%Y-%m-%d %H:%M:%S")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE invoices
            SET status = ?,
                amount_paid_cents = amount_due_cents,
                paid_at = ?,
                payment_attempt_count = payment_attempt_count + 1
            WHERE id = ?;
            """,
            (InvoiceStatus.PAID.value, iso_paid, invoice_id),
        )
        self.conn.commit()
        cursor.close()

        invoice = self.get_invoice_by_id(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice with ID '{invoice_id}' not found.")
        return invoice

    def mark_as_failed(self, invoice_id: str) -> Invoice:
        """Record a failed payment attempt on an invoice."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE invoices
            SET payment_attempt_count = payment_attempt_count + 1,
                status = CASE
                    WHEN (payment_attempt_count + 1) >= 2 THEN ?
                    ELSE status
                END
            WHERE id = ?;
            """,
            (InvoiceStatus.UNCOLLECTIBLE.value, invoice_id),
        )
        self.conn.commit()
        cursor.close()

        invoice = self.get_invoice_by_id(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice with ID '{invoice_id}' not found.")
        return invoice

    def void_invoice(self, invoice_id: str) -> Invoice:
        """Void an existing invoice."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE invoices
            SET status = ?
            WHERE id = ?;
            """,
            (InvoiceStatus.VOID.value, invoice_id),
        )
        self.conn.commit()
        cursor.close()

        invoice = self.get_invoice_by_id(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice with ID '{invoice_id}' not found.")
        return invoice

    def get_invoice_by_id(self, invoice_id: str) -> Optional[Invoice]:
        """Fetch an invoice by its unique identifier."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE id = ?;", (invoice_id,))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return None
        return Invoice.from_row(row)

    def get_invoices_by_user(self, user_id: str) -> List[Invoice]:
        """Fetch all historical invoices for a specific user."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM invoices
            WHERE user_id = ?
            ORDER BY created_at DESC;
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [Invoice.from_row(row) for row in rows]
