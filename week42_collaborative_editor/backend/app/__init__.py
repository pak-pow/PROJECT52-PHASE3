"""Flask application factory for PulsePad collaborative editor."""

from flask import Flask
from flask_cors import CORS

from app.config.settings import Config
from app.db.connection import init_db
from app.routes.document_routes import document_bp
from app.routes.health_routes import health_bp


def create_app(config_class=Config) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    cors_origins = app.config.get("CORS_ALLOWED_ORIGINS", "*")
    CORS(app, resources={r"/*": {"origins": cors_origins}})

    app.register_blueprint(health_bp)
    app.register_blueprint(document_bp, url_prefix="/api")

    if not app.config.get("TESTING", False):
        try:
            init_db(app.config.get("DB_PATH"))
        except Exception:
            pass

    return app
