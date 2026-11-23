"""Post data access object for PulsePress."""

import datetime
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.models.tag import TagDAO
from app.services.slug_service import generate_unique_slug_for_db


class PostDAO:
    """Data Access Object for blog posts and publications."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        author_id: int,
        title: str,
        body_markdown: str,
        slug: Optional[str] = None,
        body_html: str = "",
        excerpt: str = "",
        featured_image: str = "",
        status: str = "draft",
        reading_time_minutes: int = 1,
        toc_json: str = "[]",
        published_at: Optional[str] = None,
        tag_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        """Create and persist a new blog post."""
        post_slug = slug or generate_unique_slug_for_db(conn, title)
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        pub_date = published_at if published_at or status != "published" else now

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO posts (
                author_id, slug, title, body_markdown, body_html, excerpt,
                featured_image, status, reading_time_minutes, toc_json,
                published_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                author_id,
                post_slug,
                title,
                body_markdown,
                body_html,
                excerpt,
                featured_image,
                status,
                reading_time_minutes,
                toc_json,
                pub_date,
                now,
                now,
            ),
        )
        post_id = cursor.lastrowid
        conn.commit()

        if tag_ids:
            TagDAO.set_tags_for_post(conn, post_id, tag_ids)

        return PostDAO.get_by_id(conn, post_id)  # type: ignore

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, post_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve post record with author metadata and attached tags."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.id, p.author_id, p.slug, p.title, p.body_markdown,
                   p.body_html, p.excerpt, p.featured_image, p.status,
                   p.reading_time_minutes, p.toc_json, p.published_at,
                   p.created_at, p.updated_at,
                   u.username AS author_username,
                   u.display_name AS author_display_name,
                   u.avatar_url AS author_avatar_url
            FROM posts p
            JOIN users u ON p.author_id = u.id
            WHERE p.id = ?;
            """,
            (post_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        post = dict(row)
        post["tags"] = TagDAO.get_tags_for_post(conn, post_id)
        return post

    @staticmethod
    def get_by_slug(conn: sqlite3.Connection, slug: str) -> Optional[Dict[str, Any]]:
        """Retrieve post record by unique slug."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.id, p.author_id, p.slug, p.title, p.body_markdown,
                   p.body_html, p.excerpt, p.featured_image, p.status,
                   p.reading_time_minutes, p.toc_json, p.published_at,
                   p.created_at, p.updated_at,
                   u.username AS author_username,
                   u.display_name AS author_display_name,
                   u.avatar_url AS author_avatar_url
            FROM posts p
            JOIN users u ON p.author_id = u.id
            WHERE p.slug = ?;
            """,
            (slug,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        post = dict(row)
        post["tags"] = TagDAO.get_tags_for_post(conn, post["id"])
        return post

    @staticmethod
    def update(
        conn: sqlite3.Connection, post_id: int, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        """Update mutable fields on post record."""
        allowed = {
            "title",
            "slug",
            "body_markdown",
            "body_html",
            "excerpt",
            "featured_image",
            "status",
            "reading_time_minutes",
            "toc_json",
            "published_at",
        }
        tag_ids = kwargs.pop("tag_ids", None)
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        updates["updated_at"] = now

        if updates.get("status") == "published" and "published_at" not in updates:
            # Set published_at if publishing for first time
            existing = PostDAO.get_by_id(conn, post_id)
            if existing and not existing.get("published_at"):
                updates["published_at"] = now

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        params = list(updates.values()) + [post_id]

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE posts SET {set_clause} WHERE id = ?;",  # nosec B608
            params,
        )
        conn.commit()

        if tag_ids is not None:
            TagDAO.set_tags_for_post(conn, post_id, tag_ids)

        return PostDAO.get_by_id(conn, post_id)

    @staticmethod
    def delete(conn: sqlite3.Connection, post_id: int) -> bool:
        """Delete post and cascade associations."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM posts WHERE id = ?;", (post_id,))
        conn.commit()
        TagDAO.recalculate_post_counts(conn)
        return cursor.rowcount > 0

    @staticmethod
    def publish(conn: sqlite3.Connection, post_id: int) -> Optional[Dict[str, Any]]:
        """Transition post to published state."""
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return PostDAO.update(conn, post_id, status="published", published_at=now)

    @staticmethod
    def list_posts(
        conn: sqlite3.Connection,
        status: Optional[str] = "published",
        tag_id: Optional[int] = None,
        tag_slug: Optional[str] = None,
        author_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 10,
        order_by: str = "published_at_desc",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List paginated posts with optional filters and total count."""
        where_clauses: List[str] = []
        params: List[Any] = []

        if status:
            where_clauses.append("p.status = ?")
            params.append(status)

        if author_id:
            where_clauses.append("p.author_id = ?")
            params.append(author_id)

        if tag_id:
            where_clauses.append(
                "EXISTS ("
                "SELECT 1 FROM post_tags pt "
                "WHERE pt.post_id = p.id AND pt.tag_id = ?)"
            )
            params.append(tag_id)
        elif tag_slug:
            where_clauses.append("""
                EXISTS (
                    SELECT 1 FROM post_tags pt
                    JOIN tags t ON pt.tag_id = t.id
                    WHERE pt.post_id = p.id AND t.slug = ?
                )
                """)
            params.append(tag_slug)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Ordering
        if order_by == "created_at_desc":
            order_sql = "p.created_at DESC"
        elif order_by == "views_desc":
            order_sql = "view_count DESC, p.published_at DESC"
        else:
            order_sql = "COALESCE(p.published_at, p.created_at) DESC"

        # Count total
        cursor = conn.cursor()
        count_query = f"SELECT COUNT(*) FROM posts p {where_sql};"  # nosec B608
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        # Fetch page items
        limit = max(1, page_size)
        offset = max(0, (page - 1) * limit)

        select_query = f"""
            SELECT p.id, p.author_id, p.slug, p.title, p.excerpt,
                   p.featured_image, p.status, p.reading_time_minutes,
                   p.published_at, p.created_at, p.updated_at,
                   u.username AS author_username,
                   u.display_name AS author_display_name,
                   u.avatar_url AS author_avatar_url,
                   (SELECT COUNT(*) FROM post_views pv
                    WHERE pv.post_id = p.id) AS view_count,
                   (SELECT COUNT(*) FROM comments c
                    WHERE c.post_id = p.id AND c.status = 'approved') AS comment_count
            FROM posts p
            JOIN users u ON p.author_id = u.id
            {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?;
        """  # nosec B608

        cursor.execute(select_query, params + [limit, offset])
        rows = cursor.fetchall()

        posts = []
        for r in rows:
            p_dict = dict(r)
            p_dict["tags"] = TagDAO.get_tags_for_post(conn, p_dict["id"])
            posts.append(p_dict)

        return posts, total_count
