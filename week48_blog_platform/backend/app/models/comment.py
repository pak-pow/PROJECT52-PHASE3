"""Comment data access object for PulsePress."""

import sqlite3
from typing import Any, Dict, List, Optional


class CommentDAO:
    """Data Access Object for threaded visitor comments and moderation."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        post_id: int,
        author_name: str,
        author_email: str,
        author_ip_hash: str,
        body: str,
        parent_id: Optional[int] = None,
        status: str = "pending",
    ) -> Dict[str, Any]:
        """Create and persist a new visitor comment."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO comments (
                post_id, parent_id, author_name, author_email,
                author_ip_hash, body, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                post_id,
                parent_id,
                author_name,
                author_email,
                author_ip_hash,
                body,
                status,
            ),
        )
        conn.commit()
        comment_id = cursor.lastrowid
        return CommentDAO.get_by_id(conn, comment_id)  # type: ignore

    @staticmethod
    def get_by_id(
        conn: sqlite3.Connection, comment_id: int
    ) -> Optional[Dict[str, Any]]:
        """Retrieve comment record by numeric ID."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, post_id, parent_id, author_name, author_email,
                   author_ip_hash, body, status, created_at
            FROM comments WHERE id = ?;
            """,
            (comment_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_for_post(
        conn: sqlite3.Connection,
        post_id: int,
        status: Optional[str] = "approved",
    ) -> List[Dict[str, Any]]:
        """Retrieve comments for a post ordered chronologically."""
        cursor = conn.cursor()
        if status:
            cursor.execute(
                """
                SELECT id, post_id, parent_id, author_name, author_email,
                       body, status, created_at
                FROM comments
                WHERE post_id = ? AND status = ?
                ORDER BY created_at ASC;
                """,
                (post_id, status),
            )
        else:
            cursor.execute(
                """
                SELECT id, post_id, parent_id, author_name, author_email,
                       body, status, created_at
                FROM comments
                WHERE post_id = ?
                ORDER BY created_at ASC;
                """,
                (post_id,),
            )
        return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def get_threaded_tree(
        conn: sqlite3.Connection,
        post_id: int,
        status: Optional[str] = "approved",
    ) -> List[Dict[str, Any]]:
        """Construct a nested tree of comments and replies."""
        flat_list = CommentDAO.list_for_post(conn, post_id, status=status)
        comment_map: Dict[int, Dict[str, Any]] = {}
        roots: List[Dict[str, Any]] = []

        for item in flat_list:
            item["replies"] = []
            comment_map[item["id"]] = item

        for item in flat_list:
            parent_id = item.get("parent_id")
            if parent_id and parent_id in comment_map:
                comment_map[parent_id]["replies"].append(item)
            else:
                roots.append(item)

        return roots

    @staticmethod
    def update_status(
        conn: sqlite3.Connection, comment_id: int, status: str
    ) -> Optional[Dict[str, Any]]:
        """Update comment moderation status."""
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE comments SET status = ? WHERE id = ?;",
            (status, comment_id),
        )
        conn.commit()
        return CommentDAO.get_by_id(conn, comment_id)

    @staticmethod
    def delete(conn: sqlite3.Connection, comment_id: int) -> bool:
        """Delete comment and cascade child replies."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM comments WHERE id = ?;", (comment_id,))
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def count_recent_from_ip(
        conn: sqlite3.Connection, author_ip_hash: str, minutes: int = 10
    ) -> int:
        """Count comments submitted by an IP hash within the time window."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM comments
            WHERE author_ip_hash = ?
              AND created_at >= datetime('now', ?);
            """,
            (author_ip_hash, f"-{minutes} minutes"),
        )
        return cursor.fetchone()[0]
