"""Idempotent webhook event dispatcher and subscription event handlers."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from app.billing.invoice_service import InvoiceService
from app.billing.subscription_fsm import SubscriptionFSM
from app.models.schemas import BillingInterval, Subscription, SubscriptionStatus


class WebhookDispatcher:
    """Dispatches Stripe-compatible webhook events with idempotent deduplication."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.invoice_service = InvoiceService(conn)

    def dispatch(
        self,
        event_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Dispatch inbound webhook payload with idempotency defense."""
        now = datetime.now(timezone.utc)
        iso_now = now.strftime("%Y-%m-%d %H:%M:%S")

        cursor = self.conn.cursor()

        # 1. Idempotency check: verify if event was previously processed
        cursor.execute(
            "SELECT status FROM webhook_events WHERE event_id = ?;",
            (event_id,),
        )
        row = cursor.fetchone()
        if row and row["status"] == "processed":
            cursor.close()
            return {
                "status": "already_processed",
                "event_id": event_id,
                "event_type": event_type,
            }

        # 2. Register event record as pending if not already present
        if not row:
            record_id = f"wh_{uuid.uuid4().hex[:12]}"
            cursor.execute(
                """
                INSERT INTO webhook_events (
                    id, event_id, event_type, payload_json, status, received_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    record_id,
                    event_id,
                    event_type,
                    json.dumps(payload),
                    "pending",
                    iso_now,
                ),
            )
            self.conn.commit()

        cursor.close()

        # 3. Route to dedicated event handlers
        try:
            handler_result = self._route_event(event_type, payload)

            # 4. Mark event as successfully processed
            update_cursor = self.conn.cursor()
            update_cursor.execute(
                """
                UPDATE webhook_events
                SET status = 'processed',
                    processed_at = ?
                WHERE event_id = ?;
                """,
                (iso_now, event_id),
            )
            self.conn.commit()
            update_cursor.close()

            return {
                "status": "processed",
                "event_id": event_id,
                "event_type": event_type,
                "result": handler_result,
            }

        except Exception as exc:
            # 5. Mark event as failed and record error message
            fail_cursor = self.conn.cursor()
            fail_cursor.execute(
                """
                UPDATE webhook_events
                SET status = 'failed',
                    error_message = ?
                WHERE event_id = ?;
                """,
                (str(exc), event_id),
            )
            self.conn.commit()
            fail_cursor.close()
            raise

    def _route_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Internal router mapping event types to specific domain mutations."""
        data_object = payload.get("data", {}).get("object", {})

        if event_type == "customer.subscription.created":
            return self._handle_subscription_created(data_object)
        elif event_type == "customer.subscription.updated":
            return self._handle_subscription_updated(data_object)
        elif event_type == "customer.subscription.deleted":
            return self._handle_subscription_deleted(data_object)
        elif event_type == "invoice.paid":
            return self._handle_invoice_paid(data_object)
        elif event_type == "invoice.payment_failed":
            return self._handle_invoice_payment_failed(data_object)
        else:
            return {"action": "unhandled_event", "type": event_type}

    def _handle_subscription_created(self, data: Dict[str, Any]) -> Dict[str, Any]:
        user_id = data.get("customer") or data.get("user_id", "usr_demo_alice")
        plan_id = data.get("plan", {}).get("id") or data.get("plan_id", "plan_pro")
        interval = data.get("interval", "monthly")
        sub_id = data.get("id") or f"sub_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        fmt = "%Y-%m-%d %H:%M:%S"

        start_str = data.get("current_period_start") or now.strftime(fmt)
        end_str = data.get("current_period_end") or now.strftime(fmt)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO subscriptions (
                id, user_id, plan_id, billing_interval, status,
                current_period_start, current_period_end, cancel_at_period_end,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                sub_id,
                user_id,
                plan_id,
                interval,
                SubscriptionStatus.ACTIVE.value,
                start_str,
                end_str,
                0,
                now.strftime(fmt),
                now.strftime(fmt),
            ),
        )
        self.conn.commit()
        cursor.close()
        return {"action": "subscription_created", "subscription_id": sub_id}

    def _handle_subscription_updated(self, data: Dict[str, Any]) -> Dict[str, Any]:
        sub_id = data.get("id")
        cursor = self.conn.cursor()

        if sub_id:
            cursor.execute("SELECT * FROM subscriptions WHERE id = ?;", (sub_id,))
        else:
            user_id = data.get("customer") or data.get("user_id")
            cursor.execute(
                """
                SELECT * FROM subscriptions
                WHERE user_id = ?
                ORDER BY current_period_end DESC
                LIMIT 1;
                """,
                (user_id,),
            )

        row = cursor.fetchone()
        cursor.close()

        if not row:
            return {"action": "subscription_not_found"}

        sub = Subscription.from_row(row)
        fsm = SubscriptionFSM(sub, conn=self.conn)

        # Update plan if present
        new_plan = data.get("plan", {}).get("id") or data.get("plan_id")
        new_interval_str = data.get("interval")
        new_interval = BillingInterval(new_interval_str) if new_interval_str else None
        if new_plan:
            fsm.change_tier(new_plan, new_interval)

        # Update status if present
        target_status = data.get("status")
        if target_status == "past_due":
            fsm.mark_past_due()
        elif target_status == "active" and sub.status != "active":
            fsm.activate()
        elif target_status == "canceled":
            fsm.cancel(immediate=True)

        cancel_at_end = data.get("cancel_at_period_end")
        if cancel_at_end is True:
            fsm.cancel(immediate=False)
        elif cancel_at_end is False and sub.cancel_at_period_end:
            fsm.resume()

        return {"action": "subscription_updated", "subscription_id": sub.id}

    def _handle_subscription_deleted(self, data: Dict[str, Any]) -> Dict[str, Any]:
        sub_id = data.get("id")
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM subscriptions WHERE id = ?;", (sub_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return {"action": "subscription_not_found"}

        sub = Subscription.from_row(row)
        fsm = SubscriptionFSM(sub, conn=self.conn)
        fsm.cancel(immediate=True)
        return {"action": "subscription_canceled", "subscription_id": sub.id}

    def _handle_invoice_paid(self, data: Dict[str, Any]) -> Dict[str, Any]:
        inv_id = data.get("id")
        sub_id = data.get("subscription") or data.get("subscription_id")

        # Mark invoice as paid if found in database
        if inv_id:
            inv = self.invoice_service.get_invoice_by_id(inv_id)
            if inv and inv.status != "paid":
                self.invoice_service.mark_as_paid(inv_id)

        # Reactivate or verify subscription status
        if sub_id:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM subscriptions WHERE id = ?;", (sub_id,))
            row = cursor.fetchone()
            cursor.close()
            if row:
                sub = Subscription.from_row(row)
                if sub.status == SubscriptionStatus.PAST_DUE.value:
                    fsm = SubscriptionFSM(sub, conn=self.conn)
                    fsm.activate()

        return {"action": "invoice_paid_processed", "invoice_id": inv_id}

    def _handle_invoice_payment_failed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        inv_id = data.get("id")
        sub_id = data.get("subscription") or data.get("subscription_id")

        if inv_id:
            inv = self.invoice_service.get_invoice_by_id(inv_id)
            if inv:
                self.invoice_service.mark_as_failed(inv_id)

        if sub_id:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM subscriptions WHERE id = ?;", (sub_id,))
            row = cursor.fetchone()
            cursor.close()
            if row:
                sub = Subscription.from_row(row)
                if sub.status == SubscriptionStatus.ACTIVE.value:
                    fsm = SubscriptionFSM(sub, conn=self.conn)
                    fsm.mark_past_due()

        return {
            "action": "invoice_payment_failed_processed",
            "invoice_id": inv_id,
        }
