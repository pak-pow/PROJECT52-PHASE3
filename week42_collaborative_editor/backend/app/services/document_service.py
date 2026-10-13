"""Service layer for document management."""

import sqlite3
from typing import List, Optional

from app.models.document_model import Document


class DocumentService:
    """Coordinates document queries and mutations."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Retrieve document by ID."""
        return Document.get_by_id(self.conn, doc_id)

    def list_documents(self) -> List[Document]:
        """List all documents."""
        return Document.list_all(self.conn)
