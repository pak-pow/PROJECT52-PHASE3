"""Tests for multi-user presence, awareness, and remote cursor tracking."""

import time

import pytest
from flask import Flask
from flask_socketio import SocketIO

from app.engine.cursor import (
    PRESENCE_COLORS,
    get_user_color,
    transform_cursor_position,
    transform_selection,
)
from app.engine.operation import TextOperation
from app.socket.editor_events import register_socket_events, room_manager


@pytest.fixture(autouse=True)
def clear_room_manager():
    """Clear in-memory rooms between test runs."""
    room_manager.rooms.clear()
    yield
    room_manager.rooms.clear()


@pytest.fixture
def socket_app(app: Flask):
    """Provide Flask app with registered SocketIO instance."""
    sio = SocketIO(app, async_mode="threading")
    register_socket_events(sio)
    return sio, app


# ---------------------------------------------------------------------------
# 1. Color Derivation and Cursor Transformation Tests
# ---------------------------------------------------------------------------


def test_user_color_generation():
    """Verify deterministic pastel color selection from user name."""
    c1 = get_user_color("Alice")
    c2 = get_user_color("Alice")
    assert c1 == c2
    assert c1 in PRESENCE_COLORS

    assert get_user_color("") in PRESENCE_COLORS

    colors = {get_user_color(f"User_{i}") for i in range(20)}
    assert len(colors) > 1


def test_cursor_transform_insertions():
    """Verify cursor position adjusts on text insertions."""
    # Document "world" (length 5), cursor at 0
    # Insert "hello " at 0 -> "hello world"
    op = TextOperation().insert("hello ").retain(5)
    # Insertion at 0 shifts cursor 0 forward by 6 -> 6
    assert transform_cursor_position(0, op) == 6

    # Cursor at 5 (end of "world")
    # Insertion at 0 shifts cursor 5 forward by 6 -> 11
    assert transform_cursor_position(5, op) == 11

    # Insertion after cursor: doc "hello" (len 5), cursor at 2
    # Op: retain(5), insert(" world")
    op_after = TextOperation().retain(5).insert(" world")
    assert transform_cursor_position(2, op_after) == 2


def test_cursor_transform_deletions():
    """Verify cursor position adjusts or collapses on text deletions."""
    # Document "hello world" (len 11), cursor at 11
    # Delete "world" at index 6: retain(6), delete(5)
    op_del = TextOperation().retain(6).delete(5)
    assert transform_cursor_position(11, op_del) == 6

    # Cursor strictly inside deleted span: cursor at 8 (inside "world")
    # Should collapse to start of deletion (index 6)
    assert transform_cursor_position(8, op_del) == 6

    # Deletion after cursor: cursor at 3 (inside "hello")
    assert transform_cursor_position(3, op_del) == 3

    # Negative cursor clamps to 0
    assert transform_cursor_position(-5, op_del) == 0


def test_selection_transformation():
    """Verify transforming range selections with start and end offsets."""
    # Document "hello brave world" (len 17), selection from 6 to 11 ("brave")
    # Delete "hello " at 0: delete(6), retain(11)
    op = TextOperation().delete(6).retain(11)
    new_start, new_end = transform_selection(6, 11, op)
    assert new_start == 0
    assert new_end == 5

    # None selection end
    start_only, end_only = transform_selection(6, None, op)
    assert start_only == 0
    assert end_only is None


# ---------------------------------------------------------------------------
# 2. RoomManager Presence State Tests
# ---------------------------------------------------------------------------


def test_room_manager_presence_updates():
    """Verify cursor, typing, and activity state changes in RoomManager."""
    mgr = room_manager
    p = mgr.add_participant("doc-pres", "sid-1", "Alice", "#3b82f6")
    assert p.status == "active"
    assert not p.is_typing

    # Update cursor
    updated = mgr.update_participant_cursor("doc-pres", "sid-1", 10, 15)
    assert updated is not None
    assert updated.cursor_pos == 10
    assert updated.selection_end == 15

    # Update typing status
    typing_p = mgr.update_participant_typing("doc-pres", "sid-1", True)
    assert typing_p is not None
    assert typing_p.is_typing is True

    # Touch participant
    mgr.touch_participant("doc-pres", "sid-1")

    # Missing participant returns None
    assert mgr.update_participant_cursor("doc-pres", "unknown", 0) is None
    assert mgr.update_participant_typing("doc-pres", "unknown", False) is None


def test_prune_inactive_participants():
    """Verify pruning participants who exceed inactivity timeout."""
    mgr = room_manager
    p = mgr.add_participant("doc-timeout", "sid-old", "OldUser")
    p.last_active = time.time() - 100.0

    pruned = mgr.prune_inactive_participants("doc-timeout", timeout_sec=60.0)
    assert "sid-old" in pruned
    assert len(mgr.list_participants("doc-timeout")) == 0

    assert mgr.prune_inactive_participants("non-existent") == []


# ---------------------------------------------------------------------------
# 3. Real-Time Socket Presence Broadcast Tests
# ---------------------------------------------------------------------------


def test_socket_cursor_move_broadcast(socket_app):
    """Verify cursor_move updates are broadcast to peers."""
    sio, app = socket_app
    client_a = sio.test_client(app)
    client_b = sio.test_client(app)

    client_a.emit(
        "join_document",
        {"doc_id": "doc-cursor", "user_name": "Alice", "color": "#3b82f6"},
    )
    client_b.emit(
        "join_document",
        {"doc_id": "doc-cursor", "user_name": "Bob", "color": "#ec4899"},
    )
    client_a.get_received()
    client_b.get_received()

    # Alice moves cursor to position 15
    client_a.emit(
        "cursor_move",
        {"doc_id": "doc-cursor", "cursor_pos": 15, "selection_end": 20},
    )

    # Bob receives cursor_update
    b_events = client_b.get_received()
    cursor_events = [e for e in b_events if e["name"] == "cursor_update"]
    assert len(cursor_events) == 1
    update_data = cursor_events[0]["args"][0]
    assert update_data["user_name"] == "Alice"
    assert update_data["cursor_pos"] == 15
    assert update_data["selection_end"] == 20


def test_socket_typing_status_and_heartbeat(socket_app):
    """Verify typing status updates and heartbeat acknowledgment."""
    sio, app = socket_app
    client_a = sio.test_client(app)
    client_b = sio.test_client(app)

    client_a.emit("join_document", {"doc_id": "doc-typing", "user_name": "Alice"})
    client_b.emit("join_document", {"doc_id": "doc-typing", "user_name": "Bob"})
    client_a.get_received()
    client_b.get_received()

    # Alice starts typing
    client_a.emit("typing_status", {"doc_id": "doc-typing", "is_typing": True})
    b_events = client_b.get_received()
    typing_events = [e for e in b_events if e["name"] == "typing_update"]
    assert len(typing_events) == 1
    assert typing_events[0]["args"][0]["is_typing"] is True

    # Alice sends heartbeat
    client_a.emit("heartbeat", {"doc_id": "doc-typing"})
    a_events = client_a.get_received()
    assert any(e["name"] == "heartbeat_ack" for e in a_events)


def test_server_side_cursor_shifting_on_remote_edit(socket_app):
    """Verify server shifts stored remote cursor position when text is inserted."""
    sio, app = socket_app
    client_a = sio.test_client(app)
    client_b = sio.test_client(app)

    # Start with document "cat" at revision 0
    room = room_manager.get_or_create_room(
        doc_id="doc-shift",
        title="Shift Test",
        initial_content="cat",
        initial_version=0,
    )

    client_a.emit("join_document", {"doc_id": "doc-shift", "user_name": "Alice"})
    client_b.emit("join_document", {"doc_id": "doc-shift", "user_name": "Bob"})
    client_a.get_received()
    client_b.get_received()

    # Bob positions cursor at index 3 (after "cat")
    client_b.emit("cursor_move", {"doc_id": "doc-shift", "cursor_pos": 3})
    client_a.get_received()

    bob_sid = [s for s in room.participants if room.participants[s].user_name == "Bob"][
        0
    ]
    assert room.participants[bob_sid].cursor_pos == 3

    # Alice inserts "black " (6 chars) at index 0
    op = TextOperation().insert("black ").retain(3)
    client_a.emit(
        "client_operation",
        {
            "doc_id": "doc-shift",
            "revision": 0,
            "operation": op.to_dict(),
            "author": "Alice",
        },
    )

    # Bob's cursor on the server must automatically shift from 3 to 9
    assert room.participants[bob_sid].cursor_pos == 9
