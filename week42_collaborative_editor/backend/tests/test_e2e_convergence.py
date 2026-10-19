"""End-to-end multi-client convergence, fuzzing, and invariant stress tests."""

import random
from typing import List

from app.engine.compose import compose
from app.engine.cursor import transform_cursor_position, transform_selection
from app.engine.document import DocumentState
from app.engine.invert import invert
from app.engine.operation import TextOperation
from app.engine.transform import transform
from app.services.document_service import DocumentService
from app.services.revision_service import RevisionService
from app.socket.room_manager import RoomManager


def _generate_random_op(doc_len: int, rng: random.Random) -> TextOperation:
    """Helper to generate a valid TextOperation for a document of length doc_len."""
    op = TextOperation()
    cursor = 0
    words = ["alpha", "beta", "gamma", " ", "delta", "123", "\n"]

    while cursor < doc_len:
        remaining = doc_len - cursor
        action = rng.choice(["retain", "insert", "delete"])

        if action == "retain":
            count = rng.randint(1, remaining)
            op.retain(count)
            cursor += count
        elif action == "delete":
            count = rng.randint(1, remaining)
            op.delete(count)
            cursor += count
        elif action == "insert":
            text = rng.choice(words)
            op.insert(text)

    # 40% chance of a trailing insertion at EOF
    if rng.random() < 0.4:
        op.insert("!")

    return op


def test_baseline_convergence_stub():
    """Verify document convergence baseline."""
    doc = DocumentState(doc_id="doc-e2e", content="Hello", version=0)
    op = TextOperation()
    op.retain(5).insert(" World")
    doc.apply_operation(op)
    assert doc.content == "Hello World"


def test_fuzz_tp1_transformation_invariant():
    """Property-based fuzzing testing Transformation Property 1 (TP1).

    Ensures that for any two concurrent operations A and B applied to state S:
    T(A, B) -> (A', B') such that B'(A(S)) == A'(B(S)).
    """
    rng = random.Random(20261019)
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 \n"

    for iteration in range(50):
        # Generate random baseline text (length 5 to 35)
        text_len = rng.randint(5, 35)
        baseline = "".join(rng.choice(alphabet) for _ in range(text_len))

        # Generate two concurrent operations from baseline
        op_a = _generate_random_op(len(baseline), rng)
        op_b = _generate_random_op(len(baseline), rng)

        # Pairwise operational transformation
        op_a_prime, op_b_prime = transform(op_a, op_b, priority=True)

        # Apply in both execution orders
        doc_a = op_a.apply(baseline)
        doc_b = op_b.apply(baseline)

        doc_ab = op_b_prime.apply(doc_a)
        doc_ba = op_a_prime.apply(doc_b)

        assert doc_ab == doc_ba, (
            f"TP1 convergence failure on iteration {iteration}!\n"
            f"Baseline: {baseline!r}\n"
            f"Path A->B': {doc_ab!r}\n"
            f"Path B->A': {doc_ba!r}"
        )


def test_fuzz_composition_and_inversion_roundtrip():
    """Verify sequential composition and lossless undo inversion across operations."""
    rng = random.Random(42)
    alphabet = "abcdefghijklmnopqrstuvwxyz "

    for iteration in range(20):
        initial_text = "".join(rng.choice(alphabet) for _ in range(20))
        current_text = initial_text
        operations: List[TextOperation] = []

        # Apply 5 consecutive sequential operations
        for _ in range(5):
            op = _generate_random_op(len(current_text), rng)
            current_text = op.apply(current_text)
            operations.append(op)

        # Compose all 5 operations into a single compound operation
        composed_op = operations[0].copy()
        for next_op in operations[1:]:
            composed_op = compose(composed_op, next_op)

        # Verify composed operation transforms initial text directly to final text
        assert composed_op.apply(initial_text) == current_text

        # Verify operation inversion performs lossless undo
        inverted_op = invert(composed_op, initial_text)
        restored_text = inverted_op.apply(current_text)
        assert restored_text == initial_text, (
            f"Inversion failure on iteration {iteration}: "
            f"{restored_text!r} != {initial_text!r}"
        )


def test_multi_client_concurrent_editing_simulation():
    """Simulate 4 concurrent clients submitting operations out of order to server."""
    manager = RoomManager()
    doc_id = "sim-doc"
    initial_content = "The quick brown fox jumps over the lazy dog."
    room = manager.get_or_create_room(
        doc_id=doc_id,
        title="Simulation Doc",
        initial_content=initial_content,
        initial_version=0,
    )

    # 4 Collaborators start with local replica at revision 0
    # Alice: Inserts "very " before "quick" at index 4
    op_alice = (
        TextOperation().retain(4).insert("very ").retain(len(initial_content) - 4)
    )

    # Bob: Changes "brown" (index 10-15) to "red"
    op_bob = (
        TextOperation()
        .retain(10)
        .delete(5)
        .insert("red")
        .retain(len(initial_content) - 15)
    )

    # Charlie: Deletes "lazy " (index 35-40)
    op_charlie = TextOperation().retain(35).delete(5).retain(len(initial_content) - 40)

    # Dana: Appends " quietly" before trailing period (index 43)
    op_dana = TextOperation().retain(43).insert(" quietly").retain(1)

    # Interleaved server arrival order: Alice (v0), Charlie (v0), Bob (v0), Dana (v0)
    # 1. Alice arrives first
    _, v1 = manager.apply_client_operation(
        doc_id=doc_id,
        client_revision=0,
        operation=op_alice,
        author="Alice",
    )
    assert v1 == 1

    # 2. Charlie arrives lagging behind by 1 revision
    _, v2 = manager.apply_client_operation(
        doc_id=doc_id,
        client_revision=0,
        operation=op_charlie,
        author="Charlie",
    )
    assert v2 == 2

    # 3. Bob arrives lagging behind by 2 revisions
    _, v3 = manager.apply_client_operation(
        doc_id=doc_id,
        client_revision=0,
        operation=op_bob,
        author="Bob",
    )
    assert v3 == 3

    # 4. Dana arrives lagging behind by 3 revisions
    _, v4 = manager.apply_client_operation(
        doc_id=doc_id,
        client_revision=0,
        operation=op_dana,
        author="Dana",
    )
    assert v4 == 4

    # Verify authoritative server content has incorporated all mutations
    server_text = room.content
    assert "very quick" in server_text
    assert "red fox" in server_text
    assert "lazy" not in server_text
    assert "quietly." in server_text


def test_lagging_client_catch_up_and_recovery():
    """Verify lagging client catches up across sequential server revisions."""
    manager = RoomManager()
    doc_id = "catchup-doc"
    manager.get_or_create_room(
        doc_id=doc_id,
        title="Catch-Up Doc",
        initial_content="Base",
        initial_version=0,
    )

    # Server processes 5 consecutive operations
    for i in range(1, 6):
        op = TextOperation().retain(len(manager.rooms[doc_id].content)).insert(f" {i}")
        manager.apply_client_operation(
            doc_id=doc_id,
            client_revision=i - 1,
            operation=op,
            author=f"Author{i}",
        )

    # Client was at revision 2; requests catch-up operations
    catch_ups = manager.get_catch_up_operations(doc_id=doc_id, since_revision=2)
    assert len(catch_ups) == 3

    # Reconstruct client state from revision 2 text
    client_text = "Base 1 2"
    for item in catch_ups:
        op = TextOperation.from_dict(item["operation"])
        client_text = op.apply(client_text)

    assert client_text == manager.rooms[doc_id].content


def test_cursor_drift_resistance_under_concurrent_edits():
    """Verify caret and selection boundaries transform without drift or errors."""
    # Document length 20, cursor at index 10
    # Test insertion before cursor (at index 5) shifts caret forward
    op_ins_before = TextOperation().retain(5).insert("xyz").retain(15)
    assert transform_cursor_position(10, op_ins_before) == 13

    # Test insertion after cursor (at index 15) leaves caret intact
    op_ins_after = TextOperation().retain(15).insert("xyz").retain(5)
    assert transform_cursor_position(10, op_ins_after) == 10

    # Test deletion before cursor (from index 2 to 6) shifts caret backward
    op_del_before = TextOperation().retain(2).delete(4).retain(14)
    assert transform_cursor_position(10, op_del_before) == 6

    # Test deletion wrapping cursor (from index 8 to 14) collapses to deletion start
    op_del_wrap = TextOperation().retain(8).delete(6).retain(6)
    assert transform_cursor_position(10, op_del_wrap) == 8

    # Test range selection transformation in document of length 30
    op_sel = TextOperation().retain(5).insert("header_").retain(25)
    start, end = transform_selection(10, 20, op_sel)
    assert start == 17
    assert end == 27


def test_e2e_persistence_snapshots_and_rollback_flow(db_conn):
    """Verify 20-revision continuous persistence, snapshots, and multi-step rollback."""
    doc_service = DocumentService(db_conn)
    rev_service = RevisionService(db_conn)

    doc_id = "stress-doc"
    initial_text = "Seed Text"
    doc_service.create_document(
        doc_id=doc_id,
        title="Stress Test Document",
        content=initial_text,
        version=0,
    )
    rev_service.create_snapshot(doc_id, 0, initial_text)

    history_snapshots = {0: initial_text}
    current_text = initial_text

    # Generate 20 sequential revisions
    for v in range(1, 21):
        op = TextOperation().retain(len(current_text)).insert(f" +{v}")
        current_text = op.apply(current_text)
        rev_service.record_revision(
            doc_id=doc_id,
            revision_num=v,
            author=f"Worker-{v}",
            operation=op,
            current_content=current_text,
        )
        doc_service.save_document(doc_id, current_text, v)
        history_snapshots[v] = current_text

    # Verify snapshots exist at revision 0, 1, 10, 20
    snapshots = rev_service.get_snapshots(doc_id)
    snapshot_revs = [s.revision_num for s in snapshots]
    assert 0 in snapshot_revs
    assert 1 in snapshot_revs
    assert 10 in snapshot_revs
    assert 20 in snapshot_revs

    # Verify point-in-time reconstruction matches exact historical text at every step
    for rev_num in range(0, 21):
        reconstructed = rev_service.get_content_at_revision(doc_id, rev_num)
        assert (
            reconstructed == history_snapshots[rev_num]
        ), f"Reconstruction mismatch at revision {rev_num}"

    # Rollback to revision 10
    text_v21, v21, rev21 = rev_service.rollback_document(
        doc_id=doc_id, target_revision=10, author="Rollback-Admin"
    )
    assert v21 == 21
    assert text_v21 == history_snapshots[10]
    assert rev21.author == "Rollback-Admin"

    # Rollback to baseline revision 0
    text_v22, v22, _ = rev_service.rollback_document(
        doc_id=doc_id, target_revision=0, author="Rollback-Reset"
    )
    assert v22 == 22
    assert text_v22 == initial_text

    # Rollback back to revision 20
    text_v23, v23, _ = rev_service.rollback_document(
        doc_id=doc_id, target_revision=20, author="Rollback-Restore"
    )
    assert v23 == 23
    assert text_v23 == history_snapshots[20]
