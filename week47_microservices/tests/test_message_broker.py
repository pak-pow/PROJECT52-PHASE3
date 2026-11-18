"""Unit tests for asynchronous MessageBroker and Dead-Letter Queue."""

from unittest.mock import MagicMock

import pytest

from shared.message_broker import MessageBroker, get_message_broker
from shared.models import CloudEvent


@pytest.fixture
def broker() -> MessageBroker:
    """Fixture providing an isolated MessageBroker instance."""
    return MessageBroker()


def test_broker_subscribe_and_unsubscribe(broker: MessageBroker):
    """Test subscribing to a topic and unsubscribing."""
    cb = MagicMock()
    sub_id = broker.subscribe("orders.events", "worker-1", cb)
    assert sub_id.startswith("sub_")

    # Unsubscribe
    assert broker.unsubscribe("orders.events", "worker-1") is True
    # Unsubscribe again returns False
    assert broker.unsubscribe("orders.events", "worker-1") is False
    # Non-existent topic returns False
    assert broker.unsubscribe("nonexistent.topic", "worker-1") is False


def test_broker_publish_dispatches_to_subscribers(broker: MessageBroker):
    """Test publishing an event delivers to all active subscribers."""
    received_events_1 = []
    received_events_2 = []

    broker.subscribe("orders.events", "worker-1", lambda e: received_events_1.append(e))
    broker.subscribe("orders.events", "worker-2", lambda e: received_events_2.append(e))

    event = CloudEvent.create(
        source="order-service",
        event_type="order.completed",
        data={"order_id": "ord_100", "total_cents": 2500},
    )

    delivered = broker.publish("orders.events", event)
    assert delivered == 2
    assert len(received_events_1) == 1
    assert len(received_events_2) == 1
    assert received_events_1[0].id == event.id
    assert received_events_2[0].data["order_id"] == "ord_100"


def test_broker_topic_history(broker: MessageBroker):
    """Test topic event history recording and limit slicing."""
    for i in range(15):
        event = CloudEvent.create(
            source="order-service",
            event_type="order.step",
            data={"index": i},
        )
        broker.publish("orders.history", event)

    history = broker.get_topic_history("orders.history", limit=5)
    assert len(history) == 5
    # Most recent first
    assert history[0]["data"]["index"] == 14
    assert history[4]["data"]["index"] == 10


def test_broker_quarantines_poison_message_to_dlq(broker: MessageBroker):
    """Test that a failing consumer triggers retry and DLQ quarantine."""
    fail_mock = MagicMock(side_effect=RuntimeError("Database failure"))

    broker.subscribe(
        topic="orders.events",
        consumer_id="failing-worker",
        callback=fail_mock,
        max_retries=3,
    )

    event = CloudEvent.create(
        source="order-service",
        event_type="order.completed",
        data={"order_id": "ord_fail"},
    )

    delivered = broker.publish("orders.events", event)
    assert delivered == 0
    assert fail_mock.call_count == 3

    # Verify DLQ contains quarantined message
    dlq_items = broker.get_dlq()
    assert len(dlq_items) == 1
    dlq_entry = dlq_items[0]
    assert dlq_entry["consumer_id"] == "failing-worker"
    assert dlq_entry["retry_count"] == 3
    assert "Database failure" in dlq_entry["error_reason"]


def test_broker_replay_dlq_success(broker: MessageBroker):
    """Test successful replay of a quarantined dead-letter message."""
    should_fail = True

    def flaky_callback(event: CloudEvent):
        if should_fail:
            raise ValueError("Temporary glitch")
        # Succeeded on replay

    broker.subscribe(
        topic="orders.events",
        consumer_id="flaky-worker",
        callback=flaky_callback,
        max_retries=2,
    )

    event = CloudEvent.create(
        source="order-service",
        event_type="order.completed",
        data={"order_id": "ord_flaky"},
    )

    broker.publish("orders.events", event)
    dlq_items = broker.get_dlq()
    assert len(dlq_items) == 1
    dlq_id = dlq_items[0]["id"]

    # Fix condition and replay
    should_fail = False
    replayed = broker.replay_dlq(dlq_id)
    assert replayed is True

    # DLQ should now be empty
    assert len(broker.get_dlq()) == 0


def test_broker_replay_dlq_missing_or_failing(broker: MessageBroker):
    """Test DLQ replay with missing message ID or removed consumer."""
    assert broker.replay_dlq("dlq_nonexistent") is False

    # Subscriber throws error permanently
    broker.subscribe(
        "orders.events",
        "broken-worker",
        lambda e: (_ for _ in ()).throw(RuntimeError("Permanent error")),
        max_retries=1,
    )

    event = CloudEvent.create(
        source="order-service",
        event_type="order.completed",
        data={"order_id": "ord_broken"},
    )
    broker.publish("orders.events", event)
    dlq_items = broker.get_dlq()
    assert len(dlq_items) == 1
    dlq_id = dlq_items[0]["id"]

    # Replay still fails because callback still throws
    assert broker.replay_dlq(dlq_id) is False
    assert len(broker.get_dlq()) == 1

    # Unsubscribe consumer and replay
    broker.unsubscribe("orders.events", "broken-worker")
    assert broker.replay_dlq(dlq_id) is False


def test_broker_clear_dlq_and_clear_all(broker: MessageBroker):
    """Test purging the DLQ and resetting all broker state."""
    broker.subscribe(
        "alerts",
        "worker",
        lambda e: (_ for _ in ()).throw(ValueError("err")),
        max_retries=1,
    )
    event = CloudEvent.create(source="test", event_type="alert", data={})
    broker.publish("alerts", event)

    assert len(broker.get_dlq()) == 1
    broker.clear_dlq()
    assert len(broker.get_dlq()) == 0

    # Clear all
    broker.clear_all()
    assert len(broker.get_topic_history("alerts")) == 0


def test_global_message_broker_singleton():
    """Test get_message_broker returns singleton instance."""
    b1 = get_message_broker()
    b2 = get_message_broker()
    assert b1 is b2
