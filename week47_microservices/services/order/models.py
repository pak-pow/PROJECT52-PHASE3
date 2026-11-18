"""Isolated SQLite database models for Order Service and Saga Coordinator."""

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> str:
    """Current UTC timestamp as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class OrderModel:
    """Database persistence manager for orders and distributed saga steps."""

    @staticmethod
    def get_connection(db_path: str = ":memory:") -> sqlite3.Connection:
        """Create and configure SQLite connection with WAL mode and row factory."""
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @classmethod
    def init_db(cls, conn: sqlite3.Connection) -> None:
        """Initialize relational schema for orders and saga audit steps."""
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_cents INTEGER NOT NULL,
                    items_json TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saga_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
                );
                """)

    @classmethod
    def create_order(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        total_cents: int,
        items: list[dict[str, Any]],
        correlation_id: str,
        order_id: Optional[str] = None,
        status: str = "PENDING",
    ) -> dict[str, Any]:
        """Create a new order record in PENDING status."""
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise ValueError("User ID cannot be empty")
        if total_cents < 0:
            raise ValueError("Total cents cannot be negative")
        if not items:
            raise ValueError("Order items cannot be empty")

        new_id = order_id or f"ord_{secrets.token_hex(8)}"
        now = utc_now()
        items_payload = json.dumps(items)

        with conn:
            conn.execute(
                """
                INSERT INTO orders (
                    id,
                    user_id,
                    status,
                    total_cents,
                    items_json,
                    correlation_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    new_id,
                    clean_user_id,
                    status.upper(),
                    total_cents,
                    items_payload,
                    correlation_id.strip(),
                    now,
                    now,
                ),
            )

        order = cls.get_order(conn, new_id)
        if not order:
            raise RuntimeError(f"Failed to retrieve newly created order {new_id}")
        return order

    @classmethod
    def update_order_status(
        cls,
        conn: sqlite3.Connection,
        order_id: str,
        status: str,
    ) -> bool:
        """Update an order status and updated_at timestamp."""
        now = utc_now()
        with conn:
            cursor = conn.execute(
                """
                UPDATE orders
                SET status = ?, updated_at = ?
                WHERE id = ?;
                """,
                (status.upper(), now, order_id),
            )
            return cursor.rowcount > 0

    @classmethod
    def get_order(
        cls,
        conn: sqlite3.Connection,
        order_id: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve single order by ID with parsed items."""
        cursor = conn.execute(
            """
            SELECT
                id,
                user_id,
                status,
                total_cents,
                items_json,
                correlation_id,
                created_at,
                updated_at
            FROM orders
            WHERE id = ?;
            """,
            (order_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "status": row["status"],
            "total_cents": row["total_cents"],
            "items": json.loads(row["items_json"]),
            "correlation_id": row["correlation_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @classmethod
    def list_orders(
        cls,
        conn: sqlite3.Connection,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List orders filtered by user_id or return recent orders."""
        if user_id:
            cursor = conn.execute(
                """
                SELECT
                    id,
                    user_id,
                    status,
                    total_cents,
                    items_json,
                    correlation_id,
                    created_at,
                    updated_at
                FROM orders
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (user_id, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT
                    id,
                    user_id,
                    status,
                    total_cents,
                    items_json,
                    correlation_id,
                    created_at,
                    updated_at
                FROM orders
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
                    "status": row["status"],
                    "total_cents": row["total_cents"],
                    "items": json.loads(row["items_json"]),
                    "correlation_id": row["correlation_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return results

    @classmethod
    def record_saga_step(
        cls,
        conn: sqlite3.Connection,
        order_id: str,
        step_name: str,
        status: str,
        details: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record an execution step in the distributed saga transaction."""
        now = utc_now()
        details_str = json.dumps(details or {})
        clean_status = status.upper()

        with conn:
            cursor = conn.execute(
                """
                INSERT INTO saga_steps (
                    order_id,
                    step_name,
                    status,
                    details_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (order_id, step_name.upper(), clean_status, details_str, now),
            )
            step_id = cursor.lastrowid

        return {
            "id": step_id,
            "order_id": order_id,
            "step_name": step_name.upper(),
            "status": clean_status,
            "details": details or {},
            "created_at": now,
        }

    @classmethod
    def get_saga_trace(
        cls,
        conn: sqlite3.Connection,
        order_id: str,
    ) -> list[dict[str, Any]]:
        """Retrieve audit trace of all saga steps executed for an order."""
        cursor = conn.execute(
            """
            SELECT
                id,
                order_id,
                step_name,
                status,
                details_json,
                created_at
            FROM saga_steps
            WHERE order_id = ?
            ORDER BY id ASC;
            """,
            (order_id,),
        )

        trace = []
        for row in cursor.fetchall():
            trace.append(
                {
                    "id": row["id"],
                    "order_id": row["order_id"],
                    "step_name": row["step_name"],
                    "status": row["status"],
                    "details": json.loads(row["details_json"]),
                    "created_at": row["created_at"],
                }
            )
        return trace
