from flask import Flask, jsonify
from flask_cors import CORS

from app.config.settings import Config
from app.db import init_app, init_db
from app.routes.graphql_routes import graphql_bp
from app.routes.health_routes import health_bp


def create_app(test_config=None):
    """Application factory creating and configuring the Flask application."""
    app = Flask(__name__)

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_object(test_config)

    # Enable CORS for GraphQL clients and explorer
    CORS(
        app,
        resources={
            r"/graphql*": {"origins": app.config.get("CORS_ORIGIN", "*")},
            r"/api/*": {"origins": app.config.get("CORS_ORIGIN", "*")},
        },
    )

    # Initialize DB connection lifecycle
    init_app(app)

    # Initialize schema tables
    with app.app_context():
        init_db(app)

    # Register Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(graphql_bp)

    @app.errorhandler(404)
    def not_found_error(error):
        return (
            jsonify({"status": "error", "message": "Resource not found"}),
            404,
        )

    @app.errorhandler(500)
    def internal_error(error):
        return (
            jsonify({"status": "error", "message": "Internal server error"}),
            500,
        )

    return app
