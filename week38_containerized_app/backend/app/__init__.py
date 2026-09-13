"""Application factory module for Docker Pulse Task & Ops Hub."""

from flask import Flask, jsonify
from flask_cors import CORS

from app.config.settings import get_config
from app.db import init_db
from app.routes.health_routes import health_bp
from app.routes.task_routes import task_bp


def create_app(config_name: str = None, init_database: bool = True) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # Enable Cross-Origin Resource Sharing on API routes
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register Blueprints
    app.register_blueprint(health_bp, url_prefix="/api/v1")
    app.register_blueprint(task_bp, url_prefix="/api/v1")

    # Initialize Database Tables
    if init_database:
        try:
            init_db(app.config.get("DATABASE_URL"))
        except Exception as exc:
            app.logger.warning(
                f"Database auto-initialization skipped or deferred: {exc}"
            )

    # Register standard JSON error handlers
    @app.errorhandler(404)
    def handle_not_found(err):
        return jsonify({"error": "Resource not found."}), 404

    @app.errorhandler(500)
    def handle_server_error(err):
        return jsonify({"error": "Internal server error."}), 500

    return app
