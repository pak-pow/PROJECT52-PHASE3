"""Authorization code model and persistence lifecycle implementing RFC 6749."""

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple


class AuthCodeModel:
    """Manages ephemeral authorization codes, PKCE links, and single-use redemption."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        client_id: str,
        user_id: int,
        redirect_uri: str,
        scope: str,
        ttl_seconds: int = 60,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
        nonce: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Issue a new cryptographically random authorization code with TTL."""
        code = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO authorization_codes (
                code, client_id, user_id, redirect_uri, scope,
                code_challenge, code_challenge_method, nonce, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                client_id,
                user_id,
                redirect_uri,
                scope,
                code_challenge,
                code_challenge_method.upper() if code_challenge_method else None,
                nonce,
                expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        return AuthCodeModel.get_by_code(conn, code)  # type: ignore

    @staticmethod
    def get_by_code(conn: sqlite3.Connection, code: str) -> Optional[Dict[str, Any]]:
        """Retrieve authorization code record by code string."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, code, client_id, user_id, redirect_uri, scope,
                   code_challenge, code_challenge_method, nonce,
                   expires_at, used_at, created_at
            FROM authorization_codes WHERE code = ?
            """,
            (code,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    @staticmethod
    def validate_code(
        conn: sqlite3.Connection, code: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Verify code exists, has not been used, and has not expired."""
        record = AuthCodeModel.get_by_code(conn, code)
        if not record:
            return False, None, "Invalid authorization code."

        if record.get("used_at"):
            return False, record, "Authorization code has already been redeemed."

        expires_val = record.get("expires_at")
        if expires_val:
            if isinstance(expires_val, str):
                expires_at = datetime.strptime(
                    expires_val, "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
            elif isinstance(expires_val, datetime):
                expires_at = (
                    expires_val.replace(tzinfo=timezone.utc)
                    if expires_val.tzinfo is None
                    else expires_val
                )
            else:
                expires_at = None

            if expires_at:
                now = datetime.now(timezone.utc)
                if now > expires_at:
                    return False, record, "Authorization code has expired."

        return True, record, ""

    @staticmethod
    def mark_used(conn: sqlite3.Connection, code: str) -> bool:
        """Atomically mark authorization code as redeemed to prevent replay attacks."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE authorization_codes
            SET used_at = ?
            WHERE code = ? AND used_at IS NULL
            """,
            (now, code),
        )
        conn.commit()
        return cur.rowcount > 0
