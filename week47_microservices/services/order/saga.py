"""Distributed Saga Coordinator for order lifecycle with compensating rollback."""

import logging
import secrets
import sqlite3
from typing import Any, Callable, Optional

from services.order.models import OrderModel
from shared.client import PulseClient
from shared.logging import setup_mesh_logger
from shared.message_broker import MessageBroker, get_message_broker
from shared.models import CloudEvent, CorrelationContext


class OrderSagaCoordinator:
    """Orchestrates multi-service checkout workflows and automated rollbacks."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        pulse_client: Optional[PulseClient] = None,
        broker: Optional[MessageBroker] = None,
        logger: Optional[logging.Logger] = None,
        user_verifier: Optional[Callable[[str, str], tuple[bool, str]]] = None,
        stock_reserver: Optional[
            Callable[[str, list[dict[str, Any]], str], tuple[bool, str]]
        ] = None,
        stock_releaser: Optional[Callable[[str, str], tuple[bool, str]]] = None,
        stock_committer: Optional[Callable[[str, str], tuple[bool, str]]] = None,
        payment_processor: Optional[Callable[[str, int, str], tuple[bool, str]]] = None,
    ):
        self.conn = conn
        self.pulse_client = pulse_client
        self.broker = broker or get_message_broker()
        self.logger = logger or setup_mesh_logger("order-saga-coordinator")
        self.user_verifier = user_verifier
        self.stock_reserver = stock_reserver
        self.stock_releaser = stock_releaser
        self.stock_committer = stock_committer
        self.payment_processor = payment_processor

    def _verify_user(self, user_id: str, corr_id: str) -> tuple[bool, str]:
        """Verify user existence and active status."""
        if self.user_verifier:
            return self.user_verifier(user_id, corr_id)

        if self.pulse_client:
            try:
                resp = self.pulse_client.get(
                    "user-service",
                    f"/api/v1/users/{user_id}",
                    correlation_id=corr_id,
                )
                if not resp.is_success:
                    return False, f"User service rejected: {resp.status_code}"
                user_data = resp.json().get("user", resp.json())
                if not user_data.get("is_active", True):
                    return False, "User account is suspended"
                return True, ""
            except Exception as exc:
                return False, f"User service connection error: {exc}"

        # Fallback check
        if user_id.strip():
            return True, ""
        return False, "Invalid user identifier"

    def _reserve_stock(
        self, order_id: str, items: list[dict[str, Any]], corr_id: str
    ) -> tuple[bool, str]:
        """Reserve stock units across all ordered line items."""
        if self.stock_reserver:
            return self.stock_reserver(order_id, items, corr_id)

        if self.pulse_client:
            try:
                clean_items = []
                for it in items:
                    prod_id = it.get("product_id") or it.get("sku") or ""
                    clean_items.append(
                        {"product_id": prod_id, "quantity": it["quantity"]}
                    )

                payload = {"order_id": order_id, "items": clean_items}
                resp = self.pulse_client.post(
                    "catalog-service",
                    "/api/v1/inventory/reserve",
                    json=payload,
                    correlation_id=corr_id,
                )
                if resp.is_success:
                    return True, ""
                err_msg = (
                    resp.json().get("error", "Stock reservation failed")
                    if isinstance(resp.data, dict)
                    else resp.raw_text
                )
                return False, err_msg
            except Exception as exc:
                return False, f"Catalog service connection error: {exc}"

        return True, ""

    def _process_payment(
        self,
        order_id: str,
        total_cents: int,
        corr_id: str,
        simulate_failure: bool = False,
    ) -> tuple[bool, str]:
        """Simulate or execute payment gateway transaction."""
        if simulate_failure:
            return False, "Payment gateway rejected: insufficient funds"

        if self.payment_processor:
            return self.payment_processor(order_id, total_cents, corr_id)

        # Standard simulated payment
        return True, ""

    def _compensate_stock(self, order_id: str, corr_id: str) -> tuple[bool, str]:
        """Execute compensating transaction: release reserved inventory."""
        if self.stock_releaser:
            return self.stock_releaser(order_id, corr_id)

        if self.pulse_client:
            try:
                resp = self.pulse_client.post(
                    "catalog-service",
                    "/api/v1/inventory/release",
                    json={"order_id": order_id},
                    correlation_id=corr_id,
                )
                if resp.is_success:
                    return True, ""
                return False, f"Release failed: {resp.raw_text}"
            except Exception as exc:
                return False, f"Catalog release error: {exc}"

        return True, ""

    def _commit_stock(self, order_id: str, corr_id: str) -> tuple[bool, str]:
        """Commit reserved inventory to permanently deducted state."""
        if self.stock_committer:
            return self.stock_committer(order_id, corr_id)

        if self.pulse_client:
            try:
                resp = self.pulse_client.post(
                    "catalog-service",
                    "/api/v1/inventory/commit",
                    json={"order_id": order_id},
                    correlation_id=corr_id,
                )
                if resp.is_success:
                    return True, ""
                return False, f"Stock commit failed: {resp.raw_text}"
            except Exception as exc:
                return False, f"Catalog commit error: {exc}"

        return True, ""

    def execute_saga(
        self,
        user_id: str,
        total_cents: int,
        items: list[dict[str, Any]],
        correlation_id: Optional[str] = None,
        simulate_payment_failure: bool = False,
        order_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run full distributed saga workflow with compensation on failure."""
        corr_id = correlation_id or CorrelationContext.get_correlation_id()
        oid = order_id or f"ord_{secrets.token_hex(8)}"

        self.logger.info(f"Starting Order Saga for order '{oid}' [corr: {corr_id}]")

        # 0. Create initial PENDING order
        OrderModel.create_order(
            conn=self.conn,
            order_id=oid,
            user_id=user_id,
            total_cents=total_cents,
            items=items,
            correlation_id=corr_id,
            status="PENDING",
        )

        # Step 1: VERIFY_USER
        OrderModel.record_saga_step(
            self.conn, oid, "VERIFY_USER", "STARTED", {"user_id": user_id}
        )
        user_ok, user_err = self._verify_user(user_id, corr_id)
        if not user_ok:
            OrderModel.record_saga_step(
                self.conn, oid, "VERIFY_USER", "FAILED", {"error": user_err}
            )
            OrderModel.update_order_status(self.conn, oid, "FAILED")
            return {
                "success": False,
                "order_id": oid,
                "status": "FAILED",
                "failed_step": "VERIFY_USER",
                "error": user_err,
                "trace": OrderModel.get_saga_trace(self.conn, oid),
            }
        OrderModel.record_saga_step(
            self.conn, oid, "VERIFY_USER", "COMPLETED", {"user_id": user_id}
        )

        # Step 2: RESERVE_STOCK
        OrderModel.record_saga_step(
            self.conn, oid, "RESERVE_STOCK", "STARTED", {"items": items}
        )
        stock_ok, stock_err = self._reserve_stock(oid, items, corr_id)
        if not stock_ok:
            OrderModel.record_saga_step(
                self.conn, oid, "RESERVE_STOCK", "FAILED", {"error": stock_err}
            )
            OrderModel.update_order_status(self.conn, oid, "FAILED")
            return {
                "success": False,
                "order_id": oid,
                "status": "FAILED",
                "failed_step": "RESERVE_STOCK",
                "error": stock_err,
                "trace": OrderModel.get_saga_trace(self.conn, oid),
            }
        OrderModel.record_saga_step(
            self.conn, oid, "RESERVE_STOCK", "COMPLETED", {"items": items}
        )

        # Step 3: PROCESS_PAYMENT
        OrderModel.record_saga_step(
            self.conn,
            oid,
            "PROCESS_PAYMENT",
            "STARTED",
            {"amount_cents": total_cents},
        )
        pay_ok, pay_err = self._process_payment(
            oid, total_cents, corr_id, simulate_failure=simulate_payment_failure
        )
        if not pay_ok:
            OrderModel.record_saga_step(
                self.conn, oid, "PROCESS_PAYMENT", "FAILED", {"error": pay_err}
            )

            # Trigger Compensating Action: COMPENSATE_STOCK_RELEASE
            OrderModel.record_saga_step(
                self.conn,
                oid,
                "COMPENSATE_STOCK_RELEASE",
                "STARTED",
                {"reason": pay_err},
            )
            comp_ok, comp_err = self._compensate_stock(oid, corr_id)
            comp_status = "COMPENSATED" if comp_ok else "COMPENSATION_FAILED"
            OrderModel.record_saga_step(
                self.conn,
                oid,
                "COMPENSATE_STOCK_RELEASE",
                comp_status,
                {"error": comp_err} if not comp_ok else {"released": True},
            )

            OrderModel.update_order_status(self.conn, oid, "CANCELLED")

            # Publish order.cancelled CloudEvent
            cancel_event = CloudEvent.create(
                source="order-service",
                event_type="order.cancelled",
                data={
                    "order_id": oid,
                    "user_id": user_id,
                    "total_cents": total_cents,
                    "reason": pay_err,
                },
                correlation_id=corr_id,
            )
            self.broker.publish("orders.events", cancel_event)
            OrderModel.record_saga_step(
                self.conn,
                oid,
                "PUBLISH_EVENT",
                "COMPLETED",
                {"event_type": "order.cancelled", "event_id": cancel_event.id},
            )

            return {
                "success": False,
                "order_id": oid,
                "status": "CANCELLED",
                "failed_step": "PROCESS_PAYMENT",
                "error": pay_err,
                "compensated": comp_ok,
                "trace": OrderModel.get_saga_trace(self.conn, oid),
            }

        OrderModel.record_saga_step(
            self.conn,
            oid,
            "PROCESS_PAYMENT",
            "COMPLETED",
            {"amount_cents": total_cents},
        )

        # Step 4: COMMIT_STOCK
        OrderModel.record_saga_step(self.conn, oid, "COMMIT_STOCK", "STARTED")
        commit_ok, commit_err = self._commit_stock(oid, corr_id)
        if not commit_ok:
            OrderModel.record_saga_step(
                self.conn, oid, "COMMIT_STOCK", "FAILED", {"error": commit_err}
            )
            OrderModel.update_order_status(self.conn, oid, "FAILED")
            return {
                "success": False,
                "order_id": oid,
                "status": "FAILED",
                "failed_step": "COMMIT_STOCK",
                "error": commit_err,
                "trace": OrderModel.get_saga_trace(self.conn, oid),
            }
        OrderModel.record_saga_step(self.conn, oid, "COMMIT_STOCK", "COMPLETED")

        # Step 5: FINALIZE_ORDER
        OrderModel.update_order_status(self.conn, oid, "COMPLETED")
        OrderModel.record_saga_step(self.conn, oid, "FINALIZE_ORDER", "COMPLETED")

        # Step 6: PUBLISH_EVENT
        completed_event = CloudEvent.create(
            source="order-service",
            event_type="order.completed",
            data={
                "order_id": oid,
                "user_id": user_id,
                "total_cents": total_cents,
                "items": items,
            },
            correlation_id=corr_id,
        )
        self.broker.publish("orders.events", completed_event)
        OrderModel.record_saga_step(
            self.conn,
            oid,
            "PUBLISH_EVENT",
            "COMPLETED",
            {"event_type": "order.completed", "event_id": completed_event.id},
        )

        updated_order = OrderModel.get_order(self.conn, oid)
        trace = OrderModel.get_saga_trace(self.conn, oid)

        return {
            "success": True,
            "order": updated_order,
            "trace": trace,
        }
