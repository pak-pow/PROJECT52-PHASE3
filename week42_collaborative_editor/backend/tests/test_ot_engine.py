"""Unit tests for the Operational Transformation (OT) core engine."""

import pytest

from app.engine.compose import compose
from app.engine.document import DocumentState
from app.engine.invert import invert
from app.engine.operation import OpComponent, OpKind, TextOperation
from app.engine.transform import transform

# ---------------------------------------------------------------------------
# 1. Atomic Operations and TextOperation Tests
# ---------------------------------------------------------------------------


def test_operation_construction_and_apply():
    """Verify building and applying insert, retain, and delete operations."""
    doc = "Hello world!"
    op = TextOperation()
    # Hello (6), insert "brave ", world! (6)
    op.retain(6).insert("brave ").retain(6)
    assert op.apply(doc) == "Hello brave world!"


def test_operation_delete_and_apply():
    """Verify deleting characters from a document."""
    doc = "Hello brave world!"
    op = TextOperation()
    op.retain(6).delete(6).retain(6)
    assert op.apply(doc) == "Hello world!"


def test_operation_noop_and_copy():
    """Verify is_noop and copy functionality."""
    op = TextOperation()
    op.retain(10)
    assert op.is_noop()

    copied = op.copy()
    assert copied == op
    assert copied is not op

    op_edit = TextOperation()
    op_edit.insert("a")
    assert not op_edit.is_noop()
    assert op_edit != op
    assert op_edit != "not-an-op"


def test_operation_component_merging():
    """Verify consecutive components of the same kind are coalesced."""
    op = TextOperation()
    op.retain(3).retain(4)
    assert len(op.components) == 1
    assert op.components[0].value == 7

    op.insert("foo").insert("bar")
    assert len(op.components) == 2
    assert op.components[1].value == "foobar"

    op.delete(2).delete(5)
    assert len(op.components) == 3
    assert op.components[2].value == 7


def test_operation_serialization():
    """Verify to_dict and from_dict roundtrip."""
    op = TextOperation()
    op.retain(5).insert("xyz").delete(2)
    data = op.to_dict()
    reconstructed = TextOperation.from_dict(data)
    assert reconstructed == op


def test_operation_validation_errors():
    """Verify errors when applying operations with invalid string lengths."""
    op = TextOperation()
    op.retain(5)

    with pytest.raises(ValueError, match="does not match document text length"):
        op.apply("Too long string")

    # Construct invalid op with corrupted target_length
    bad_op = TextOperation(
        components=[OpComponent(OpKind.RETAIN, 3)],
        base_length=3,
        target_length=5,
    )
    with pytest.raises(ValueError, match="does not match operation target_length"):
        bad_op.apply("abc")


# ---------------------------------------------------------------------------
# 2. Transform Tests (Commutative Convergence Guarantee)
# ---------------------------------------------------------------------------


def test_transform_non_overlapping_inserts():
    """Verify convergence for two concurrent inserts at different offsets."""
    initial = "cat"
    # Client 1: insert "black " at start -> "black cat"
    op1 = TextOperation().insert("black ").retain(3)
    # Client 2: insert "s" at end -> "cats"
    op2 = TextOperation().retain(3).insert("s")

    op1_prime, op2_prime = transform(op1, op2)

    res1 = op2_prime.apply(op1.apply(initial))
    res2 = op1_prime.apply(op2.apply(initial))
    assert res1 == "black cats"
    assert res2 == "black cats"
    assert res1 == res2


def test_transform_concurrent_inserts_same_position():
    """Verify tie-breaking with priority for concurrent inserts at same offset."""
    initial = "code"
    # Both insert at offset 0
    op1 = TextOperation().insert("quick ").retain(4)
    op2 = TextOperation().insert("clean ").retain(4)

    # Priority True: op1 comes first
    op1_p, op2_p = transform(op1, op2, priority=True)
    res_a1 = op2_p.apply(op1.apply(initial))
    res_a2 = op1_p.apply(op2.apply(initial))
    assert res_a1 == "quick clean code"
    assert res_a2 == "quick clean code"

    # Priority False: op2 comes first
    op1_p_rev, op2_p_rev = transform(op1, op2, priority=False)
    res_b1 = op2_p_rev.apply(op1.apply(initial))
    res_b2 = op1_p_rev.apply(op2.apply(initial))
    assert res_b1 == "clean quick code"
    assert res_b2 == "clean quick code"


def test_transform_insert_vs_delete():
    """Verify transformation between concurrent insert and delete."""
    initial = "hello world"
    # Client 1: deletes "world" -> "hello "
    op1 = TextOperation().retain(6).delete(5)
    # Client 2: inserts "wonderful " before world -> "hello wonderful world"
    op2 = TextOperation().retain(6).insert("wonderful ").retain(5)

    op1_prime, op2_prime = transform(op1, op2)

    res1 = op2_prime.apply(op1.apply(initial))
    res2 = op1_prime.apply(op2.apply(initial))
    assert res1 == "hello wonderful "
    assert res2 == "hello wonderful "


def test_transform_overlapping_deletes():
    """Verify convergence when two clients delete overlapping text spans."""
    initial = "abcdef"
    # Client 1 deletes first 4 characters "abcd" -> "ef"
    op1 = TextOperation().delete(4).retain(2)
    # Client 2 deletes last 4 characters "cdef" -> "ab"
    op2 = TextOperation().retain(2).delete(4)

    op1_prime, op2_prime = transform(op1, op2)

    res1 = op2_prime.apply(op1.apply(initial))
    res2 = op1_prime.apply(op2.apply(initial))
    assert res1 == ""
    assert res2 == ""


def test_transform_identical_deletes():
    """Verify convergence when both clients delete the exact same text span."""
    initial = "collaborative"
    op1 = TextOperation().delete(13)
    op2 = TextOperation().delete(13)

    op1_prime, op2_prime = transform(op1, op2)
    res1 = op2_prime.apply(op1.apply(initial))
    res2 = op1_prime.apply(op2.apply(initial))
    assert res1 == ""
    assert res2 == ""


def test_transform_mismatched_base_length_error():
    """Verify transform raises error on mismatched base lengths."""
    op1 = TextOperation().retain(5)
    op2 = TextOperation().retain(10)
    with pytest.raises(ValueError, match="mismatched base_length"):
        transform(op1, op2)


# ---------------------------------------------------------------------------
# 3. Compose Tests (Sequential Edits Coalescence)
# ---------------------------------------------------------------------------


def test_compose_consecutive_inserts():
    """Verify composing consecutive character inserts."""
    initial = "Hello"
    op1 = TextOperation().retain(5).insert(" brave")
    op2 = TextOperation().retain(11).insert(" world")

    composed = compose(op1, op2)
    res_sequential = op2.apply(op1.apply(initial))
    res_composed = composed.apply(initial)

    assert res_composed == "Hello brave world"
    assert res_composed == res_sequential


def test_compose_insert_then_delete():
    """Verify composing insert followed by delete cancels out."""
    initial = "Hello"
    # Insert " world" -> "Hello world"
    op1 = TextOperation().retain(5).insert(" world")
    # Delete " world" -> "Hello"
    op2 = TextOperation().retain(5).delete(6)

    composed = compose(op1, op2)
    assert composed.apply(initial) == "Hello"


def test_compose_replace_text():
    """Verify composing deletion then insertion."""
    initial = "Red apple"
    # Delete "Red " -> "apple"
    op1 = TextOperation().delete(4).retain(5)
    # Insert "Green " -> "Green apple"
    op2 = TextOperation().insert("Green ").retain(5)

    composed = compose(op1, op2)
    assert composed.apply(initial) == "Green apple"


def test_compose_mismatched_lengths_error():
    """Verify compose raises error when intermediate lengths mismatch."""
    op1 = TextOperation().insert("abc")  # target_length = 3
    op2 = TextOperation().retain(5)  # base_length = 5
    with pytest.raises(ValueError, match="Cannot compose operations"):
        compose(op1, op2)


# ---------------------------------------------------------------------------
# 4. Invert Tests (Undo / Redo Generation)
# ---------------------------------------------------------------------------


def test_invert_insert():
    """Verify inverting an insert restores the original document."""
    initial = "Hello"
    op = TextOperation().retain(5).insert(" world")
    updated = op.apply(initial)
    assert updated == "Hello world"

    inv = invert(op, initial)
    restored = inv.apply(updated)
    assert restored == initial


def test_invert_delete():
    """Verify inverting a deletion restores the deleted characters."""
    initial = "Hello world"
    op = TextOperation().retain(6).delete(5)
    updated = op.apply(initial)
    assert updated == "Hello "

    inv = invert(op, initial)
    restored = inv.apply(updated)
    assert restored == initial


def test_invert_mixed():
    """Verify inverting a compound operation with insert, retain, and delete."""
    initial = "The quick brown fox"
    # Replace "quick" with "slow", delete "brown "
    op = (
        TextOperation().retain(4).delete(5).insert("slow").retain(1).delete(6).retain(3)
    )
    updated = op.apply(initial)

    inv = invert(op, initial)
    restored = inv.apply(updated)
    assert restored == initial


def test_invert_mismatched_base_length_error():
    """Verify invert raises error when document text length does not match op."""
    op = TextOperation().retain(10)
    with pytest.raises(ValueError, match="Cannot invert operation"):
        invert(op, "short")


# ---------------------------------------------------------------------------
# 5. DocumentState Tests
# ---------------------------------------------------------------------------


def test_document_state_lifecycle():
    """Verify DocumentState lifecycle and dictionary conversion."""
    doc = DocumentState(doc_id="doc-test", title="Test Doc", content="start", version=0)
    op = TextOperation().retain(5).insert("ing")
    doc.apply_operation(op)

    assert doc.content == "starting"
    assert doc.version == 1

    doc_dict = doc.to_dict()
    assert doc_dict["doc_id"] == "doc-test"
    assert doc_dict["content"] == "starting"
    assert doc_dict["version"] == 1
