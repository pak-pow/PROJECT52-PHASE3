"""PulseStream Flask application factory."""

from pathlib import Path
from typing import Any, Optional

from app.config.settings import Config, get_config
from app.db.connection import init_db
from app.routes.health import health_bp
from app.services.storage_service import StorageService
from flask import Flask, Response


def create_app(config: Optional[Any] = None) -> Flask:
    """Create and configure the PulseStream Flask application instance."""
    app_cfg = config or get_config()

    frontend_dist = Path(Config.FRONTEND_DIR) / "public"
    app = Flask(
        __name__,
        static_folder=str(frontend_dist) if frontend_dist.exists() else None,
        static_url_path="",
    )

    # Apply configuration
    if isinstance(app_cfg, dict):
        app.config.from_mapping(app_cfg)
    else:
        app.config.from_object(app_cfg)

    # Initialize storage and schema if not in testing memory
    storage = StorageService(media_dir=app.config.get("MEDIA_DIR"))
    storage.ensure_storage_dirs()

    db_path = app.config.get("DB_PATH", Config.DB_PATH)
    if str(db_path) != ":memory:" and not Path(db_path).exists():
        init_db(db_path=db_path)

    # Register blueprints
    app.register_blueprint(health_bp)

    # CORS & Streaming Headers
    @app.after_request
    def apply_cors_headers(response: Response) -> Response:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Range, Authorization"
        )
        response.headers["Access-Control-Expose-Headers"] = (
            "Content-Range, Content-Length, Accept-Ranges"
        )
        return response

    return app
