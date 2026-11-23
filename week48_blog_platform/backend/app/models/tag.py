"""Tag taxonomy data access object for PulsePress."""

import sqlite3
from typing import Any, Dict, List, Optional, Sequence

from app.services.slug_service import generate_slug


class TagDAO:
    """Data Access Object for article taxonomy tags."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        name: str,
        slug: Optional[str] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        """Create a new tag record."""
        tag_slug = slug or generate_slug(name)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tags (name, slug, description, post_count)
            VALUES (?, ?, ?, 0);
            """,
            (name, tag_slug, description),
        )
        conn.commit()
        tag_id = cursor.lastrowid
        return TagDAO.get_by_id(conn, tag_id)  # type: ignore

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, tag_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve tag record by numeric ID."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, slug, description, post_count, created_at
            FROM tags WHERE id = ?;
            """,
            (tag_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_slug(conn: sqlite3.Connection, slug: str) -> Optional[Dict[str, Any]]:
        """Retrieve tag record by slug."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, slug, description, post_count, created_at
            FROM tags WHERE slug = ?;
            """,
            (slug,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_all(
        conn: sqlite3.Connection, order_by: str = "name"
    ) -> List[Dict[str, Any]]:
        """List all tags sorted by name or post count."""
        sort_col = "post_count DESC, name ASC" if order_by == "count" else "name ASC"
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT id, name, slug, description, post_count, created_at
            FROM tags ORDER BY {sort_col};
            """)  # nosec B608
        return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def update(
        conn: sqlite3.Connection, tag_id: int, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        """Update tag fields."""
        allowed_keys = {"name", "slug", "description"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_keys}
        if not updates:
            return TagDAO.get_by_id(conn, tag_id)

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        params = list(updates.values()) + [tag_id]

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE tags SET {set_clause} WHERE id = ?;",  # nosec B608
            params,
        )
        conn.commit()
        return TagDAO.get_by_id(conn, tag_id)

    @staticmethod
    def delete(conn: sqlite3.Connection, tag_id: int) -> bool:
        """Delete tag and cascade associations."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tags WHERE id = ?;", (tag_id,))
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def recalculate_post_counts(conn: sqlite3.Connection) -> None:
        """Recalculate post counts for all tags based on published posts."""
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tags SET post_count = (
                SELECT COUNT(*)
                FROM post_tags pt
                JOIN posts p ON pt.post_id = p.id
                WHERE pt.tag_id = tags.id AND p.status = 'published'
            );
            """)
        conn.commit()

    @staticmethod
    def get_tags_for_post(
        conn: sqlite3.Connection, post_id: int
    ) -> List[Dict[str, Any]]:
        """Retrieve all tags associated with a specific post."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.id, t.name, t.slug, t.description, t.post_count
            FROM tags t
            JOIN post_tags pt ON pt.tag_id = t.id
            WHERE pt.post_id = ?
            ORDER BY t.name ASC;
            """,
            (post_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def set_tags_for_post(
        conn: sqlite3.Connection, post_id: int, tag_ids: Sequence[int]
    ) -> None:
        """Synchronize the tags attached to a post."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM post_tags WHERE post_id = ?;", (post_id,))
        for tid in set(tag_ids):
            cursor.execute(
                """
                INSERT OR IGNORE INTO post_tags (post_id, tag_id)
                VALUES (?, ?);
                """,
                (post_id, tid),
            )
        conn.commit()
        TagDAO.recalculate_post_counts(conn)
