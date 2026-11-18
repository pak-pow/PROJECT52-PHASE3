"""Flask REST application for Order Service & Saga Coordinator."""

from typing import Optional

from flask import Flask, jsonify, request

from services.order.models import OrderModel
from services.order.saga import OrderSagaCoordinator
from shared.client import PulseClient
from shared.config import BaseMeshConfig, get_config
from shared.logging import setup_mesh_logger
from shared.message_broker import MessageBroker, get_message_broker
from shared.models import CorrelationContext
from shared.registration import ServiceRegistrar


def create_order_app(
    config_class: Optional[type[BaseMeshConfig]] = None,
    db_path: str = ":memory:",
    instance_id: Optional[str] = None,
    registrar: Optional[ServiceRegistrar] = None,
    pulse_client: Optional[PulseClient] = None,
    broker: Optional[MessageBroker] = None,
    coordinator: Optional[OrderSagaCoordinator] = None,
) -> Flask:
    """Application factory for Order Service & Saga Coordinator."""
    cfg = config_class or get_config()
    app = Flask(__name__)
    app.config.from_object(cfg)

    inst_id = instance_id or f"order-service-{cfg.PORT_ORDER_SERVICE}"
    logger = setup_mesh_logger("order-service", inst_id)

    # Initialize isolated SQLite database
    conn = OrderModel.get_connection(db_path)
    OrderModel.init_db(conn)
    app.db_conn = conn  # type: ignore[attr-defined]
    app.instance_id = inst_id  # type: ignore[attr-defined]

    # Initialize Saga Coordinator
    saga_broker = broker or get_message_broker()
    saga_coord = coordinator or OrderSagaCoordinator(
        conn=conn,
        pulse_client=pulse_client,
        broker=saga_broker,
        logger=logger,
    )
    app.coordinator = saga_coord  # type: ignore[attr-defined]
    app.broker = saga_broker  # type: ignore[attr-defined]

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
        """Vitality health probe reporting service status and instance ID."""
        return (
            jsonify(
                {
                    "status": "UP",
                    "service": "order-service",
                    "instance_id": inst_id,
                }
            ),
            200,
        )

    @app.route("/api/v1/orders", methods=["POST"])
    def create_order():
        """Initiate distributed checkout saga to validate, reserve and create order."""
        data = request.get_json(silent=True) or {}
        user_id = data.get("user_id")
        items = data.get("items")
        simulate_payment_failure = bool(data.get("simulate_payment_failure", False))

        if not user_id or not isinstance(user_id, str):
            return (
                jsonify({"error": "user_id is required and must be a string"}),
                400,
            )

        if not items or not isinstance(items, list):
            return (
                jsonify({"error": "items is required and must be a non-empty list"}),
                400,
            )

        # Calculate or extract total cents
        total_cents = data.get("total_cents")
        if total_cents is None:
            total_cents = sum(
                it.get("price_cents", 0) * it.get("quantity", 1) for it in items
            )
        elif not isinstance(total_cents, int) or total_cents < 0:
            return (
                jsonify({"error": "total_cents must be a non-negative integer"}),
                400,
            )

        corr_id = CorrelationContext.get_correlation_id()
        result = app.coordinator.execute_saga(  # type: ignore[attr-defined]
            user_id=user_id,
            total_cents=total_cents,
            items=items,
            correlation_id=corr_id,
            simulate_payment_failure=simulate_payment_failure,
        )

        if result.get("success"):
            return jsonify(result), 201

        status_code = 400
        if result.get("status") == "CANCELLED":
            status_code = 402  # Payment Required / cancelled
        elif result.get("failed_step") == "VERIFY_USER":
            status_code = 422

        return jsonify(result), status_code

    @app.route("/api/v1/orders/<order_id>", methods=["GET"])
    def get_order(order_id: str):
        """Retrieve order details by order identifier."""
        conn = app.db_conn  # type: ignore[attr-defined]
        order = OrderModel.get_order(conn, order_id)
        if not order:
            return jsonify({"error": f"Order '{order_id}' not found"}), 404
        return jsonify({"order": order}), 200

    @app.route("/api/v1/orders/<order_id>/saga-trace", methods=["GET"])
    def get_saga_trace(order_id: str):
        """Retrieve execution audit trace of all distributed saga steps."""
        conn = app.db_conn  # type: ignore[attr-defined]
        order = OrderModel.get_order(conn, order_id)
        if not order:
            return jsonify({"error": f"Order '{order_id}' not found"}), 404

        trace = OrderModel.get_saga_trace(conn, order_id)
        return jsonify({"order_id": order_id, "trace": trace}), 200

    @app.route("/api/v1/orders", methods=["GET"])
    def list_orders():
        """Query and list orders with optional user_id filter."""
        user_id = request.args.get("user_id")
        limit = request.args.get("limit", 50, type=int)

        conn = app.db_conn  # type: ignore[attr-defined]
        orders = OrderModel.list_orders(conn, user_id=user_id, limit=limit)
        return jsonify({"orders": orders, "count": len(orders)}), 200

    return app
