"""In-memory document state wrapper for applying transformed operations."""

from dataclasses import dataclass

from app.engine.operation import TextOperation


@dataclass
class DocumentState:
    """Document state holding content string and monotonic revision version."""

    doc_id: str
    title: str = "Untitled Document"
    content: str = ""
    version: int = 0

    def apply_operation(self, op: TextOperation) -> None:
        """Apply an operation to update the document text."""
        self.content = op.apply(self.content)
        self.version += 1
