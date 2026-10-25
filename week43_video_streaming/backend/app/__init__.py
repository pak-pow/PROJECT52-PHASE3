"""PulseStream Flask application factory."""

from pathlib import Path
from typing import Any, Optional

from flask import Flask, Response, send_file, send_from_directory

from app.config.settings import Config, get_config
from app.db.connection import init_db
from app.routes.health import health_bp
from app.routes.job_routes import job_bp
from app.routes.video_routes import video_bp
from app.services.storage_service import StorageService
from app.services.transcoding_service import TranscodingQueue


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
    media_dir = app.config.get("MEDIA_DIR")
    storage = StorageService(media_dir=media_dir)
    storage.ensure_storage_dirs()

    db_path = app.config.get("DB_PATH", Config.DB_PATH)
    if str(db_path) != ":memory:" and not Path(db_path).exists():
        init_db(db_path=db_path)

    # Attach transcoding queue
    is_testing = app.config.get("TESTING", False)
    app.transcoding_queue = TranscodingQueue(
        db_path=db_path,
        media_dir=storage.media_dir,
        autostart_worker=not is_testing,
    )

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(job_bp)

    # Static frontend routes
    @app.route("/")
    def index() -> Any:
        index_file = Path(Config.FRONTEND_DIR) / "public" / "index.html"
        if index_file.exists():
            return send_file(index_file)
        return "PulseStream API is running", 200

    @app.route("/src/<path:filename>")
    def serve_frontend_src(filename: str) -> Any:
        src_dir = Path(Config.FRONTEND_DIR) / "src"
        return send_from_directory(src_dir, filename)

    @app.route("/public/<path:filename>")
    def serve_frontend_public(filename: str) -> Any:
        public_dir = Path(Config.FRONTEND_DIR) / "public"
        return send_from_directory(public_dir, filename)

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
