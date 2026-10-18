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

    @classmethod
    def create(
        cls,
        conn: sqlite3.Connection,
        doc_id: str,
        title: str = "Untitled Document",
        content: str = "",
        version: int = 0,
    ) -> "Document":
        """Create a new document record."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (id, title, content, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (doc_id, title, content, version),
        )
        conn.commit()
        return cls.get_by_id(conn, doc_id)

    @classmethod
    def save_or_update(
        cls,
        conn: sqlite3.Connection,
        doc_id: str,
        content: Optional[str] = None,
        version: Optional[int] = None,
        title: Optional[str] = None,
    ) -> "Document":
        """Update existing document fields or create if absent."""
        existing = cls.get_by_id(conn, doc_id)
        if not existing:
            return cls.create(
                conn,
                doc_id=doc_id,
                title=title or "Untitled Document",
                content=content or "",
                version=version or 0,
            )

        new_title = title if title is not None else existing.title
        new_content = content if content is not None else existing.content
        new_version = version if version is not None else existing.version

        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE documents
            SET title = ?, content = ?, version = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_title, new_content, new_version, doc_id),
        )
        conn.commit()
        return cls.get_by_id(conn, doc_id)

    @classmethod
    def delete(cls, conn: sqlite3.Connection, doc_id: str) -> bool:
        """Delete a document record by ID."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        return cursor.rowcount > 0
