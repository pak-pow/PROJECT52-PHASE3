"""Isolated SQLite database models for Notification & Audit Service."""

import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> str:
    """Current UTC timestamp as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class NotificationModel:
    """Database persistence manager for notifications and event deduplication."""

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
        """Initialize relational schema for notifications and processed event audit."""
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );
                """)

    @classmethod
    def is_event_processed(cls, conn: sqlite3.Connection, event_id: str) -> bool:
        """Check if an event has already been consumed (idempotency check)."""
        cursor = conn.execute(
            "SELECT 1 FROM processed_events WHERE event_id = ?;",
            (event_id,),
        )
        return cursor.fetchone() is not None

    @classmethod
    def mark_event_processed(
        cls,
        conn: sqlite3.Connection,
        event_id: str,
        event_type: str,
    ) -> bool:
        """Record an event identifier to ensure exactly-once semantics."""
        now = utc_now()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO processed_events (event_id, event_type, processed_at)
                    VALUES (?, ?, ?);
                    """,
                    (event_id, event_type, now),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @classmethod
    def create_notification(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        channel: str,
        event_type: str,
        subject: str,
        body: str,
        correlation_id: str,
        status: str = "SENT",
        notif_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Insert a newly dispatched customer notification."""
        new_id = notif_id or f"ntf_{secrets.token_hex(8)}"
        now = utc_now()

        with conn:
            conn.execute(
                """
                INSERT INTO notifications (
                    id,
                    user_id,
                    channel,
                    event_type,
                    subject,
                    body,
                    status,
                    correlation_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    new_id,
                    user_id.strip(),
                    channel.strip().upper(),
                    event_type.strip(),
                    subject.strip(),
                    body.strip(),
                    status.strip().upper(),
                    correlation_id.strip(),
                    now,
                ),
            )

        return {
            "id": new_id,
            "user_id": user_id.strip(),
            "channel": channel.strip().upper(),
            "event_type": event_type.strip(),
            "subject": subject.strip(),
            "body": body.strip(),
            "status": status.strip().upper(),
            "correlation_id": correlation_id.strip(),
            "created_at": now,
        }

    @classmethod
    def get_notifications_for_user(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve historical notifications sent to a specific user."""
        cursor = conn.execute(
            """
            SELECT
                id,
                user_id,
                channel,
                event_type,
                subject,
                body,
                status,
                correlation_id,
                created_at
            FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (user_id, limit),
        )

        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "channel": row["channel"],
                    "event_type": row["event_type"],
                    "subject": row["subject"],
                    "body": row["body"],
                    "status": row["status"],
                    "correlation_id": row["correlation_id"],
                    "created_at": row["created_at"],
                }
            )
        return results

    @classmethod
    def list_notifications(
        cls,
        conn: sqlite3.Connection,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List all recent dispatched notifications across the platform."""
        cursor = conn.execute(
            """
            SELECT
                id,
                user_id,
                channel,
                event_type,
                subject,
                body,
                status,
                correlation_id,
                created_at
            FROM notifications
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (limit,),
        )

        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "channel": row["channel"],
                    "event_type": row["event_type"],
                    "subject": row["subject"],
                    "body": row["body"],
                    "status": row["status"],
                    "correlation_id": row["correlation_id"],
                    "created_at": row["created_at"],
                }
            )
        return results

    @classmethod
    def list_processed_events(
        cls,
        conn: sqlite3.Connection,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List recent processed event identifiers from the idempotency log."""
        cursor = conn.execute(
            """
            SELECT
                event_id,
                event_type,
                processed_at
            FROM processed_events
            ORDER BY processed_at DESC
            LIMIT ?;
            """,
            (limit,),
        )

        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "processed_at": row["processed_at"],
                }
            )
        return results
