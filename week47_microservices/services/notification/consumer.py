"""Event consumer processing order lifecycle events into customer notifications."""

import logging
import sqlite3
import threading
from typing import Optional

from services.notification.models import NotificationModel
from shared.logging import setup_mesh_logger
from shared.message_broker import MessageBroker, get_message_broker
from shared.models import CloudEvent


class NotificationConsumer:
    """Consumes CloudEvents from MessageBroker with idempotent deduplication."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        broker: Optional[MessageBroker] = None,
        topic: str = "orders.events",
        consumer_id: str = "notification-service-worker",
        logger: Optional[logging.Logger] = None,
    ):
        self.conn = conn
        self.broker = broker or get_message_broker()
        self.topic = topic
        self.consumer_id = consumer_id
        self.logger = logger or setup_mesh_logger("notification-consumer")
        self._lock = threading.RLock()
        self.subscription_id: Optional[str] = None

    def start(self) -> str:
        """Subscribe this consumer to the target event topic."""
        with self._lock:
            if not self.subscription_id:
                self.subscription_id = self.broker.subscribe(
                    topic=self.topic,
                    consumer_id=self.consumer_id,
                    callback=self.handle_event,
                )
                self.logger.info(
                    f"NotificationConsumer subscribed to '{self.topic}' "
                    f"as '{self.consumer_id}' (sub: {self.subscription_id})"
                )
            return self.subscription_id

    def stop(self) -> bool:
        """Unsubscribe this consumer from the target event topic."""
        with self._lock:
            if self.subscription_id:
                removed = self.broker.unsubscribe(self.topic, self.consumer_id)
                self.subscription_id = None
                return removed
            return False

    def handle_event(self, event: CloudEvent) -> None:
        """Handle incoming CloudEvent, enforcing idempotent exactly-once processing."""
        with self._lock:
            # 1. Idempotency check: has this event already been processed?
            if NotificationModel.is_event_processed(self.conn, event.id):
                self.logger.warning(
                    f"Duplicate event ignored [id: {event.id}, type: {event.type}]"
                )
                return

            corr_id = event.correlation_id or ""
            data = event.data or {}

            if event.type == "order.completed":
                order_id = data.get("order_id", "UNKNOWN")
                user_id = data.get("user_id", "UNKNOWN")
                total_cents = data.get("total_cents", 0)
                dollars = total_cents / 100.0

                subject = f"Order {order_id} Confirmed"
                body = (
                    f"Your order '{order_id}' was completed successfully. "
                    f"Total billed: ${dollars:.2f}."
                )

                NotificationModel.create_notification(
                    conn=self.conn,
                    user_id=user_id,
                    channel="EMAIL",
                    event_type=event.type,
                    subject=subject,
                    body=body,
                    correlation_id=corr_id,
                    status="SENT",
                )
                NotificationModel.mark_event_processed(self.conn, event.id, event.type)
                self.logger.info(
                    f"Dispatched confirmation notification for order '{order_id}'"
                )

            elif event.type == "order.cancelled":
                order_id = data.get("order_id", "UNKNOWN")
                user_id = data.get("user_id", "UNKNOWN")
                reason = data.get("reason", "Checkout processing failure")

                subject = f"Order {order_id} Cancelled"
                body = (
                    f"Your order '{order_id}' has been cancelled. "
                    f"Reason: {reason}. Any held reservations were released."
                )

                NotificationModel.create_notification(
                    conn=self.conn,
                    user_id=user_id,
                    channel="EMAIL",
                    event_type=event.type,
                    subject=subject,
                    body=body,
                    correlation_id=corr_id,
                    status="SENT",
                )
                NotificationModel.mark_event_processed(self.conn, event.id, event.type)
                self.logger.info(
                    f"Dispatched cancellation notification for order '{order_id}'"
                )

            else:
                # Other generic event types
                NotificationModel.mark_event_processed(self.conn, event.id, event.type)
                self.logger.info(
                    f"Recorded unhandled event type '{event.type}' [id: {event.id}]"
                )
