"""Snapshot data access model for point-in-time document states."""

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Snapshot:
    """Snapshot database entity."""

    id: Optional[int]
    document_id: str
    revision_num: int
    content: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary."""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "revision_num": self.revision_num,
            "content": self.content,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Snapshot":
        """Construct entity from SQLite row."""
        return cls(
            id=row["id"],
            document_id=row["document_id"],
            revision_num=row["revision_num"],
            content=row["content"],
            created_at=row["created_at"],
        )

    @classmethod
    def create(
        cls,
        conn: sqlite3.Connection,
        document_id: str,
        revision_num: int,
        content: str,
    ) -> "Snapshot":
        """Insert a new snapshot record."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO snapshots (document_id, revision_num, content, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (document_id, revision_num, content),
        )
        conn.commit()
        snapshot_id = cursor.lastrowid
        cursor.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,))
        row = cursor.fetchone()
        return cls.from_row(row)

    @classmethod
    def get_latest_before_or_at(
        cls, conn: sqlite3.Connection, document_id: str, revision_num: int
    ) -> Optional["Snapshot"]:
        """Find the most recent snapshot at or prior to given revision number."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM snapshots
            WHERE document_id = ? AND revision_num <= ?
            ORDER BY revision_num DESC
            LIMIT 1
            """,
            (document_id, revision_num),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def list_for_document(
        cls, conn: sqlite3.Connection, document_id: str
    ) -> List["Snapshot"]:
        """List all snapshots for a document in ascending revision order."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM snapshots
            WHERE document_id = ?
            ORDER BY revision_num ASC
            """,
            (document_id,),
        )
        return [cls.from_row(r) for r in cursor.fetchall()]
