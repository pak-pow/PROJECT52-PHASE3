"""Authentication, user registration, and profile routes."""

from flask import Blueprint, current_app, jsonify, request

from app.config.settings import Config
from app.db.connection import get_db_connection
from app.services.auth_service import AuthService
from app.services.decorators import _resolve_user_id
from app.services.entitlements_service import EntitlementsService

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new customer account and return an initial bearer token."""
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "")
    password = payload.get("password", "")
    full_name = payload.get("full_name", "")
    role = payload.get("role", "user")

    if not email or not password or not full_name:
        return (
            jsonify(
                {
                    "error": "invalid_payload",
                    "message": (
                        "Fields 'email', 'password', and 'full_name' are required."
                    ),
                }
            ),
            400,
        )

    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        auth_service = AuthService(conn)
        try:
            user, token = auth_service.register_user(
                email=email,
                password=password,
                full_name=full_name,
                role=role,
            )
        except ValueError as exc:
            msg = str(exc)
            status_code = 409 if "already registered" in msg.lower() else 400
            return (
                jsonify(
                    {
                        "error": "registration_failed",
                        "message": msg,
                    }
                ),
                status_code,
            )

        return (
            jsonify(
                {
                    "user": user,
                    "token": token,
                    "message": "User registered successfully.",
                }
            ),
            201,
        )
    finally:
        conn.close()


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate existing customer credentials and return a session token."""
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "")
    password = payload.get("password", "")

    if not email or not password:
        return (
            jsonify(
                {
                    "error": "invalid_payload",
                    "message": "Fields 'email' and 'password' are required.",
                }
            ),
            400,
        )

    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        auth_service = AuthService(conn)
        auth_result = auth_service.authenticate_user(email=email, password=password)
        if not auth_result:
            return (
                jsonify(
                    {
                        "error": "invalid_credentials",
                        "message": "Invalid email or password.",
                    }
                ),
                401,
            )

        user, token = auth_result
        return (
            jsonify(
                {
                    "user": user,
                    "token": token,
                    "message": "Authentication successful.",
                }
            ),
            200,
        )
    finally:
        conn.close()


@auth_bp.route("/me", methods=["GET"])
def get_current_user():
    """Retrieve profile and active subscription details for authenticated user."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        auth_service = AuthService(conn)
        user = auth_service.get_user_by_id(user_id)
        if not user:
            return (
                jsonify(
                    {
                        "error": "user_not_found",
                        "message": f"User '{user_id}' does not exist.",
                    }
                ),
                404,
            )

        entitlements_service = EntitlementsService(conn)
        plan, subscription = entitlements_service.get_user_plan(user_id)

        return (
            jsonify(
                {
                    "user": user,
                    "plan": plan.to_dict(),
                    "subscription": subscription.to_dict() if subscription else None,
                }
            ),
            200,
        )
    finally:
        conn.close()
