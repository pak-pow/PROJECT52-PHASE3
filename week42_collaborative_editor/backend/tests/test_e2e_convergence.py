"""End-to-end multi-client convergence baseline test."""

from app.engine.document import DocumentState
from app.engine.operation import TextOperation


def test_baseline_convergence_stub():
    """Verify document convergence baseline."""
    doc = DocumentState(doc_id="doc-e2e", content="Hello", version=0)
    op = TextOperation()
    op.retain(5).insert(" World")
    doc.apply_operation(op)
    assert doc.content == "Hello World"
