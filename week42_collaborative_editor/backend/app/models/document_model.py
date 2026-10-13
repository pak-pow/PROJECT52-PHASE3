"""Document data access model."""

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Document:
    """Document database entity."""

    id: str
    title: str
    content: str
    version: int
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Document":
        """Construct entity from SQLite row."""
        return cls(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, doc_id: str) -> Optional["Document"]:
        """Fetch document by primary key."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        return Document.from_row(row) if row else None

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> List["Document"]:
        """List all documents ordered by update time."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents ORDER BY updated_at DESC")
        return [Document.from_row(r) for r in cursor.fetchall()]
