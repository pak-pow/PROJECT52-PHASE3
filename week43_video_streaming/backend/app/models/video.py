"""Data access model for videos and ABR renditions."""

import sqlite3
import uuid
from typing import Any, Dict, List, Optional


class VideoModel:
    """Operations for videos and ABR renditions in the SQLite database."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        title: str,
        filename: str,
        description: Optional[str] = None,
        category_id: Optional[int] = None,
        duration: float = 0.0,
        size_bytes: int = 0,
        mime_type: str = "video/mp4",
        video_id: Optional[str] = None,
        status: str = "pending",
        poster_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new video record."""
        vid = video_id or str(uuid.uuid4())
        query = """
            INSERT INTO videos (
                id, title, description, category_id, filename,
                duration, size_bytes, mime_type, status, poster_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = conn.cursor()
        cursor.execute(
            query,
            (
                vid,
                title.strip(),
                description,
                category_id,
                filename,
                duration,
                size_bytes,
                mime_type,
                status,
                poster_path,
            ),
        )
        conn.commit()
        record = VideoModel.get_by_id(conn, vid)
        if record is None:
            raise RuntimeError("Failed to retrieve created video record.")
        return record

    @staticmethod
    def get_by_id(
        conn: sqlite3.Connection,
        video_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a video by its unique identifier with optional category info."""
        query = """
            SELECT v.*, c.name AS category_name, c.slug AS category_slug
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            WHERE v.id = ?
        """
        cursor = conn.cursor()
        cursor.execute(query, (video_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_all(
        conn: sqlite3.Connection,
        category_id: Optional[int] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List videos with optional filters for category, status, and search."""
        query = """
            SELECT v.*, c.name AS category_name, c.slug AS category_slug
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            WHERE 1=1
        """
        params: List[Any] = []

        if category_id is not None:
            query += " AND v.category_id = ?"
            params.append(category_id)

        if status is not None:
            query += " AND v.status = ?"
            params.append(status)

        if search:
            query += " AND (v.title LIKE ? OR v.description LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term])

        query += " ORDER BY v.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def update_status(
        conn: sqlite3.Connection,
        video_id: str,
        status: str,
        duration: Optional[float] = None,
        poster_path: Optional[str] = None,
    ) -> bool:
        """Update video lifecycle status and optionally duration or poster."""
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: List[Any] = [status]

        if duration is not None:
            updates.append("duration = ?")
            params.append(duration)

        if poster_path is not None:
            updates.append("poster_path = ?")
            params.append(poster_path)

        params.append(video_id)
        query = f"UPDATE videos SET {', '.join(updates)} WHERE id = ?"  # nosec B608
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def increment_views(conn: sqlite3.Connection, video_id: str) -> int:
        """Increment video view count atomically and return updated count."""
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE videos
            SET views_count = views_count + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (video_id,),
        )
        conn.commit()

        cursor.execute("SELECT views_count FROM videos WHERE id = ?", (video_id,))
        row = cursor.fetchone()
        return row["views_count"] if row else 0

    @staticmethod
    def delete(conn: sqlite3.Connection, video_id: str) -> bool:
        """Delete a video record by ID."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def add_rendition(
        conn: sqlite3.Connection,
        video_id: str,
        resolution: str,
        width: int,
        height: int,
        bitrate_kbps: int,
        playlist_path: str,
        segment_count: int = 0,
        rendition_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add an ABR rendition profile to a video."""
        rid = rendition_id or str(uuid.uuid4())
        query = """
            INSERT INTO video_renditions (
                id, video_id, resolution, width, height,
                bitrate_kbps, playlist_path, segment_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = conn.cursor()
        cursor.execute(
            query,
            (
                rid,
                video_id,
                resolution,
                width,
                height,
                bitrate_kbps,
                playlist_path,
                segment_count,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM video_renditions WHERE id = ?", (rid,))
        row = cursor.fetchone()
        return dict(row)

    @staticmethod
    def get_renditions(
        conn: sqlite3.Connection,
        video_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve all renditions for a video ordered by height descending."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM video_renditions
            WHERE video_id = ?
            ORDER BY height DESC
            """,
            (video_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
