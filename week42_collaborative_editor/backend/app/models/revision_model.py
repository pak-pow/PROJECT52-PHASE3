"""Revision data access model."""

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Revision:
    """Revision database entity."""

    id: Optional[int]
    document_id: str
    revision_num: int
    author: str
    operation_json: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary."""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "revision_num": self.revision_num,
            "author": self.author,
            "operation_json": self.operation_json,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Revision":
        """Construct entity from SQLite row."""
        return cls(
            id=row["id"],
            document_id=row["document_id"],
            revision_num=row["revision_num"],
            author=row["author"],
            operation_json=row["operation_json"],
            created_at=row["created_at"],
        )

    @staticmethod
    def list_for_document(conn: sqlite3.Connection, doc_id: str) -> List["Revision"]:
        """List revisions for a specific document."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM revisions WHERE document_id = ? "
            "ORDER BY revision_num ASC",
            (doc_id,),
        )
        return [Revision.from_row(r) for r in cursor.fetchall()]
