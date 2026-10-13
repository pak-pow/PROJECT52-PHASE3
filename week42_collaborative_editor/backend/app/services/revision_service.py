"""Service layer for document revision and history tracking."""

import sqlite3
from typing import List

from app.models.revision_model import Revision


class RevisionService:
    """Coordinates document revision history and timeline queries."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_revisions(self, doc_id: str) -> List[Revision]:
        """Fetch all revisions for a given document."""
        return Revision.list_for_document(self.conn, doc_id)
