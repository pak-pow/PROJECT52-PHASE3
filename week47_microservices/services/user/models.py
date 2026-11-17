"""Isolated SQLite database models for User & Identity Service."""

import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> str:
    """Current UTC timestamp as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class UserModel:
    """Database persistence manager for users and addresses."""

    @staticmethod
    def get_connection(db_path: str = ":memory:") -> sqlite3.Connection:
        """Create and configure SQLite connection with WAL mode and row factory."""
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    @classmethod
    def init_db(cls, conn: sqlite3.Connection) -> None:
        """Initialize relational schema for users and addresses."""
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'customer',
                    api_key TEXT UNIQUE NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS addresses (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    street TEXT NOT NULL,
                    city TEXT NOT NULL,
                    country TEXT NOT NULL,
                    postal_code TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """)

    @classmethod
    def create_user(
        cls,
        conn: sqlite3.Connection,
        email: str,
        full_name: str,
        role: str = "customer",
    ) -> dict[str, Any]:
        """Create a new user account with unique API key."""
        clean_email = email.strip().lower()
        clean_name = full_name.strip()

        if not clean_email:
            raise ValueError("Email cannot be empty")
        if not clean_name:
            raise ValueError("Full name cannot be empty")

        user_id = f"usr_{secrets.token_hex(8)}"
        api_key = f"pk_{secrets.token_hex(16)}"
        now = utc_now()

        with conn:
            try:
                conn.execute(
                    """
                    INSERT INTO users (
                        id, email, full_name, role, api_key, is_active, created_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?);
                    """,
                    (user_id, clean_email, clean_name, role, api_key, now),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"User with email '{clean_email}' already exists")

        user = cls.get_by_id(conn, user_id)
        assert user is not None
        return user

    @classmethod
    def get_by_id(
        cls, conn: sqlite3.Connection, user_id: str
    ) -> Optional[dict[str, Any]]:
        """Retrieve user record by user ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @classmethod
    def get_by_email(
        cls, conn: sqlite3.Connection, email: str
    ) -> Optional[dict[str, Any]]:
        """Retrieve user record by email address."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?;", (email.strip().lower(),))
        row = cursor.fetchone()
        return dict(row) if row else None

    @classmethod
    def get_by_api_key(
        cls, conn: sqlite3.Connection, api_key: str
    ) -> Optional[dict[str, Any]]:
        """Retrieve user record by API key."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE api_key = ?;", (api_key.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None

    @classmethod
    def list_users(
        cls, conn: sqlite3.Connection, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List user records with pagination."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?;",
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def add_address(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        street: str,
        city: str,
        country: str,
        postal_code: str,
        is_default: bool = False,
    ) -> dict[str, Any]:
        """Add a postal address linked to a user."""
        user = cls.get_by_id(conn, user_id)
        if not user:
            raise ValueError(f"User '{user_id}' does not exist")

        addr_id = f"addr_{secrets.token_hex(8)}"
        now = utc_now()

        with conn:
            if is_default:
                conn.execute(
                    "UPDATE addresses SET is_default = 0 WHERE user_id = ?;",
                    (user_id,),
                )
            conn.execute(
                """
                INSERT INTO addresses (
                    id, user_id, street, city,
                    country, postal_code, is_default, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    addr_id,
                    user_id,
                    street.strip(),
                    city.strip(),
                    country.strip(),
                    postal_code.strip(),
                    1 if is_default else 0,
                    now,
                ),
            )

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM addresses WHERE id = ?;", (addr_id,))
        row = cursor.fetchone()
        assert row is not None
        return dict(row)

    @classmethod
    def get_addresses(
        cls, conn: sqlite3.Connection, user_id: str
    ) -> list[dict[str, Any]]:
        """Retrieve all addresses for a user."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM addresses
            WHERE user_id = ?
            ORDER BY is_default DESC, created_at ASC;
            """,
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def authenticate_api_key(
        cls, conn: sqlite3.Connection, api_key: str
    ) -> Optional[dict[str, Any]]:
        """Authenticate user by API key, returning user dict if active."""
        user = cls.get_by_api_key(conn, api_key)
        if user and user.get("is_active"):
            return user
        return None
