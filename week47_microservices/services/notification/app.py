"""Flask REST application for Notification & Audit microservice."""

from typing import Optional

from flask import Flask, jsonify, request

from services.notification.consumer import NotificationConsumer
from services.notification.models import NotificationModel
from shared.config import BaseMeshConfig, get_config
from shared.logging import setup_mesh_logger
from shared.message_broker import MessageBroker, get_message_broker
from shared.models import CorrelationContext
from shared.registration import ServiceRegistrar


def create_notification_app(
    config_class: Optional[type[BaseMeshConfig]] = None,
    db_path: str = ":memory:",
    instance_id: Optional[str] = None,
    registrar: Optional[ServiceRegistrar] = None,
    broker: Optional[MessageBroker] = None,
    consumer: Optional[NotificationConsumer] = None,
) -> Flask:
    """Application factory for Notification & Audit Service."""
    cfg = config_class or get_config()
    app = Flask(__name__)
    app.config.from_object(cfg)

    inst_id = instance_id or f"notification-service-{cfg.PORT_NOTIFICATION_SERVICE}"
    logger = setup_mesh_logger("notification-service", inst_id)

    # Initialize isolated SQLite database
    conn = NotificationModel.get_connection(db_path)
    NotificationModel.init_db(conn)
    app.db_conn = conn  # type: ignore[attr-defined]
    app.instance_id = inst_id  # type: ignore[attr-defined]

    # Initialize and start Event Consumer
    event_broker = broker or get_message_broker()
    app.broker = event_broker  # type: ignore[attr-defined]

    worker = consumer or NotificationConsumer(
        conn=conn,
        broker=event_broker,
        topic="orders.events",
        consumer_id=f"notification-worker-{inst_id}",
        logger=logger,
    )
    worker.start()
    app.consumer = worker  # type: ignore[attr-defined]

    # Optional self-registration with Service Registry
    if registrar is not None:
        registrar.register()
        registrar.start_heartbeat()
        app.registrar = registrar  # type: ignore[attr-defined]

    @app.before_request
    def set_correlation() -> None:
        """Extract or generate distributed correlation identifier."""
        corr_id = request.headers.get("X-Correlation-ID")
        if not corr_id:
            corr_id = CorrelationContext.generate_correlation_id()
        CorrelationContext.set_correlation_id(corr_id)

    @app.after_request
    def attach_correlation(response):
        """Append correlation identifier to outbound response headers."""
        response.headers["X-Correlation-ID"] = CorrelationContext.get_correlation_id()
        response.headers["X-Instance-ID"] = inst_id
        return response

    @app.route("/health", methods=["GET"])
    def health_probe():
        """Vitality health probe reporting service and instance ID."""
        return (
            jsonify(
                {
                    "status": "UP",
                    "service": "notification-service",
                    "instance_id": inst_id,
                }
            ),
            200,
        )

    @app.route("/api/v1/notifications", methods=["GET"])
    def list_notifications():
        """List all recent dispatched notifications across the platform."""
        limit = request.args.get("limit", 50, type=int)
        conn = app.db_conn  # type: ignore[attr-defined]
        items = NotificationModel.list_notifications(conn, limit=limit)
        return jsonify({"notifications": items, "count": len(items)}), 200

    @app.route("/api/v1/notifications/user/<user_id>", methods=["GET"])
    def get_user_notifications(user_id: str):
        """Retrieve dispatched notifications for a specific user."""
        limit = request.args.get("limit", 50, type=int)
        conn = app.db_conn  # type: ignore[attr-defined]
        items = NotificationModel.get_notifications_for_user(
            conn, user_id=user_id, limit=limit
        )
        return (
            jsonify({"user_id": user_id, "notifications": items, "count": len(items)}),
            200,
        )

    @app.route("/api/v1/notifications/processed-events", methods=["GET"])
    def list_processed_events():
        """Retrieve the idempotency log of processed event IDs."""
        limit = request.args.get("limit", 50, type=int)
        events = NotificationModel.list_processed_events(  # type: ignore[attr-defined]
            app.db_conn, limit=limit
        )
        return jsonify({"processed_events": events, "count": len(events)}), 200

    return app
