from flask import Flask
from flask_cors import CORS
from app.config.settings import get_config
from app.db import init_db
from app.routes.health_routes import health_bp
from app.routes.deployment_routes import deployment_bp


def create_app(config_class=None):
    """Application factory for the CI/CD Deployment Monitor service."""
    app = Flask(__name__)

    if config_class is None:
        config_class = get_config()

    app.config.from_object(config_class)

    # Enable CORS for API routes
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register Route Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(deployment_bp)

    # Initialize Database Schema
    with app.app_context():
        init_db(app.config["DATABASE_PATH"])

    return app
