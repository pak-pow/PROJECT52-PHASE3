"""Service layer for document revision and history tracking."""

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

from app.engine.operation import TextOperation, create_operation_from_diff
from app.models.document_model import Document
from app.models.revision_model import Revision
from app.models.snapshot_model import Snapshot


class RevisionService:
    """Coordinates document revision history, snapshots, and rollback."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record_revision(
        self,
        doc_id: str,
        revision_num: int,
        author: str,
        operation: Union[TextOperation, Dict[str, Any], str],
        current_content: Optional[str] = None,
    ) -> Revision:
        """Persist a new revision and periodically capture a point-in-time snapshot."""
        if isinstance(operation, TextOperation):
            op_json = json.dumps(operation.to_dict())
        elif isinstance(operation, dict):
            op_json = json.dumps(operation)
        else:
            op_json = str(operation)

        rev = Revision.create(
            self.conn,
            document_id=doc_id,
            revision_num=revision_num,
            author=author,
            operation_json=op_json,
        )

        # Automatically capture snapshot every 10 revisions or at revision 1
        if current_content is not None and (
            revision_num % 10 == 0 or revision_num == 1
        ):
            self.create_snapshot(doc_id, revision_num, current_content)

        return rev

    def get_revisions(self, doc_id: str) -> List[Revision]:
        """Fetch all revisions for a given document."""
        return Revision.list_for_document(self.conn, doc_id)

    def get_revision(self, doc_id: str, revision_num: int) -> Optional[Revision]:
        """Fetch single revision by document ID and revision number."""
        return Revision.get_by_revision(self.conn, doc_id, revision_num)

    def create_snapshot(self, doc_id: str, revision_num: int, content: str) -> Snapshot:
        """Create and store a point-in-time snapshot of the document."""
        return Snapshot.create(self.conn, doc_id, revision_num, content)

    def get_snapshots(self, doc_id: str) -> List[Snapshot]:
        """List all snapshots recorded for a document."""
        return Snapshot.list_for_document(self.conn, doc_id)

    def get_content_at_revision(self, doc_id: str, target_revision: int) -> str:
        """Reconstruct document text at a specific point-in-time revision.

        Finds the nearest preceding snapshot and sequentially replays
        revisions up to target_revision.
        """
        if target_revision < 0:
            raise ValueError("Target revision cannot be negative")

        if target_revision == 0:
            snap0 = Snapshot.get_latest_before_or_at(self.conn, doc_id, 0)
            if snap0 and snap0.revision_num == 0:
                return snap0.content
            doc = Document.get_by_id(self.conn, doc_id)
            if doc and doc.version == 0:
                return doc.content
            return ""

        snapshot = Snapshot.get_latest_before_or_at(self.conn, doc_id, target_revision)
        if snapshot:
            text = snapshot.content
            start_rev = snapshot.revision_num + 1
        else:
            text = ""
            start_rev = 1

        revisions = Revision.list_range(self.conn, doc_id, start_rev, target_revision)
        for r in revisions:
            op_dict = json.loads(r.operation_json)
            op = TextOperation.from_dict(op_dict)
            text = op.apply(text)

        return text

    def rollback_document(
        self,
        doc_id: str,
        target_revision: int,
        author: str = "System Rollback",
    ) -> Tuple[str, int, Revision]:
        """Rollback document to target_revision by recording an append-only revision.

        Returns (new_content, new_version, revision_record).
        """
        doc = Document.get_by_id(self.conn, doc_id)
        if not doc:
            raise ValueError(f"Document '{doc_id}' not found")

        if target_revision < 0 or target_revision > doc.version:
            raise ValueError(
                f"Invalid target revision {target_revision} "
                f"(current version: {doc.version})"
            )

        target_content = self.get_content_at_revision(doc_id, target_revision)
        rollback_op = create_operation_from_diff(doc.content, target_content)
        new_version = doc.version + 1

        rev = self.record_revision(
            doc_id=doc_id,
            revision_num=new_version,
            author=author,
            operation=rollback_op,
            current_content=target_content,
        )

        Document.save_or_update(
            self.conn,
            doc_id=doc_id,
            content=target_content,
            version=new_version,
        )

        return target_content, new_version, rev
