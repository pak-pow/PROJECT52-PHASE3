"""Integration tests for real-time WebSocket synchronization protocol."""

import pytest
from flask import Flask
from flask_socketio import SocketIO

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


def test_socket_connection_and_disconnect(socket_app):
    """Verify socket connection and graceful disconnect."""
    sio, app = socket_app
    client = sio.test_client(app)
    assert client.is_connected()
    client.disconnect()
    assert not client.is_connected()


def test_join_document_state(socket_app):
    """Verify joining a document room yields current document state."""
    sio, app = socket_app
    client = sio.test_client(app)

    client.emit(
        "join_document",
        {"doc_id": "doc-room-1", "user_name": "Alice", "color": "#3b82f6"},
    )

    received = client.get_received()
    state_events = [e for e in received if e["name"] == "document_state"]
    assert len(state_events) == 1

    payload = state_events[0]["args"][0]
    assert payload["doc_id"] == "doc-room-1"
    assert payload["version"] == 0
    assert len(payload["participants"]) == 1
    assert payload["participants"][0]["user_name"] == "Alice"


def test_peer_join_and_leave_notifications(socket_app):
    """Verify peers in the same document room receive join and leave alerts."""
    sio, app = socket_app
    client_a = sio.test_client(app)
    client_b = sio.test_client(app)

    # Alice joins
    client_a.emit(
        "join_document",
        {"doc_id": "doc-shared", "user_name": "Alice", "color": "#10b981"},
    )
    client_a.get_received()  # Flush Alice's inbox

    # Bob joins
    client_b.emit(
        "join_document",
        {"doc_id": "doc-shared", "user_name": "Bob", "color": "#f59e0b"},
    )

    # Alice should receive participant_joined
    a_received = client_a.get_received()
    joined_events = [e for e in a_received if e["name"] == "participant_joined"]
    assert len(joined_events) == 1
    assert joined_events[0]["args"][0]["user_name"] == "Bob"

    # Bob voluntarily leaves
    client_b.emit("leave_document", {"doc_id": "doc-shared"})
    a_after_leave = client_a.get_received()
    left_events = [e for e in a_after_leave if e["name"] == "participant_left"]
    assert len(left_events) == 1
    assert left_events[0]["args"][0]["user_name"] == "Bob"


def test_single_client_operation_flow(socket_app):
    """Verify client operation receives ack with incremented revision."""
    sio, app = socket_app
    client = sio.test_client(app)

    client.emit(
        "join_document",
        {"doc_id": "doc-edit-1", "user_name": "Charlie", "color": "#6366f1"},
    )
    client.get_received()

    # Initial state is empty "" (base_length = 0)
    op = TextOperation().insert("Hello")
    client.emit(
        "client_operation",
        {
            "doc_id": "doc-edit-1",
            "revision": 0,
            "operation": op.to_dict(),
            "author": "Charlie",
        },
    )

    received = client.get_received()
    ack_events = [e for e in received if e["name"] == "operation_ack"]
    assert len(ack_events) == 1
    assert ack_events[0]["args"][0]["revision"] == 1

    room = room_manager.rooms["doc-edit-1"]
    assert room.content == "Hello"
    assert room.version == 1


def test_concurrent_clients_operational_transformation(socket_app):
    """Verify concurrent edits from two clients converge to identical text."""
    sio, app = socket_app
    client_a = sio.test_client(app)
    client_b = sio.test_client(app)

    # Setup room with initial content "cat" at revision 0
    room = room_manager.get_or_create_room(
        doc_id="doc-converge",
        title="Cat Doc",
        initial_content="cat",
        initial_version=0,
    )

    client_a.emit(
        "join_document",
        {"doc_id": "doc-converge", "user_name": "Alice", "color": "#3b82f6"},
    )
    client_b.emit(
        "join_document",
        {"doc_id": "doc-converge", "user_name": "Bob", "color": "#ec4899"},
    )
    client_a.get_received()
    client_b.get_received()

    # Client A types "black " at index 0 (based on revision 0)
    op_a = TextOperation().insert("black ").retain(3)
    client_a.emit(
        "client_operation",
        {
            "doc_id": "doc-converge",
            "revision": 0,
            "operation": op_a.to_dict(),
            "author": "Alice",
        },
    )

    # Alice receives ACK for revision 1
    a_events = client_a.get_received()
    assert any(
        e["name"] == "operation_ack" and e["args"][0]["revision"] == 1 for e in a_events
    )

    # Client B concurrently types "s" at index 3 based on revision 0
    # (has not processed A's edit yet)
    op_b = TextOperation().retain(3).insert("s")
    client_b.emit(
        "client_operation",
        {
            "doc_id": "doc-converge",
            "revision": 0,
            "operation": op_b.to_dict(),
            "author": "Bob",
        },
    )

    # Bob receives ACK for revision 2
    b_events = client_b.get_received()
    assert any(
        e["name"] == "operation_ack" and e["args"][0]["revision"] == 2 for e in b_events
    )

    # Alice receives Bob's transformed operation
    a_remote_events = client_a.get_received()
    remote_b_ops = [e for e in a_remote_events if e["name"] == "remote_operation"]
    assert len(remote_b_ops) == 1
    assert remote_b_ops[0]["args"][0]["revision"] == 2

    # Server content must converge to "black cats"
    assert room.content == "black cats"
    assert room.version == 2


def test_catch_up_operations(socket_app):
    """Verify catch_up returns past operations since requested revision."""
    sio, app = socket_app
    client = sio.test_client(app)

    room_manager.get_or_create_room(
        doc_id="doc-catchup",
        title="Sync Test",
        initial_content="",
        initial_version=0,
    )

    # Apply 2 revisions directly
    op1 = TextOperation().insert("Hello")
    room_manager.apply_client_operation("doc-catchup", 0, op1, "Alice")
    op2 = TextOperation().retain(5).insert(" World")
    room_manager.apply_client_operation("doc-catchup", 1, op2, "Bob")

    client.emit("catch_up", {"doc_id": "doc-catchup", "since_revision": 0})
    received = client.get_received()
    catch_up_events = [e for e in received if e["name"] == "catch_up_response"]
    assert len(catch_up_events) == 1

    ops = catch_up_events[0]["args"][0]["operations"]
    assert len(ops) == 2
    assert ops[0]["revision"] == 1
    assert ops[1]["revision"] == 2


def test_client_operation_validation_errors(socket_app):
    """Verify error events emitted when required payload fields are missing."""
    sio, app = socket_app
    client = sio.test_client(app)

    # Missing doc_id
    client.emit("client_operation", {"revision": 0, "operation": {}})
    received = client.get_received()
    err_events = [e for e in received if e["name"] == "operation_error"]
    assert len(err_events) == 1

    # Catch-up missing doc_id
    client.emit("catch_up", {})
    received2 = client.get_received()
    err2 = [e for e in received2 if e["name"] == "operation_error"]
    assert len(err2) == 1
