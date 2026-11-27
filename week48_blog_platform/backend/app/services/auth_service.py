"""JWT Bearer authentication and role-based access control service for PulsePress."""

import base64
import hashlib
import hmac
import json
import sqlite3
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from flask import current_app, g, jsonify, request

from app.db.connection import get_db_connection
from app.models.user import UserDAO


class AuthenticationError(ValueError):
    """Raised when credentials or JWT tokens are invalid or expired."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


class AuthService:
    """Stateless HS256 JWT token management and user authentication."""

    DEFAULT_TTL_SECONDS = 86400  # 24 hours

    @staticmethod
    def create_token(
        user: Dict[str, Any],
        secret_key: str,
        expires_in: int = DEFAULT_TTL_SECONDS,
    ) -> str:
        """Create an HS256 signed JWT token for an authenticated user."""
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": str(user["id"]),
            "username": user["username"],
            "role": user["role"],
            "iat": now,
            "exp": now + expires_in,
        }
        header_b64 = _b64url_encode(
            json.dumps(header, separators=(",", ":")).encode("utf-8")
        )
        payload_b64 = _b64url_encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = hmac.new(
            secret_key.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"

    @staticmethod
    def decode_token(token: str, secret_key: str) -> Dict[str, Any]:
        """Verify HS256 signature and expiration, returning the decoded payload."""
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthenticationError("Malformed JWT token.")

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(
            secret_key.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()

        try:
            actual_sig = _b64url_decode(sig_b64)
        except Exception as exc:
            raise AuthenticationError("Invalid token encoding.") from exc

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise AuthenticationError("Invalid token signature.")

        try:
            payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        except Exception as exc:
            raise AuthenticationError("Invalid token payload.") from exc

        exp = payload.get("exp")
        if not isinstance(exp, (int, float)) or exp < int(time.time()):
            raise AuthenticationError("Token has expired.")

        return payload

    @staticmethod
    def sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
        """Strip password_hash before returning user data to API callers."""
        clean = dict(user)
        clean.pop("password_hash", None)
        return clean

    @staticmethod
    def register_user(
        conn: sqlite3.Connection,
        username: str,
        email: str,
        password: str,
        secret_key: str,
        display_name: Optional[str] = None,
        bio: str = "",
    ) -> Tuple[Dict[str, Any], str]:
        """Validate registration input, create user, and issue JWT token."""
        clean_username = username.strip()
        clean_email = email.strip().lower()
        clean_display = (display_name or clean_username).strip()

        if len(clean_username) < 3:
            raise ValueError("Username must be at least 3 characters.")
        if "@" not in clean_email or "." not in clean_email:
            raise ValueError("A valid email address is required.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")

        if UserDAO.get_by_username(conn, clean_username):
            raise ValueError(f"Username '{clean_username}' is already taken.")
        if UserDAO.get_by_email(conn, clean_email):
            raise ValueError(f"Email '{clean_email}' is already registered.")

        created = UserDAO.create(
            conn=conn,
            username=clean_username,
            email=clean_email,
            password=password,
            display_name=clean_display,
            bio=bio.strip(),
            role="author",
        )
        safe_user = AuthService.sanitize_user(created)
        token = AuthService.create_token(safe_user, secret_key=secret_key)
        return safe_user, token

    @staticmethod
    def login_user(
        conn: sqlite3.Connection,
        identifier: str,
        password: str,
        secret_key: str,
    ) -> Tuple[Dict[str, Any], str]:
        """Authenticate by username or email and return sanitized user + JWT."""
        clean_id = identifier.strip()
        if not clean_id or not password:
            raise AuthenticationError("Username/email and password are required.")

        user = UserDAO.get_by_username(conn, clean_id)
        if not user:
            user = UserDAO.get_by_email(conn, clean_id.lower())

        if not user or not UserDAO.verify_password(user, password):
            raise AuthenticationError("Invalid credentials.")

        safe_user = AuthService.sanitize_user(user)
        token = AuthService.create_token(safe_user, secret_key=secret_key)
        return safe_user, token

    @staticmethod
    def resolve_optional_user(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
        """Attempt to resolve Bearer token from request headers without failing."""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:].strip()
        if not token:
            return None
        try:
            payload = AuthService.decode_token(token, current_app.config["SECRET_KEY"])
            user = UserDAO.get_by_id(conn, int(payload["sub"]))
            return AuthService.sanitize_user(user) if user else None
        except Exception:
            return None


def require_auth(roles: Optional[Sequence[str]] = None) -> Callable[..., Any]:
    """Decorator enforcing JWT Bearer authentication and optional role membership."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Authorization Bearer token required.",
                        }
                    ),
                    401,
                )

            token = auth_header[7:].strip()
            try:
                payload = AuthService.decode_token(
                    token, current_app.config["SECRET_KEY"]
                )
            except AuthenticationError as exc:
                return jsonify({"status": "error", "message": str(exc)}), 401

            with get_db_connection(current_app.config["DB_PATH"]) as conn:
                user = UserDAO.get_by_id(conn, int(payload["sub"]))

            if not user:
                return (
                    jsonify({"status": "error", "message": "User account not found."}),
                    401,
                )

            safe_user = AuthService.sanitize_user(user)
            if roles and safe_user.get("role") not in roles:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Insufficient permissions for this action.",
                        }
                    ),
                    403,
                )

            g.current_user = safe_user
            return fn(*args, **kwargs)

        return wrapper

    return decorator
