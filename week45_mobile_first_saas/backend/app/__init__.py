"""PulseSub Flask application factory."""

from pathlib import Path
from typing import Any, Optional

from flask import Flask, Response

from app.config.settings import Config, get_config
from app.db.connection import init_db
from app.routes.health import health_bp
from app.routes.static_routes import static_bp


def create_app(config: Optional[Any] = None) -> Flask:
    """Create and configure the PulseSub Flask application instance."""
    app_cfg = config or get_config()

    app = Flask(
        __name__,
        static_folder=None,
    )

    # Apply configuration
    if isinstance(app_cfg, dict):
        app.config.from_mapping(app_cfg)
    else:
        app.config.from_object(app_cfg)

    # Initialize database schema if database file does not exist yet
    db_path = app.config.get("DB_PATH", Config.DB_PATH)
    if str(db_path) != ":memory:" and not Path(db_path).exists():
        init_db(db_path=db_path, seed_defaults=True)

    # Register HTTP blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(static_bp)

    # Standard security and CORS headers
    @app.after_request
    def apply_security_headers(response: Response) -> Response:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, Stripe-Signature, X-Request-ID"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    return app
