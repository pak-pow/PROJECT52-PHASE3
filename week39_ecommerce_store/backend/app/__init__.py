import os
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

from app.config.settings import get_config
from app.db import close_db, init_db
from app.routes.cart_routes import cart_bp
from app.routes.health_routes import health_bp
from app.routes.order_routes import order_bp
from app.routes.product_routes import product_bp
from app.routes.webhook_routes import webhook_bp


def create_app(config_class=None):
    app = Flask(__name__)

    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    app.teardown_appcontext(close_db)

    app.register_blueprint(health_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(webhook_bp)

    @app.errorhandler(400)
    def bad_request(error):
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "BAD_REQUEST",
                    "message": getattr(error, "description", "Bad Request"),
                }
            ),
            400,
        )

    @app.errorhandler(404)
    def not_found(error):
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "NOT_FOUND",
                    "message": "Resource was not found.",
                }
            ),
            404,
        )

    @app.errorhandler(405)
    def method_not_allowed(error):
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "METHOD_NOT_ALLOWED",
                    "message": "The HTTP method is not allowed for this endpoint.",
                }
            ),
            405,
        )

    @app.errorhandler(500)
    def internal_error(error):
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected server error occurred.",
                }
            ),
            500,
        )

    db_path = app.config.get("DATABASE_PATH")
    if db_path and db_path != ":memory:":
        db_file = Path(db_path)
        if not db_file.exists():
            os.makedirs(db_file.parent, exist_ok=True)
            with app.app_context():
                init_db()

    return app
