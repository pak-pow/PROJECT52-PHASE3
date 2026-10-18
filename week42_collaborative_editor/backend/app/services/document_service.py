"""Service layer for document management and export."""

import sqlite3
from typing import List, Optional, Tuple

from app.models.document_model import Document


class DocumentService:
    """Coordinates document queries, mutations, and export formatting."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Retrieve document by ID."""
        return Document.get_by_id(self.conn, doc_id)

    def list_documents(self) -> List[Document]:
        """List all documents."""
        return Document.list_all(self.conn)

    def create_document(
        self,
        doc_id: str,
        title: str = "Untitled Document",
        content: str = "",
        version: int = 0,
    ) -> Document:
        """Create a new document record in the database."""
        return Document.create(
            self.conn,
            doc_id=doc_id,
            title=title,
            content=content,
            version=version,
        )

    def save_document(
        self,
        doc_id: str,
        content: str,
        version: int,
        title: Optional[str] = None,
    ) -> Document:
        """Persist updated document content, version, and optional title."""
        return Document.save_or_update(
            self.conn,
            doc_id=doc_id,
            content=content,
            version=version,
            title=title,
        )

    def export_document(
        self, doc_id: str, format_type: str = "txt"
    ) -> Tuple[str, str, str]:
        """Export document content formatted for download.

        Returns a tuple of (content, mimetype, filename).
        """
        doc = self.get_document(doc_id)
        if not doc:
            raise ValueError(f"Document '{doc_id}' not found")

        fmt = format_type.lower()
        if fmt in ("md", "markdown"):
            filename = f"{doc_id}.md"
            mimetype = "text/markdown; charset=utf-8"
        else:
            filename = f"{doc_id}.txt"
            mimetype = "text/plain; charset=utf-8"

        return doc.content, mimetype, filename
