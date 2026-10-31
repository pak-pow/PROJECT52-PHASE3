"""Flask application factory for PulsePad collaborative editor."""

import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from app.config.settings import Config
from app.db.connection import init_db
from app.routes.document_routes import document_bp
from app.routes.health_routes import health_bp


def create_app(config_class=Config) -> Flask:
    """Create and configure the Flask application."""
    frontend_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    )
    app = Flask(__name__)
    app.config.from_object(config_class)

    cors_origins = app.config.get("CORS_ALLOWED_ORIGINS", "*")
    CORS(app, resources={r"/*": {"origins": cors_origins}})

    app.register_blueprint(health_bp)
    app.register_blueprint(document_bp, url_prefix="/api")

    @app.route("/")
    def index():
        """Serve the frontend workbench shell."""
        public_dir = os.path.join(frontend_dir, "public")
        return send_from_directory(public_dir, "index.html")

    @app.route("/src/<path:filename>")
    def serve_frontend_src(filename: str):
        """Serve frontend module assets."""
        src_dir = os.path.join(frontend_dir, "src")
        return send_from_directory(src_dir, filename)

    if not app.config.get("TESTING", False):
        try:
            init_db(app.config.get("DB_PATH"))
            # Auto-seed default document if table is empty
            from app.db.connection import get_db_connection

            with get_db_connection(app.config.get("DB_PATH")) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM documents")
                if cur.fetchone()[0] == 0:
                    from data.seed import seed_database

                    seed_database()
        except (OSError, FileNotFoundError) as exc:
            app.logger.warning("Could not auto-initialize database: %s", exc)

    return app
