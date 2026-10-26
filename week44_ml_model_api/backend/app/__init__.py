"""PulseInfer Flask application factory."""

from pathlib import Path
from typing import Any, Optional

from flask import Flask, Response

from app.config.settings import Config, get_config
from app.db.connection import init_db
from app.routes.health import health_bp
from app.routes.static_routes import static_bp
from app.services.storage_service import StorageService


def create_app(config: Optional[Any] = None) -> Flask:
    """Create and configure the PulseInfer Flask application instance."""
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

    # Initialize storage directories
    vault_dir = app.config.get("MODELS_VAULT_DIR", Config.MODELS_VAULT_DIR)
    storage = StorageService(vault_dir=vault_dir)
    storage.ensure_storage_dirs()

    # Initialize database schema if database file does not exist yet
    db_path = app.config.get("DB_PATH", Config.DB_PATH)
    if str(db_path) != ":memory:" and not Path(db_path).exists():
        init_db(db_path=db_path)

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(static_bp)

    # CORS Headers for API client compatibility
    @app.after_request
    def apply_cors_headers(response: Response) -> Response:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Request-ID"
        )
        return response

    return app
