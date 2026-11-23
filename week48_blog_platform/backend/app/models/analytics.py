"""Post view and analytics data access object for PulsePress."""

import sqlite3
from typing import Any, Dict, List


class AnalyticsDAO:
    """Data Access Object for post view tracking and metrics."""

    @staticmethod
    def record_view(conn: sqlite3.Connection, post_id: int, visitor_hash: str) -> bool:
        """Record a visitor view for a post."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO post_views (post_id, visitor_hash)
            VALUES (?, ?);
            """,
            (post_id, visitor_hash),
        )
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def get_post_views(conn: sqlite3.Connection, post_id: int) -> int:
        """Count total page views for a specific post."""
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM post_views WHERE post_id = ?;", (post_id,))
        return cursor.fetchone()[0]

    @staticmethod
    def get_post_unique_visitors(conn: sqlite3.Connection, post_id: int) -> int:
        """Count distinct visitor fingerprints for a post."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(DISTINCT visitor_hash)
            FROM post_views WHERE post_id = ?;
            """,
            (post_id,),
        )
        return cursor.fetchone()[0]

    @staticmethod
    def get_top_posts_by_views(
        conn: sqlite3.Connection, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve most viewed published posts."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.id, p.slug, p.title, COUNT(pv.id) AS view_count
            FROM posts p
            LEFT JOIN post_views pv ON p.id = pv.post_id
            WHERE p.status = 'published'
            GROUP BY p.id
            ORDER BY view_count DESC, p.published_at DESC
            LIMIT ?;
            """,
            (limit,),
        )
        return [dict(r) for r in cursor.fetchall()]
