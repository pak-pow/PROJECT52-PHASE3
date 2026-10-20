"""Data access model for background transcoding jobs."""

import sqlite3
import uuid
from typing import Any, Dict, List, Optional


class TranscodingJobModel:
    """Operations for transcoding queue jobs in SQLite."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        video_id: str,
        job_id: Optional[str] = None,
        status: str = "queued",
    ) -> Dict[str, Any]:
        """Create a new transcoding job entry."""
        jid = job_id or str(uuid.uuid4())
        query = """
            INSERT INTO transcoding_jobs (
                id, video_id, status, progress, current_stage
            ) VALUES (?, ?, ?, 0, 'queued')
        """
        cursor = conn.cursor()
        cursor.execute(query, (jid, video_id, status))
        conn.commit()
        job = TranscodingJobModel.get_by_id(conn, jid)
        if job is None:
            raise RuntimeError("Failed to retrieve created transcoding job.")
        return job

    @staticmethod
    def get_by_id(
        conn: sqlite3.Connection,
        job_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a transcoding job by ID with video details."""
        query = """
            SELECT j.*, v.title AS video_title, v.filename AS video_filename
            FROM transcoding_jobs j
            JOIN videos v ON j.video_id = v.id
            WHERE j.id = ?
        """
        cursor = conn.cursor()
        cursor.execute(query, (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_video_id(
        conn: sqlite3.Connection,
        video_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent transcoding job for a video."""
        query = """
            SELECT * FROM transcoding_jobs
            WHERE video_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """
        cursor = conn.cursor()
        cursor.execute(query, (video_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def update_progress(
        conn: sqlite3.Connection,
        job_id: str,
        progress: int,
        current_stage: Optional[str] = None,
    ) -> bool:
        """Update progress percentage and stage."""
        updates = [
            "progress = ?",
            "updated_at = CURRENT_TIMESTAMP",
            "status = 'processing'",
        ]
        params: List[Any] = [min(100, max(0, progress))]

        if current_stage:
            updates.append("current_stage = ?")
            params.append(current_stage)

        params.append(job_id)
        query = (
            f"UPDATE transcoding_jobs SET {', '.join(updates)} "  # nosec B608
            "WHERE id = ? AND status != 'completed' AND status != 'failed'"
        )
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def mark_completed(conn: sqlite3.Connection, job_id: str) -> bool:
        """Mark job as successfully completed with 100% progress."""
        query = """
            UPDATE transcoding_jobs
            SET status = 'completed',
                progress = 100,
                current_stage = 'finished',
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        cursor = conn.cursor()
        cursor.execute(query, (job_id,))
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def mark_failed(
        conn: sqlite3.Connection,
        job_id: str,
        error_message: str,
    ) -> bool:
        """Mark job as failed with captured error message."""
        query = """
            UPDATE transcoding_jobs
            SET status = 'failed',
                error_message = ?,
                current_stage = 'error',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        cursor = conn.cursor()
        cursor.execute(query, (error_message, job_id))
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def list_by_status(
        conn: sqlite3.Connection,
        status: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List transcoding jobs matching status."""
        query = """
            SELECT * FROM transcoding_jobs
            WHERE status = ?
            ORDER BY created_at ASC
            LIMIT ?
        """
        cursor = conn.cursor()
        cursor.execute(query, (status, limit))
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def list_all(
        conn: sqlite3.Connection,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List all transcoding jobs ordered by creation descending."""
        query = """
            SELECT j.*, v.title AS video_title
            FROM transcoding_jobs j
            JOIN videos v ON j.video_id = v.id
            ORDER BY j.created_at DESC
            LIMIT ?
        """
        cursor = conn.cursor()
        cursor.execute(query, (limit,))
        return [dict(row) for row in cursor.fetchall()]
