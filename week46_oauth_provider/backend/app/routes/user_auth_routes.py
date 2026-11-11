"""User authentication and registration API endpoints."""

from flask import Blueprint, jsonify, request

from app.db.connection import get_db
from app.models.user_model import UserModel

user_auth_bp = Blueprint("user_auth", __name__)


@user_auth_bp.route("/api/v1/auth/login", methods=["POST"])
def auth_login():
    """Authenticate user with email and password."""
    conn = get_db()
    data = request.get_json(silent=True) or request.form or {}

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return (
            jsonify(
                {
                    "error": "invalid_request",
                    "error_description": "Missing 'email' or 'password'.",
                }
            ),
            400,
        )

    user = UserModel.verify_credentials(conn, email, password)
    if not user:
        return (
            jsonify(
                {
                    "error": "invalid_credentials",
                    "error_description": "Invalid email or password.",
                }
            ),
            401,
        )

    return (
        jsonify(
            {
                "status": "success",
                "message": "User authenticated successfully.",
                "user": user,
            }
        ),
        200,
    )


@user_auth_bp.route("/api/v1/auth/register", methods=["POST"])
def auth_register():
    """Register a new user account with scrypt password hashing."""
    conn = get_db()
    data = request.get_json(silent=True) or request.form or {}

    email = data.get("email")
    password = data.get("password")
    full_name = data.get("full_name")

    if not email or not password or not full_name:
        return (
            jsonify(
                {
                    "error": "invalid_request",
                    "error_description": (
                        "Missing required fields: email, password, and full_name."
                    ),
                }
            ),
            400,
        )

    if "@" not in email or "." not in email:
        return (
            jsonify(
                {
                    "error": "invalid_request",
                    "error_description": "Invalid email address format.",
                }
            ),
            400,
        )

    if len(password) < 8:
        return (
            jsonify(
                {
                    "error": "invalid_request",
                    "error_description": (
                        "Password must be at least 8 characters long."
                    ),
                }
            ),
            400,
        )

    existing = UserModel.get_by_email(conn, email)
    if existing:
        return (
            jsonify(
                {
                    "error": "conflict",
                    "error_description": "Email address already registered.",
                }
            ),
            409,
        )

    created_user = UserModel.create(
        conn=conn, email=email, password=password, full_name=full_name
    )
    safe_user = dict(created_user)
    safe_user.pop("password_hash", None)

    return (
        jsonify(
            {
                "status": "created",
                "message": "User registered successfully.",
                "user": safe_user,
            }
        ),
        201,
    )


@user_auth_bp.route("/api/v1/auth/users", methods=["GET"])
def list_users():
    """List registered users (omitting sensitive password hashes)."""
    conn = get_db()
    users = UserModel.list_all(conn)
    return jsonify({"status": "success", "count": len(users), "data": users}), 200
