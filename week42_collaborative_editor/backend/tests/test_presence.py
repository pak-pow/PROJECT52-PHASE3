"""Tests for room presence and participant management."""

from app.socket.room_manager import RoomManager


def test_room_manager_add_and_list_participants():
    """Verify adding participants to a document room and listing them."""
    mgr = RoomManager()
    p1 = mgr.add_participant(
        doc_id="doc-1",
        sid="sid-123",
        user_name="Alice",
        color="#3b82f6",
    )
    assert p1.user_name == "Alice"

    participants = mgr.list_participants("doc-1")
    assert len(participants) == 1
    assert participants[0].sid == "sid-123"

    removed = mgr.remove_participant("doc-1", "sid-123")
    assert removed is not None
    assert len(mgr.list_participants("doc-1")) == 0


def test_room_manager_edge_cases():
    """Verify non-existent participant removal and missing room list."""
    mgr = RoomManager()
    assert mgr.remove_participant("unknown-doc", "sid-999") is None
    assert mgr.list_participants("unknown-doc") == []
