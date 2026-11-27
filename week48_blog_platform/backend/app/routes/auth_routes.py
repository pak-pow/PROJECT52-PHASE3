"""Authentication and user profile HTTP routes for PulsePress."""

from flask import Blueprint, Response, current_app, g, jsonify, request

from app.db.connection import get_db_connection
from app.services.auth_service import AuthenticationError, AuthService, require_auth

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register() -> tuple[Response, int]:
    """Register a new author account and return user metadata + JWT token."""
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "")
    email = payload.get("email", "")
    password = payload.get("password", "")
    display_name = payload.get("display_name")
    bio = payload.get("bio", "")

    try:
        with get_db_connection(current_app.config["DB_PATH"]) as conn:
            user, token = AuthService.register_user(
                conn=conn,
                username=username,
                email=email,
                password=password,
                secret_key=current_app.config["SECRET_KEY"],
                display_name=display_name,
                bio=bio,
            )
    except ValueError as exc:
        msg = str(exc)
        status_code = 409 if "already" in msg else 400
        return jsonify({"status": "error", "message": msg}), status_code

    return (
        jsonify({"status": "success", "data": {"user": user, "token": token}}),
        201,
    )


@auth_bp.route("/login", methods=["POST"])
def login() -> tuple[Response, int]:
    """Authenticate user credentials and issue an HS256 JWT token."""
    payload = request.get_json(silent=True) or {}
    identifier = payload.get("username") or payload.get("email") or ""
    password = payload.get("password", "")

    try:
        with get_db_connection(current_app.config["DB_PATH"]) as conn:
            user, token = AuthService.login_user(
                conn=conn,
                identifier=identifier,
                password=password,
                secret_key=current_app.config["SECRET_KEY"],
            )
    except AuthenticationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 401

    return jsonify({"status": "success", "data": {"user": user, "token": token}}), 200


@auth_bp.route("/me", methods=["GET"])
@require_auth()
def me() -> tuple[Response, int]:
    """Return the currently authenticated user profile."""
    return jsonify({"status": "success", "data": {"user": g.current_user}}), 200
