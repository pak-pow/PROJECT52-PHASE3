"""Data access model for video categories."""

import sqlite3
from typing import Any, Dict, List, Optional


class CategoryModel:
    """Operations for video categories in the SQLite database."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        name: str,
        slug: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new category and return its representation."""
        query = """
            INSERT INTO categories (name, slug, description)
            VALUES (?, ?, ?)
        """
        cursor = conn.cursor()
        cursor.execute(query, (name.strip(), slug.strip().lower(), description))
        conn.commit()
        cat_id = cursor.lastrowid
        created = CategoryModel.get_by_id(conn, cat_id)
        if created is None:
            raise RuntimeError("Failed to retrieve created category.")
        return created

    @staticmethod
    def get_by_id(
        conn: sqlite3.Connection,
        category_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve category by primary key ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_slug(
        conn: sqlite3.Connection,
        slug: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve category by unique slug."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM categories WHERE slug = ?", (slug.strip().lower(),)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """List all categories ordered alphabetically by name."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def delete(conn: sqlite3.Connection, category_id: int) -> bool:
        """Delete category by ID."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        conn.commit()
        return cursor.rowcount > 0
