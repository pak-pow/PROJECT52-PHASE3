"""Flask REST application for Catalog & Inventory microservice."""

from typing import Optional

from flask import Flask, jsonify, request

from services.catalog.inventory import InventoryEngine
from services.catalog.models import CatalogModel
from shared.config import BaseMeshConfig, get_config
from shared.logging import setup_mesh_logger
from shared.models import CorrelationContext
from shared.registration import ServiceRegistrar


def create_catalog_app(
    config_class: Optional[type[BaseMeshConfig]] = None,
    db_path: str = ":memory:",
    instance_id: Optional[str] = None,
    registrar: Optional[ServiceRegistrar] = None,
) -> Flask:
    """Application factory for Catalog & Inventory Service."""
    cfg = config_class or get_config()
    app = Flask(__name__)
    app.config.from_object(cfg)

    inst_id = instance_id or f"catalog-service-{cfg.PORT_CATALOG_SERVICE}"
    logger = setup_mesh_logger("catalog-service", inst_id)

    # Initialize isolated SQLite database
    conn = CatalogModel.get_connection(db_path)
    CatalogModel.init_db(conn)
    app.db_conn = conn  # type: ignore[attr-defined]
    app.instance_id = inst_id  # type: ignore[attr-defined]

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
                    "service": "catalog-service",
                    "instance_id": inst_id,
                }
            ),
            200,
        )

    @app.route("/api/v1/products", methods=["POST"])
    def create_product():
        """Register a new product in the catalog."""
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return (
                jsonify({"error": "invalid_payload", "message": "JSON body required"}),
                400,
            )

        sku = payload.get("sku", "")
        name = payload.get("name", "")
        price_cents = payload.get("price_cents", 0)
        stock_quantity = payload.get("stock_quantity", 0)
        description = payload.get("description", "")

        try:
            product = CatalogModel.create_product(
                conn=conn,
                sku=sku,
                name=name,
                price_cents=price_cents,
                stock_quantity=stock_quantity,
                description=description,
            )
            logger.info(
                f"Created product '{product['id']}' "
                f"({product['sku']} - {product['name']})"
            )
            return jsonify(product), 201
        except ValueError as err:
            return jsonify({"error": "validation_error", "message": str(err)}), 400

    @app.route("/api/v1/products/<product_id>", methods=["GET"])
    def get_product(product_id: str):
        """Retrieve single product details with live available stock."""
        product = CatalogModel.get_by_id(conn, product_id)
        if not product:
            return (
                jsonify(
                    {
                        "error": "product_not_found",
                        "message": f"Product '{product_id}' not found",
                    }
                ),
                404,
            )
        return jsonify(product), 200

    @app.route("/api/v1/products", methods=["GET"])
    def list_products():
        """List products with live stock availability."""
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        products = CatalogModel.list_products(conn, limit=limit, offset=offset)
        return jsonify({"count": len(products), "products": products}), 200

    @app.route("/api/v1/inventory/reserve", methods=["POST"])
    def reserve_stock():
        """Atomically reserve stock for an order saga."""
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return (
                jsonify({"error": "invalid_payload", "message": "JSON body required"}),
                400,
            )

        order_id = payload.get("order_id")
        items = payload.get("items", [])

        try:
            result = InventoryEngine.reserve(conn, order_id=order_id, items=items)
            logger.info(
                f"Reserved stock for order '{order_id}': "
                f"{result['reservation_count']} items"
            )
            return jsonify(result), 200
        except ValueError as err:
            logger.warning(f"Stock reservation rejected for order '{order_id}': {err}")
            return jsonify({"error": "reservation_failed", "message": str(err)}), 400

    @app.route("/api/v1/inventory/release", methods=["POST"])
    def release_stock():
        """Compensating action releasing reserved stock for a cancelled order."""
        payload = request.get_json(silent=True) or {}
        order_id = payload.get("order_id", "").strip()

        if not order_id:
            return (
                jsonify(
                    {"error": "missing_parameter", "message": "order_id is required"}
                ),
                400,
            )

        result = InventoryEngine.release(conn, order_id=order_id)
        logger.info(
            f"Released stock for order '{order_id}': {result['released_count']} items"
        )
        return jsonify(result), 200

    @app.route("/api/v1/inventory/commit", methods=["POST"])
    def commit_stock():
        """Permanently deduct reserved stock upon order completion."""
        payload = request.get_json(silent=True) or {}
        order_id = payload.get("order_id", "").strip()

        if not order_id:
            return (
                jsonify(
                    {"error": "missing_parameter", "message": "order_id is required"}
                ),
                400,
            )

        result = InventoryEngine.commit(conn, order_id=order_id)
        logger.info(
            f"Committed stock for order '{order_id}': {result['committed_count']} items"
        )
        return jsonify(result), 200

    @app.route("/api/v1/inventory/orders/<order_id>", methods=["GET"])
    def get_order_reservations(order_id: str):
        """Retrieve inventory reservation history for an order."""
        reservations = InventoryEngine.get_order_reservations(conn, order_id)
        return (
            jsonify(
                {
                    "order_id": order_id,
                    "count": len(reservations),
                    "reservations": reservations,
                }
            ),
            200,
        )

    return app
