"""Token model and persistence lifecycle implementing RFC 6749 and RFC 7009."""

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import jwt


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
        resource: Optional[str] = None,
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
                scope, token_family_id, expires_at, resource
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                resource,
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
                   scope, token_family_id, expires_at, revoked_at, created_at, resource
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
                   scope, token_family_id, expires_at, revoked_at, created_at, resource
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
                   scope, token_family_id, expires_at, revoked_at, created_at, resource
            FROM tokens WHERE jti = ?
            """,
            (jti,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    @staticmethod
    def parse_datetime(dt_val: Any) -> Optional[datetime]:
        """Parse sqlite datetime string or timestamp into timezone-aware datetime."""
        if not dt_val:
            return None
        if isinstance(dt_val, datetime):
            return (
                dt_val.replace(tzinfo=timezone.utc) if dt_val.tzinfo is None else dt_val
            )
        if isinstance(dt_val, str):
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
            ):
                try:
                    return datetime.strptime(dt_val, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
        return None

    @staticmethod
    def find_token(
        conn: sqlite3.Connection, raw_token: str
    ) -> Optional[Dict[str, Any]]:
        """Lookup token by raw token value hash, or if JWT by jti claim."""
        if not raw_token:
            return None
        record = TokenModel.get_by_raw_token(conn, raw_token)
        if record:
            return record

        if raw_token.count(".") == 2:
            try:
                unverified = jwt.decode(raw_token, options={"verify_signature": False})
                jti = unverified.get("jti")
                if jti:
                    return TokenModel.get_by_jti(conn, jti)
            except Exception:
                pass
        return None

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

        expires_at = TokenModel.parse_datetime(record.get("expires_at"))
        if expires_at and datetime.now(timezone.utc) > expires_at:
            return False, record, "Token has expired."

        return True, record, ""

    @staticmethod
    def revoke_by_hash(conn: sqlite3.Connection, token_hash: str) -> bool:
        """Mark single token as revoked by SHA-256 value hash."""
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
    def revoke(conn: sqlite3.Connection, raw_token: str) -> bool:
        """Mark single token as revoked by raw token value."""
        token_hash = TokenModel.hash_token(raw_token)
        return TokenModel.revoke_by_hash(conn, token_hash)

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

    @staticmethod
    def revoke_user_tokens(
        conn: sqlite3.Connection, user_id: int, client_id: Optional[str] = None
    ) -> int:
        """Revoke all active tokens for a specific user (and optionally client)."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.cursor()
        if client_id:
            cur.execute(
                """
                UPDATE tokens
                SET revoked_at = ?
                WHERE user_id = ? AND client_id = ? AND revoked_at IS NULL
                """,
                (now_str, user_id, client_id),
            )
        else:
            cur.execute(
                """
                UPDATE tokens
                SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (now_str, user_id),
            )
        conn.commit()
        return cur.rowcount

    @staticmethod
    def get_family_tokens(
        conn: sqlite3.Connection, token_family_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieve all tokens associated with a given family identifier."""
        if not token_family_id:
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, token_type, token_value_hash, jti, client_id, user_id,
                   scope, token_family_id, expires_at, revoked_at, created_at, resource
            FROM tokens WHERE token_family_id = ?
            ORDER BY created_at ASC
            """,
            (token_family_id,),
        )
        return [dict(r) for r in cur.fetchall()]
