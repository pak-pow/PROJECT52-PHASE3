"""Unit and integration tests for Notification & Audit Service."""

import sqlite3

import pytest

from services.notification.app import create_notification_app
from services.notification.consumer import NotificationConsumer
from services.notification.models import NotificationModel
from shared.message_broker import MessageBroker
from shared.models import CloudEvent


@pytest.fixture
def notif_db() -> sqlite3.Connection:
    """Fixture providing an in-memory SQLite database for Notification Service."""
    conn = NotificationModel.get_connection(":memory:")
    NotificationModel.init_db(conn)
    return conn


@pytest.fixture
def broker() -> MessageBroker:
    """Fixture providing an isolated MessageBroker."""
    return MessageBroker()


def test_notification_model_crud(notif_db: sqlite3.Connection):
    """Test NotificationModel insertion and retrieval."""
    notif = NotificationModel.create_notification(
        conn=notif_db,
        user_id="usr_test_notif",
        channel="EMAIL",
        event_type="order.completed",
        subject="Order Confirmation",
        body="Your order has shipped.",
        correlation_id="corr_test_notif",
    )
    assert notif["id"].startswith("ntf_")
    assert notif["user_id"] == "usr_test_notif"
    assert notif["channel"] == "EMAIL"
    assert notif["status"] == "SENT"

    # Fetch by user
    user_notifs = NotificationModel.get_notifications_for_user(
        notif_db, "usr_test_notif"
    )
    assert len(user_notifs) == 1
    assert user_notifs[0]["id"] == notif["id"]

    # List all
    all_notifs = NotificationModel.list_notifications(notif_db)
    assert len(all_notifs) == 1


def test_notification_model_idempotency(notif_db: sqlite3.Connection):
    """Test idempotency tracking for processed event identifiers."""
    evt_id = "evt_dedup_001"
    assert NotificationModel.is_event_processed(notif_db, evt_id) is False

    # Mark processed
    ok1 = NotificationModel.mark_event_processed(notif_db, evt_id, "order.completed")
    assert ok1 is True
    assert NotificationModel.is_event_processed(notif_db, evt_id) is True

    # Mark duplicate event fails integrity check
    ok2 = NotificationModel.mark_event_processed(notif_db, evt_id, "order.completed")
    assert ok2 is False

    # Check list
    records = NotificationModel.list_processed_events(notif_db)
    assert len(records) == 1
    assert records[0]["event_id"] == evt_id


def test_notification_consumer_processes_order_completed(
    notif_db: sqlite3.Connection, broker: MessageBroker
):
    """Test consumer dispatches confirmation notification on order.completed."""
    consumer = NotificationConsumer(
        conn=notif_db,
        broker=broker,
        topic="orders.events",
    )
    consumer.start()

    event = CloudEvent.create(
        source="order-service",
        event_type="order.completed",
        data={
            "order_id": "ord_999",
            "user_id": "usr_buyer",
            "total_cents": 4999,
        },
        correlation_id="corr_order_completed",
    )

    broker.publish("orders.events", event)

    # Verify notification was inserted
    notifs = NotificationModel.get_notifications_for_user(notif_db, "usr_buyer")
    assert len(notifs) == 1
    assert notifs[0]["subject"] == "Order ord_999 Confirmed"
    assert "$49.99" in notifs[0]["body"]
    assert notifs[0]["correlation_id"] == "corr_order_completed"

    # Verify idempotency log
    assert NotificationModel.is_event_processed(notif_db, event.id) is True
    consumer.stop()


def test_notification_consumer_processes_order_cancelled(
    notif_db: sqlite3.Connection, broker: MessageBroker
):
    """Test consumer dispatches cancellation notification on order.cancelled."""
    consumer = NotificationConsumer(
        conn=notif_db,
        broker=broker,
        topic="orders.events",
    )
    consumer.start()

    event = CloudEvent.create(
        source="order-service",
        event_type="order.cancelled",
        data={
            "order_id": "ord_888",
            "user_id": "usr_cancelled",
            "reason": "Payment card declined",
        },
        correlation_id="corr_order_cancelled",
    )

    broker.publish("orders.events", event)

    notifs = NotificationModel.get_notifications_for_user(notif_db, "usr_cancelled")
    assert len(notifs) == 1
    assert notifs[0]["subject"] == "Order ord_888 Cancelled"
    assert "Payment card declined" in notifs[0]["body"]
    consumer.stop()


def test_notification_consumer_idempotency_deduplication(
    notif_db: sqlite3.Connection, broker: MessageBroker
):
    """Test duplicate message delivery does not create duplicate notifications."""
    consumer = NotificationConsumer(
        conn=notif_db,
        broker=broker,
        topic="orders.events",
    )
    consumer.start()

    event = CloudEvent.create(
        source="order-service",
        event_type="order.completed",
        data={
            "order_id": "ord_dup",
            "user_id": "usr_dup",
            "total_cents": 1000,
        },
    )

    # Publish twice
    broker.publish("orders.events", event)
    broker.publish("orders.events", event)

    notifs = NotificationModel.get_notifications_for_user(notif_db, "usr_dup")
    assert len(notifs) == 1  # Exactly one notification stored
    consumer.stop()


def test_notification_consumer_unhandled_event(
    notif_db: sqlite3.Connection, broker: MessageBroker
):
    """Test consumer gracefully records unknown event without creating notifications."""
    consumer = NotificationConsumer(
        conn=notif_db,
        broker=broker,
        topic="orders.events",
    )
    consumer.start()

    event = CloudEvent.create(
        source="unknown-service",
        event_type="custom.ping",
        data={"message": "hello"},
    )
    broker.publish("orders.events", event)

    notifs = NotificationModel.list_notifications(notif_db)
    assert len(notifs) == 0
    assert NotificationModel.is_event_processed(notif_db, event.id) is True
    consumer.stop()


def test_notification_service_rest_api():
    """Test Notification Service REST endpoints via Flask test client."""
    app = create_notification_app(db_path=":memory:")
    client = app.test_client()

    # 1. Health probe
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json["service"] == "notification-service"

    # 2. Seed notification
    NotificationModel.create_notification(
        conn=app.db_conn,  # type: ignore[attr-defined]
        user_id="usr_api_test",
        channel="EMAIL",
        event_type="order.completed",
        subject="Hello",
        body="World",
        correlation_id="corr_1",
    )

    # 3. List all notifications
    res = client.get("/api/v1/notifications")
    assert res.status_code == 200
    assert res.json["count"] == 1

    # 4. List notifications for user
    res = client.get("/api/v1/notifications/user/usr_api_test")
    assert res.status_code == 200
    assert res.json["count"] == 1
    assert res.json["notifications"][0]["user_id"] == "usr_api_test"

    # 5. List processed events
    res = client.get("/api/v1/notifications/processed-events")
    assert res.status_code == 200
    assert "processed_events" in res.json
