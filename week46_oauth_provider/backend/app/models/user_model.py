"""User entity model and credential management for PulseAuth."""

import sqlite3
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash


class UserModel:
    """Manages user persistence, authentication, and profile lookups."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        email: str,
        password: str,
        full_name: str,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """Create a new user with securely hashed password."""
        normalized_email = email.strip().lower()
        pwd_hash = generate_password_hash(password, method="scrypt")

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (email, password_hash, full_name, is_active)
            VALUES (?, ?, ?, ?)
            """,
            (normalized_email, pwd_hash, full_name.strip(), 1 if is_active else 0),
        )
        conn.commit()
        user_id = cur.lastrowid
        return UserModel.get_by_id(conn, user_id)  # type: ignore

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch user by primary key ID."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, email, password_hash, full_name,
                   is_active, created_at, updated_at
            FROM users WHERE id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    @staticmethod
    def get_by_email(conn: sqlite3.Connection, email: str) -> Optional[Dict[str, Any]]:
        """Fetch user by unique email address."""
        normalized_email = email.strip().lower()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, email, password_hash, full_name,
                   is_active, created_at, updated_at
            FROM users WHERE email = ?
            """,
            (normalized_email,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    @staticmethod
    def verify_credentials(
        conn: sqlite3.Connection, email: str, password: str
    ) -> Optional[Dict[str, Any]]:
        """Authenticate user by email and password, returning profile if valid."""
        user = UserModel.get_by_email(conn, email)
        if not user or not user["is_active"]:
            return None

        if check_password_hash(user["password_hash"], password):
            # Return safe dictionary without password_hash
            safe_user = dict(user)
            safe_user.pop("password_hash", None)
            return safe_user

        return None

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """List all users omitting sensitive password hashes."""
        cur = conn.cursor()
        cur.execute("""
            SELECT id, email, full_name, is_active, created_at, updated_at
            FROM users ORDER BY id ASC
            """)
        return [dict(r) for r in cur.fetchall()]
