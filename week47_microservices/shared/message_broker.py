"""Asynchronous CloudEvents pub/sub message broker with Dead-Letter Queue."""

import logging
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from shared.logging import setup_mesh_logger
from shared.models import CloudEvent, utc_now_iso


@dataclass
class DeadLetterMessage:
    """Represents a poisoned message quarantined in the Dead-Letter Queue."""

    id: str
    topic: str
    consumer_id: str
    event: CloudEvent
    error_reason: str
    retry_count: int
    failed_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """Serialize DLQ message to JSON-compatible dictionary."""
        return {
            "id": self.id,
            "topic": self.topic,
            "consumer_id": self.consumer_id,
            "event": self.event.to_dict(),
            "error_reason": self.error_reason,
            "retry_count": self.retry_count,
            "failed_at": self.failed_at,
        }


@dataclass
class Subscription:
    """Subscription handle linking a topic to a consumer callback."""

    id: str
    topic: str
    consumer_id: str
    callback: Callable[[CloudEvent], None]
    max_retries: int = 3


class MessageBroker:
    """Thread-safe in-memory pub/sub event bus with Dead-Letter Queue."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self._lock = threading.RLock()
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._history: dict[str, list[CloudEvent]] = {}
        self._dlq: dict[str, DeadLetterMessage] = {}
        self.logger = logger or setup_mesh_logger("message-broker")

    def subscribe(
        self,
        topic: str,
        consumer_id: str,
        callback: Callable[[CloudEvent], None],
        max_retries: int = 3,
    ) -> str:
        """Register a subscriber callback for an event topic."""
        clean_topic = topic.strip().lower()
        sub_id = f"sub_{secrets.token_hex(6)}"
        sub = Subscription(
            id=sub_id,
            topic=clean_topic,
            consumer_id=consumer_id.strip(),
            callback=callback,
            max_retries=max(1, max_retries),
        )

        with self._lock:
            subs = self._subscriptions.setdefault(clean_topic, [])
            subs.append(sub)
            self.logger.info(
                f"Consumer '{consumer_id}' subscribed to topic '{clean_topic}'"
            )
            return sub_id

    def unsubscribe(self, topic: str, consumer_id: str) -> bool:
        """Remove all subscriptions for a consumer on a topic."""
        clean_topic = topic.strip().lower()
        with self._lock:
            if clean_topic not in self._subscriptions:
                return False
            initial_count = len(self._subscriptions[clean_topic])
            self._subscriptions[clean_topic] = [
                s
                for s in self._subscriptions[clean_topic]
                if s.consumer_id != consumer_id
            ]
            removed = len(self._subscriptions[clean_topic]) < initial_count
            return removed

    def publish(self, topic: str, event: CloudEvent) -> int:
        """Publish a CloudEvent to a topic and dispatch to all active subscribers."""
        clean_topic = topic.strip().lower()

        with self._lock:
            history = self._history.setdefault(clean_topic, [])
            history.append(event)
            if len(history) > 500:
                history.pop(0)

            subscribers = list(self._subscriptions.get(clean_topic, []))

        delivery_count = 0
        for sub in subscribers:
            success = False
            last_err = ""

            for attempt in range(sub.max_retries):
                try:
                    sub.callback(event)
                    success = True
                    delivery_count += 1
                    break
                except Exception as exc:
                    last_err = str(exc)
                    self.logger.warning(
                        f"Delivery attempt {attempt + 1}/{sub.max_retries} "
                        f"failed for consumer '{sub.consumer_id}': {exc}"
                    )

            if not success:
                # Quarantine in Dead-Letter Queue
                dlq_id = f"dlq_{secrets.token_hex(8)}"
                dlq_msg = DeadLetterMessage(
                    id=dlq_id,
                    topic=clean_topic,
                    consumer_id=sub.consumer_id,
                    event=event,
                    error_reason=last_err,
                    retry_count=sub.max_retries,
                )
                with self._lock:
                    self._dlq[dlq_id] = dlq_msg
                self.logger.error(
                    f"Quarantined message '{event.id}' in DLQ '{dlq_id}' "
                    f"for consumer '{sub.consumer_id}': {last_err}"
                )

        return delivery_count

    def get_topic_history(self, topic: str, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent events published to a topic."""
        clean_topic = topic.strip().lower()
        with self._lock:
            events = self._history.get(clean_topic, [])
            slice_start = max(0, len(events) - limit)
            return [e.to_dict() for e in reversed(events[slice_start:])]

    def get_dlq(self) -> list[dict[str, Any]]:
        """Retrieve all poisoned messages currently in the Dead-Letter Queue."""
        with self._lock:
            return [msg.to_dict() for msg in self._dlq.values()]

    def replay_dlq(self, dlq_id: str) -> bool:
        """Replay a dead-letter message to its target consumer."""
        with self._lock:
            msg = self._dlq.get(dlq_id)
            if not msg:
                return False

            subscribers = self._subscriptions.get(msg.topic, [])
            target_sub = next(
                (s for s in subscribers if s.consumer_id == msg.consumer_id), None
            )

        if not target_sub:
            self.logger.warning(
                f"Cannot replay DLQ message '{dlq_id}': "
                f"consumer '{msg.consumer_id}' not found"
            )
            return False

        try:
            target_sub.callback(msg.event)
            with self._lock:
                del self._dlq[dlq_id]
            self.logger.info(f"Replayed and removed DLQ message '{dlq_id}'")
            return True
        except Exception as exc:
            self.logger.error(f"Replay failed for DLQ message '{dlq_id}': {exc}")
            return False

    def clear_dlq(self) -> None:
        """Purge all records from the Dead-Letter Queue."""
        with self._lock:
            self._dlq.clear()

    def clear_all(self) -> None:
        """Reset broker subscriptions, history, and DLQ."""
        with self._lock:
            self._subscriptions.clear()
            self._history.clear()
            self._dlq.clear()


# Default process-level broker instance
_DEFAULT_BROKER: Optional[MessageBroker] = None
_BROKER_LOCK = threading.RLock()


def get_message_broker() -> MessageBroker:
    """Retrieve global shared MessageBroker instance."""
    global _DEFAULT_BROKER
    with _BROKER_LOCK:
        if _DEFAULT_BROKER is None:
            _DEFAULT_BROKER = MessageBroker()
        return _DEFAULT_BROKER
