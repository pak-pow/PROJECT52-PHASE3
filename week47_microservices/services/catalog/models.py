"""Isolated SQLite database models for Catalog & Inventory Service."""

import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> str:
    """Current UTC timestamp as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class CatalogModel:
    """Database persistence manager for products and inventory."""

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
        """Initialize relational schema for products and inventory reservations."""
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    sku TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    price_cents INTEGER NOT NULL,
                    stock_quantity INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory_reservations (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (product_id) REFERENCES products(id)
                );
                """)

    @classmethod
    def create_product(
        cls,
        conn: sqlite3.Connection,
        sku: str,
        name: str,
        price_cents: int,
        stock_quantity: int,
        description: str = "",
    ) -> dict[str, Any]:
        """Register a new product SKU in the catalog."""
        clean_sku = sku.strip().upper()
        clean_name = name.strip()

        if not clean_sku:
            raise ValueError("SKU cannot be empty")
        if not clean_name:
            raise ValueError("Product name cannot be empty")
        if not isinstance(price_cents, int) or price_cents < 0:
            raise ValueError("Price in cents must be a non-negative integer")
        if not isinstance(stock_quantity, int) or stock_quantity < 0:
            raise ValueError("Stock quantity must be a non-negative integer")

        product_id = f"prod_{secrets.token_hex(8)}"
        now = utc_now()

        with conn:
            try:
                conn.execute(
                    """
                    INSERT INTO products (
                        id, sku, name, description,
                        price_cents, stock_quantity,
                        is_active, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?);
                    """,
                    (
                        product_id,
                        clean_sku,
                        clean_name,
                        description.strip(),
                        price_cents,
                        stock_quantity,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"Product with SKU '{clean_sku}' already exists")

        prod = cls.get_by_id(conn, product_id)
        assert prod is not None
        return prod

    @classmethod
    def get_by_id(
        cls, conn: sqlite3.Connection, product_id: str
    ) -> Optional[dict[str, Any]]:
        """Retrieve product details with real-time available stock."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?;", (product_id,))
        row = cursor.fetchone()
        if not row:
            return None

        product = dict(row)
        # Compute active reserved stock
        cursor.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) AS reserved_qty
            FROM inventory_reservations
            WHERE product_id = ? AND status = 'RESERVED';
            """,
            (product_id,),
        )
        reserved_qty = cursor.fetchone()["reserved_qty"]
        product["reserved_stock"] = reserved_qty
        product["available_stock"] = max(0, product["stock_quantity"] - reserved_qty)
        return product

    @classmethod
    def get_by_sku(cls, conn: sqlite3.Connection, sku: str) -> Optional[dict[str, Any]]:
        """Retrieve product by its unique SKU."""
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM products WHERE sku = ?;", (sku.strip().upper(),))
        row = cursor.fetchone()
        if not row:
            return None
        return cls.get_by_id(conn, row["id"])

    @classmethod
    def list_products(
        cls, conn: sqlite3.Connection, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List products with live available stock counts."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM products
            WHERE is_active = 1
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?;
            """,
            (limit, offset),
        )
        product_ids = [row["id"] for row in cursor.fetchall()]
        products = []
        for pid in product_ids:
            item = cls.get_by_id(conn, pid)
            if item:
                products.append(item)
        return products
