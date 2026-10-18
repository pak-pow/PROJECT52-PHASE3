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

    @classmethod
    def create(
        cls,
        conn: sqlite3.Connection,
        document_id: str,
        revision_num: int,
        author: str,
        operation_json: str,
    ) -> "Revision":
        """Insert a new revision record."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO revisions
            (document_id, revision_num, author, operation_json, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (document_id, revision_num, author, operation_json),
        )
        conn.commit()
        rev_id = cursor.lastrowid
        cursor.execute("SELECT * FROM revisions WHERE id = ?", (rev_id,))
        row = cursor.fetchone()
        return cls.from_row(row)

    @classmethod
    def get_by_revision(
        cls, conn: sqlite3.Connection, document_id: str, revision_num: int
    ) -> Optional["Revision"]:
        """Fetch a specific revision by document ID and revision number."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM revisions
            WHERE document_id = ? AND revision_num = ?
            """,
            (document_id, revision_num),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def list_range(
        cls,
        conn: sqlite3.Connection,
        document_id: str,
        start_rev: int,
        end_rev: int,
    ) -> List["Revision"]:
        """List revisions within an inclusive revision number range."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM revisions
            WHERE document_id = ? AND revision_num >= ? AND revision_num <= ?
            ORDER BY revision_num ASC
            """,
            (document_id, start_rev, end_rev),
        )
        return [cls.from_row(r) for r in cursor.fetchall()]

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
