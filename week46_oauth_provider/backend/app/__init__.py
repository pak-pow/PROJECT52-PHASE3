"""Application factory for PulseAuth OAuth 2.0 / OIDC Identity Provider."""

from pathlib import Path
from typing import Optional, Type

from flask import Flask, jsonify
from flask_cors import CORS

from app.config.settings import Config, get_config
from app.crypto.rsa_manager import RSAKeyManager
from app.db.connection import close_db, init_db
from app.routes.discovery_routes import discovery_bp


def create_app(config_class: Optional[Type[Config]] = None) -> Flask:
    """Instantiate and configure the Flask PulseAuth application."""
    app = Flask(__name__)

    active_config = config_class or get_config()
    app.config.from_object(active_config)

    # Enable CORS
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Teardown database connections
    app.teardown_appcontext(close_db)

    # Initialize RSA Cryptographic Engine
    keys_dir = Path(app.config.get("DATA_DIR", ".")) / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)

    priv_path = app.config.get("RSA_PRIVATE_KEY_PATH")
    pub_path = app.config.get("RSA_PUBLIC_KEY_PATH")

    rsa_manager = RSAKeyManager(
        private_key_path=priv_path,
        public_key_path=pub_path,
        auto_generate=True,
        key_size=app.config.get("RSA_KEY_SIZE", 2048),
    )
    app.extensions["rsa_manager"] = rsa_manager

    # Ensure schema is ready
    with app.app_context():
        init_db(app.config.get("DATABASE_PATH"))

    # Register blueprints
    app.register_blueprint(discovery_bp)

    # Global Error Handlers
    @app.errorhandler(400)
    def handle_bad_request(err):
        return (
            jsonify({"error": "invalid_request", "error_description": str(err)}),
            400,
        )

    @app.errorhandler(404)
    def handle_not_found(err):
        return (
            jsonify({"error": "not_found", "error_description": "Resource not found."}),
            404,
        )

    @app.errorhandler(500)
    def handle_server_error(err):
        return (
            jsonify(
                {
                    "error": "server_error",
                    "error_description": "Internal identity server error.",
                }
            ),
            500,
        )

    return app
