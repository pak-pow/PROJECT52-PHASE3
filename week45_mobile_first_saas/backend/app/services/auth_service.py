"""Authentication and session credential services for PulseSub."""

import base64
import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from app.config.settings import Config


def hash_password(password: str) -> str:
    """Generate deterministic salted SHA256 password hash for authentication."""
    salt = "pulsesub_demo_salt_2026"
    return hashlib.sha256(f"{salt}_{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Validate plaintext password against stored salted hash in constant time."""
    computed = hash_password(password)
    return hmac.compare_digest(computed, hashed)


def create_auth_token(
    user_id: str,
    email: str,
    role: str = "user",
    secret_key: Optional[str] = None,
    expires_in_seconds: int = 604800,  # 7 days
) -> str:
    """Issue a signed HMAC-SHA256 bearer token encoding user claims."""
    key = secret_key or Config.SECRET_KEY
    now = int(time.time())
    payload = {
        "uid": user_id,
        "eml": email,
        "rol": role,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    raw_json = json.dumps(payload, separators=(",", ":"))
    b64_payload = (
        base64.urlsafe_b64encode(raw_json.encode("utf-8")).decode("utf-8").rstrip("=")
    )
    sig = hmac.new(
        key.encode("utf-8"),
        b64_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"pst_{b64_payload}.{sig}"


def verify_auth_token(
    token: str,
    secret_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Verify bearer token signature, expiration, and decode claims."""
    key = secret_key or Config.SECRET_KEY
    if not token or not token.startswith("pst_"):
        return None

    stripped = token[4:]
    if "." not in stripped:
        return None

    b64_payload, sig = stripped.rsplit(".", 1)
    expected_sig = hmac.new(
        key.encode("utf-8"),
        b64_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

    if not hmac.compare_digest(expected_sig, sig):
        return None

    padding = "=" * ((4 - len(b64_payload) % 4) % 4)
    try:
        decoded_bytes = base64.urlsafe_b64decode(b64_payload + padding)
        payload = json.loads(decoded_bytes.decode("utf-8"))
    except (ValueError, TypeError):
        return None

    now = int(time.time())
    if payload.get("exp", 0) < now:
        return None

    return {
        "user_id": payload.get("uid"),
        "email": payload.get("eml"),
        "role": payload.get("rol", "user"),
        "issued_at": payload.get("iat"),
        "expires_at": payload.get("exp"),
    }


class AuthService:
    """Service managing customer account registration and authentication."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def register_user(
        self,
        email: str,
        password: str,
        full_name: str,
        role: str = "user",
    ) -> Tuple[Dict[str, Any], str]:
        """Register customer account, validate input, and issue a session token."""
        clean_email = email.strip().lower()
        clean_name = full_name.strip()

        if not clean_email or "@" not in clean_email or "." not in clean_email:
            raise ValueError("A valid email address is required.")
        if len(password) < 6:
            raise ValueError("Password must contain at least 6 characters.")
        if not clean_name:
            raise ValueError("Full name cannot be blank.")

        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?;", (clean_email,))
        existing = cursor.fetchone()
        if existing:
            cursor.close()
            raise ValueError(f"Email '{clean_email}' is already registered.")

        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        password_hashed = hash_password(password)
        now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

        cursor.execute(
            """
            INSERT INTO users (
                id, email, password_hash, full_name, role, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                user_id,
                clean_email,
                password_hashed,
                clean_name,
                role,
                now_str,
                now_str,
            ),
        )
        self.conn.commit()
        cursor.close()

        user_dict = {
            "id": user_id,
            "email": clean_email,
            "full_name": clean_name,
            "role": role,
            "created_at": now_str,
            "updated_at": now_str,
        }
        token = create_auth_token(user_id=user_id, email=clean_email, role=role)
        return user_dict, token

    def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        """Authenticate existing credentials and issue a new bearer token."""
        clean_email = email.strip().lower()
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?;", (clean_email,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        if not verify_password(password, row["password_hash"]):
            return None

        user_dict = {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "role": row["role"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        token = create_auth_token(
            user_id=row["id"],
            email=row["email"],
            role=row["role"],
        )
        return user_dict, token

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch user profile excluding sensitive password hash."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        return {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "role": row["role"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
