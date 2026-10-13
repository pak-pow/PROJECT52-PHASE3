from app.engine.compose import compose
from app.engine.document import DocumentState
from app.engine.invert import invert
from app.engine.operation import TextOperation
from app.engine.transform import transform


def test_operation_creation_and_apply():
    """Verify building and applying an insert and retain operation."""
    op = TextOperation()
    # "Hello " is 6 chars, "world!" is 6 chars, total 12 chars
    op.retain(6).insert("beautiful ").retain(6)
    doc_text = "Hello world!"
    new_text = op.apply(doc_text)
    assert new_text == "Hello beautiful world!"


def test_operation_delete():
    """Verify deleting characters with TextOperation."""
    op = TextOperation()
    op.retain(6).delete(6)
    doc_text = "Hello world!"
    new_text = op.apply(doc_text)
    assert new_text == "Hello "


def test_operation_is_noop():
    """Verify is_noop returns True when only retaining text."""
    op = TextOperation()
    op.retain(5)
    assert op.is_noop()


def test_operation_serialization():
    """Verify to_dict and from_dict roundtrip."""
    op = TextOperation()
    op.retain(2).insert("abc").delete(1)
    data = op.to_dict()
    reconstructed = TextOperation.from_dict(data)
    assert reconstructed.base_length == op.base_length
    assert reconstructed.target_length == op.target_length
    assert len(reconstructed.components) == len(op.components)


def test_operation_adjacent_merging():
    """Verify adjacent components of identical kinds are merged."""
    op = TextOperation()
    op.retain(2).retain(3)
    assert len(op.components) == 1
    assert op.components[0].value == 5

    op2 = TextOperation()
    op2.insert("foo").insert("bar")
    assert len(op2.components) == 1
    assert op2.components[0].value == "foobar"

    op3 = TextOperation()
    op3.delete(2).delete(3)
    assert len(op3.components) == 1
    assert op3.components[0].value == 5


def test_document_state_apply():
    """Verify DocumentState applies operation and increments version."""
    state = DocumentState(doc_id="doc-1", content="cat", version=0)
    op = TextOperation()
    op.retain(3).insert("s")
    state.apply_operation(op)
    assert state.content == "cats"
    assert state.version == 1


def test_placeholders_return_stubs():
    """Verify Day 1 engine placeholders return default values."""
    op1 = TextOperation()
    op2 = TextOperation()
    assert compose(op1, op2) is None
    assert invert(op1, "") is None
    res1, res2 = transform(op1, op2)
    assert res1 == op1
    assert res2 == op2
