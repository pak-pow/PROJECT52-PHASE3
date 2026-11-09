"""Token model and persistence lifecycle implementing RFC 6749 and RFC 7009."""

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


class TokenModel:
    """Manages persistence, hashing, lookup, and revocation of issued tokens."""

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Derive deterministic SHA-256 hex digest for opaque or JWT tokens."""
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        token_type: str,
        raw_token: str,
        client_id: str,
        scope: str,
        expires_at: datetime,
        user_id: Optional[int] = None,
        jti: Optional[str] = None,
        token_family_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a newly issued token into the database using value hashing."""
        if token_type not in ("access_token", "refresh_token", "id_token"):
            raise ValueError(f"Invalid token_type: {token_type}")

        token_hash = TokenModel.hash_token(raw_token)
        expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tokens (
                token_type, token_value_hash, jti, client_id, user_id,
                scope, token_family_id, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_type,
                token_hash,
                jti,
                client_id,
                user_id,
                scope,
                token_family_id,
                expires_str,
            ),
        )
        conn.commit()
        token_id = cur.lastrowid
        return TokenModel.get_by_id(conn, token_id)  # type: ignore

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, token_id: int) -> Optional[Dict[str, Any]]:
        """Fetch token record by primary key ID."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, token_type, token_value_hash, jti, client_id, user_id,
                   scope, token_family_id, expires_at, revoked_at, created_at
            FROM tokens WHERE id = ?
            """,
            (token_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    @staticmethod
    def get_by_hash(
        conn: sqlite3.Connection, token_hash: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve token record using SHA-256 value hash."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, token_type, token_value_hash, jti, client_id, user_id,
                   scope, token_family_id, expires_at, revoked_at, created_at
            FROM tokens WHERE token_value_hash = ?
            """,
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    @staticmethod
    def get_by_raw_token(
        conn: sqlite3.Connection, raw_token: str
    ) -> Optional[Dict[str, Any]]:
        """Compute SHA-256 hash of raw token and look up matching database record."""
        token_hash = TokenModel.hash_token(raw_token)
        return TokenModel.get_by_hash(conn, token_hash)

    @staticmethod
    def get_by_jti(conn: sqlite3.Connection, jti: str) -> Optional[Dict[str, Any]]:
        """Retrieve token record by JWT ID (jti)."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, token_type, token_value_hash, jti, client_id, user_id,
                   scope, token_family_id, expires_at, revoked_at, created_at
            FROM tokens WHERE jti = ?
            """,
            (jti,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    @staticmethod
    def is_valid(
        conn: sqlite3.Connection, raw_token: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Verify token exists, has not been revoked, and has not expired."""
        record = TokenModel.get_by_raw_token(conn, raw_token)
        if not record:
            return False, None, "Token not found."

        if record.get("revoked_at"):
            return False, record, "Token has been revoked."

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

            if expires_at and datetime.now(timezone.utc) > expires_at:
                return False, record, "Token has expired."

        return True, record, ""

    @staticmethod
    def revoke(conn: sqlite3.Connection, raw_token: str) -> bool:
        """Mark single token as revoked by timestamping revoked_at."""
        token_hash = TokenModel.hash_token(raw_token)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tokens
            SET revoked_at = ?
            WHERE token_value_hash = ? AND revoked_at IS NULL
            """,
            (now_str, token_hash),
        )
        conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def revoke_family(conn: sqlite3.Connection, token_family_id: str) -> int:
        """Revoke all tokens sharing the same token family lineage identifier."""
        if not token_family_id:
            return 0
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tokens
            SET revoked_at = ?
            WHERE token_family_id = ? AND revoked_at IS NULL
            """,
            (now_str, token_family_id),
        )
        conn.commit()
        return cur.rowcount
