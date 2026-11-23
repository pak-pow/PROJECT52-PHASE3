"""User data access object for PulsePress."""

import sqlite3
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash


class UserDAO:
    """Data Access Object for user accounts and roles."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        username: str,
        email: str,
        password: str,
        display_name: str,
        bio: str = "",
        avatar_url: str = "",
        role: str = "author",
    ) -> Dict[str, Any]:
        """Create and persist a new user account."""
        password_hash = generate_password_hash(password)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (
                username, email, password_hash, display_name, bio, avatar_url, role
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (username, email, password_hash, display_name, bio, avatar_url, role),
        )
        conn.commit()
        user_id = cursor.lastrowid
        return UserDAO.get_by_id(conn, user_id)  # type: ignore

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve user record by numeric ID."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, username, email, password_hash, display_name, bio,
                   avatar_url, role, created_at
            FROM users WHERE id = ?;
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_username(
        conn: sqlite3.Connection, username: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve user record by unique username."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, username, email, password_hash, display_name, bio,
                   avatar_url, role, created_at
            FROM users WHERE username = ?;
            """,
            (username,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_email(conn: sqlite3.Connection, email: str) -> Optional[Dict[str, Any]]:
        """Retrieve user record by unique email."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, username, email, password_hash, display_name, bio,
                   avatar_url, role, created_at
            FROM users WHERE email = ?;
            """,
            (email,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def verify_password(user: Dict[str, Any], password: str) -> bool:
        """Check password against user password hash."""
        pwd_hash = user.get("password_hash", "")
        return check_password_hash(pwd_hash, password)

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """List all users without password hashes."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, email, display_name, bio, avatar_url, role,
                   created_at
            FROM users ORDER BY id ASC;
            """)
        return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def update(
        conn: sqlite3.Connection, user_id: int, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        """Update mutable fields on user account."""
        allowed_keys = {"display_name", "bio", "avatar_url", "role"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_keys}
        if not updates:
            return UserDAO.get_by_id(conn, user_id)

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        params = list(updates.values()) + [user_id]

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE users SET {set_clause} WHERE id = ?;",  # nosec B608
            params,
        )
        conn.commit()
        return UserDAO.get_by_id(conn, user_id)

    @staticmethod
    def delete(conn: sqlite3.Connection, user_id: int) -> bool:
        """Delete user account by ID."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?;", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
