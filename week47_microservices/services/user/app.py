"""Flask REST application for User & Identity microservice."""

from typing import Optional

from flask import Flask, jsonify, request

from services.user.models import UserModel
from shared.config import BaseMeshConfig, get_config
from shared.logging import setup_mesh_logger
from shared.models import CorrelationContext
from shared.registration import ServiceRegistrar


def create_user_app(
    config_class: Optional[type[BaseMeshConfig]] = None,
    db_path: str = ":memory:",
    instance_id: Optional[str] = None,
    registrar: Optional[ServiceRegistrar] = None,
) -> Flask:
    """Application factory for User & Identity Service."""
    cfg = config_class or get_config()
    app = Flask(__name__)
    app.config.from_object(cfg)

    inst_id = instance_id or f"user-service-{cfg.PORT_USER_SERVICE}"
    logger = setup_mesh_logger("user-service", inst_id)

    # Initialize isolated SQLite database
    conn = UserModel.get_connection(db_path)
    UserModel.init_db(conn)
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
                    "service": "user-service",
                    "instance_id": inst_id,
                }
            ),
            200,
        )

    @app.route("/api/v1/users", methods=["POST"])
    def create_user():
        """Register a new user profile."""
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return (
                jsonify({"error": "invalid_payload", "message": "JSON body required"}),
                400,
            )

        email = payload.get("email", "")
        full_name = payload.get("full_name", "")
        role = payload.get("role", "customer")

        try:
            user = UserModel.create_user(conn, email, full_name, role)
            logger.info(f"Created user '{user['id']}' ({user['email']})")
            return jsonify(user), 201
        except ValueError as err:
            return jsonify({"error": "validation_error", "message": str(err)}), 400

    @app.route("/api/v1/users/<user_id>", methods=["GET"])
    def get_user(user_id: str):
        """Retrieve user profile along with registered addresses."""
        user = UserModel.get_by_id(conn, user_id)
        if not user:
            return (
                jsonify(
                    {
                        "error": "user_not_found",
                        "message": f"User '{user_id}' not found",
                    }
                ),
                404,
            )

        addresses = UserModel.get_addresses(conn, user_id)
        user["addresses"] = addresses
        return jsonify(user), 200

    @app.route("/api/v1/users", methods=["GET"])
    def list_users():
        """List registered users with pagination."""
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        users = UserModel.list_users(conn, limit=limit, offset=offset)
        return jsonify({"count": len(users), "users": users}), 200

    @app.route("/api/v1/users/<user_id>/addresses", methods=["POST"])
    def add_user_address(user_id: str):
        """Add a postal address to a user profile."""
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return (
                jsonify({"error": "invalid_payload", "message": "JSON body required"}),
                400,
            )

        street = payload.get("street", "")
        city = payload.get("city", "")
        country = payload.get("country", "")
        postal_code = payload.get("postal_code", "")
        is_default = bool(payload.get("is_default", False))

        try:
            addr = UserModel.add_address(
                conn=conn,
                user_id=user_id,
                street=street,
                city=city,
                country=country,
                postal_code=postal_code,
                is_default=is_default,
            )
            return jsonify(addr), 201
        except ValueError as err:
            return jsonify({"error": "validation_error", "message": str(err)}), 400

    @app.route("/api/v1/users/authenticate", methods=["POST"])
    def authenticate():
        """Authenticate user credentials by API key."""
        payload = request.get_json(silent=True) or {}
        api_key = payload.get("api_key", "").strip()

        if not api_key:
            return (
                jsonify({"error": "missing_api_key", "message": "api_key is required"}),
                400,
            )

        user = UserModel.authenticate_api_key(conn, api_key)
        if not user:
            return (
                jsonify({"error": "invalid_credentials", "message": "Invalid API key"}),
                401,
            )

        return jsonify({"status": "authenticated", "user": user}), 200

    return app
