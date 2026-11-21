"""Atomic inventory reservation engine supporting sagas and compensating rollbacks."""

import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from services.catalog.models import CatalogModel


def utc_now() -> str:
    """Current UTC timestamp as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class InventoryEngine:
    """Manages transactional stock reservations, commits, and compensating releases."""

    _lock = threading.RLock()

    @classmethod
    def reserve(
        cls,
        conn: sqlite3.Connection,
        order_id: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Atomically reserve product quantities for an order saga.

        Validates available stock for all items before reserving.
        If any item has insufficient stock, rolls back and raises ValueError.
        """
        if not order_id or not order_id.strip():
            raise ValueError("order_id cannot be empty")
        if not items:
            raise ValueError("items list cannot be empty")

        clean_order_id = order_id.strip()

        with cls._lock, conn:
            # Check if this order is already reserved (idempotency check)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM inventory_reservations
                WHERE order_id = ? AND status = 'RESERVED';
                """,
                (clean_order_id,),
            )
            existing = cursor.fetchall()
            if existing:
                return {
                    "order_id": clean_order_id,
                    "status": "RESERVED",
                    "reservation_count": len(existing),
                    "already_reserved": True,
                }

            # Phase 1: Validate available stock for all items atomically
            for item in items:
                prod_id = item.get("product_id")
                qty = item.get("quantity")

                if not prod_id:
                    raise ValueError("Each item must specify 'product_id'")
                if not isinstance(qty, int) or qty <= 0:
                    raise ValueError("Item quantity must be a positive integer")

                product = CatalogModel.get_by_id(conn, str(prod_id))
                if not product:
                    raise ValueError(f"Product '{prod_id}' not found")

                available = product["available_stock"]
                if qty > available:
                    raise ValueError(
                        f"Insufficient stock for '{product['name']}' ({prod_id}): "
                        f"requested {qty}, available {available}"
                    )

            # Phase 2: Create reservation records
            now = utc_now()
            res_ids = []
            for item in items:
                res_id = f"res_{secrets.token_hex(8)}"
                conn.execute(
                    """
                    INSERT INTO inventory_reservations (
                        id, order_id, product_id,
                        quantity, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'RESERVED', ?, ?);
                    """,
                    (
                        res_id,
                        clean_order_id,
                        str(item["product_id"]),
                        int(item["quantity"]),
                        now,
                        now,
                    ),
                )
                res_ids.append(res_id)

            return {
                "order_id": clean_order_id,
                "status": "RESERVED",
                "reservation_count": len(res_ids),
                "reservation_ids": res_ids,
            }

    @classmethod
    def release(cls, conn: sqlite3.Connection, order_id: str) -> dict[str, Any]:
        """Compensating transaction releasing reserved stock back to available pool."""
        clean_order_id = order_id.strip()
        now = utc_now()

        with cls._lock, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id FROM inventory_reservations
                WHERE order_id = ? AND status = 'RESERVED';
                """,
                (clean_order_id,),
            )
            active_res = cursor.fetchall()

            if active_res:
                conn.execute(
                    """
                    UPDATE inventory_reservations
                    SET status = 'RELEASED', updated_at = ?
                    WHERE order_id = ? AND status = 'RESERVED';
                    """,
                    (now, clean_order_id),
                )

            return {
                "order_id": clean_order_id,
                "status": "RELEASED",
                "released_count": len(active_res),
            }

    @classmethod
    def commit(cls, conn: sqlite3.Connection, order_id: str) -> dict[str, Any]:
        """Commit reservations permanently and deduct from product stock_quantity."""
        clean_order_id = order_id.strip()
        now = utc_now()

        with cls._lock, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, product_id, quantity FROM inventory_reservations
                WHERE order_id = ? AND status = 'RESERVED';
                """,
                (clean_order_id,),
            )
            reservations = cursor.fetchall()

            for res in reservations:
                # Deduct permanently from products table
                conn.execute(
                    """
                    UPDATE products
                    SET stock_quantity = stock_quantity - ?
                    WHERE id = ?;
                    """,
                    (res["quantity"], res["product_id"]),
                )
                # Mark reservation as committed
                conn.execute(
                    """
                    UPDATE inventory_reservations
                    SET status = 'COMMITTED', updated_at = ?
                    WHERE id = ?;
                    """,
                    (now, res["id"]),
                )

            return {
                "order_id": clean_order_id,
                "status": "COMMITTED",
                "committed_count": len(reservations),
            }

    @classmethod
    def get_order_reservations(
        cls, conn: sqlite3.Connection, order_id: str
    ) -> list[dict[str, Any]]:
        """Retrieve all inventory reservations for a given order ID."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM inventory_reservations
            WHERE order_id = ?
            ORDER BY created_at ASC;
            """,
            (order_id.strip(),),
        )
        return [dict(row) for row in cursor.fetchall()]
