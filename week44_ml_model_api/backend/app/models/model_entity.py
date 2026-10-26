"""Data access object for registered machine learning models."""

import sqlite3
from typing import Any, Dict, List, Optional


class ModelDAO:
    """Operations for the 'models' table in SQLite."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        model_id: str,
        name: str,
        domain: str,
        description: Optional[str] = None,
        active_version: str = "v1",
    ) -> Dict[str, Any]:
        """Insert a new model record."""
        clean_id = model_id.strip().lower()
        query = """
            INSERT INTO models (id, name, domain, description, active_version)
            VALUES (?, ?, ?, ?, ?)
        """
        cursor = conn.cursor()
        cursor.execute(
            query,
            (
                clean_id,
                name.strip(),
                domain.strip().lower(),
                description,
                active_version,
            ),
        )
        conn.commit()
        record = ModelDAO.get_by_id(conn, clean_id)
        if record is None:
            raise RuntimeError(f"Failed to retrieve created model: {clean_id}")
        return record

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, model_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a model by its unique identifier."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM models WHERE id = ?", (model_id.strip().lower(),))
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_all(
        conn: sqlite3.Connection, domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all registered models, optionally filtered by domain."""
        cursor = conn.cursor()
        if domain:
            cursor.execute(
                "SELECT * FROM models WHERE domain = ? ORDER BY id ASC",
                (domain.strip().lower(),),
            )
        else:
            cursor.execute("SELECT * FROM models ORDER BY id ASC")
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def update_active_version(
        conn: sqlite3.Connection, model_id: str, new_version: str
    ) -> bool:
        """Update active version pointer for a model."""
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE models
            SET active_version = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_version.strip(), model_id.strip().lower()),
        )
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def delete(conn: sqlite3.Connection, model_id: str) -> bool:
        """Delete a model and cascaded versions/logs."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM models WHERE id = ?", (model_id.strip().lower(),))
        conn.commit()
        return cursor.rowcount > 0
