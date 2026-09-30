from flask import Flask, jsonify
from flask_cors import CORS
from app.config.settings import Config
from app.db import init_app, init_db
from app.routes.health_routes import health_bp
from app.routes.sync_routes import sync_bp
from app.routes.task_routes import task_bp


def create_app(test_config=None):
    """Application factory creating and configuring the Flask application."""
    app = Flask(__name__)

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_object(test_config)

    # Initialize CORS for cross-origin PWA requests
    CORS(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGIN", "*")}})

    # Initialize DB lifecycle
    init_app(app)

    # Initialize schema tables
    with app.app_context():
        init_db(app)

    # Register Blueprints under /api prefix
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(task_bp, url_prefix="/api")
    app.register_blueprint(sync_bp, url_prefix="/api")

    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({"status": "error", "message": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return (
            jsonify({"status": "error", "message": "Internal server error"}),
            500,
        )

    return app
