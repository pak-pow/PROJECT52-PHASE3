"""Socket.IO event listeners for real-time document synchronization and presence."""

from flask import request
from flask_socketio import SocketIO, emit, join_room, leave_room

from app.db.connection import get_db_connection
from app.engine.operation import TextOperation
from app.models.document_model import Document
from app.socket.room_manager import RoomManager

room_manager = RoomManager()


def register_socket_events(socketio: SocketIO) -> None:
    """Register WebSocket event handlers with SocketIO instance."""

    @socketio.on("connect")
    def handle_connect():
        """Handle new client socket connection."""
        pass

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection and clean up room participation."""
        sid = request.sid
        found = room_manager.find_participant_room(sid)
        if found:
            doc_id, participant = found
            room_manager.remove_participant(doc_id, sid)
            emit(
                "participant_left",
                {"sid": sid, "user_name": participant.user_name},
                room=doc_id,
            )

    @socketio.on("join_document")
    def handle_join_document(data: dict):
        """Handle client joining a collaborative document session."""
        doc_id = data.get("doc_id", "welcome-doc")
        user_name = data.get("user_name", "Anonymous")
        color = data.get("color")
        sid = request.sid

        if doc_id not in room_manager.rooms:
            try:
                with get_db_connection() as conn:
                    doc = Document.get_by_id(conn, doc_id)
                    if doc:
                        room_manager.get_or_create_room(
                            doc_id=doc.id,
                            title=doc.title,
                            initial_content=doc.content,
                            initial_version=doc.version,
                        )
                    else:
                        room_manager.get_or_create_room(
                            doc_id=doc_id,
                            title="Untitled Document",
                            initial_content="",
                            initial_version=0,
                        )
            except Exception:
                room_manager.get_or_create_room(
                    doc_id=doc_id,
                    title="Untitled Document",
                    initial_content="",
                    initial_version=0,
                )

        join_room(doc_id)
        participant = room_manager.add_participant(
            doc_id=doc_id, sid=sid, user_name=user_name, color=color
        )

        # Emit full initial state to joining client
        emit("document_state", room_manager.get_document_state(doc_id))

        # Notify other peers in room of new participant
        emit(
            "participant_joined",
            participant.to_dict(),
            room=doc_id,
            include_self=False,
        )

    @socketio.on("leave_document")
    def handle_leave_document(data: dict):
        """Handle client voluntarily leaving a document session."""
        doc_id = data.get("doc_id")
        sid = request.sid
        if not doc_id:
            return

        leave_room(doc_id)
        participant = room_manager.remove_participant(doc_id, sid)
        if participant:
            emit(
                "participant_left",
                {"sid": sid, "user_name": participant.user_name},
                room=doc_id,
            )

    @socketio.on("cursor_move")
    def handle_cursor_move(data: dict):
        """Update and broadcast participant cursor/selection positions."""
        doc_id = data.get("doc_id")
        cursor_pos = data.get("cursor_pos", 0)
        selection_end = data.get("selection_end")
        sid = request.sid

        if not doc_id:
            return

        end_val = int(selection_end) if selection_end is not None else None
        participant = room_manager.update_participant_cursor(
            doc_id=doc_id,
            sid=sid,
            cursor_pos=int(cursor_pos),
            selection_end=end_val,
        )
        if participant:
            emit(
                "cursor_update",
                participant.to_dict(),
                room=doc_id,
                include_self=False,
            )

    @socketio.on("typing_status")
    def handle_typing_status(data: dict):
        """Update and broadcast participant typing indicator status."""
        doc_id = data.get("doc_id")
        is_typing = bool(data.get("is_typing", False))
        sid = request.sid

        if not doc_id:
            return

        participant = room_manager.update_participant_typing(
            doc_id=doc_id, sid=sid, is_typing=is_typing
        )
        if participant:
            emit(
                "typing_update",
                {
                    "sid": sid,
                    "user_name": participant.user_name,
                    "is_typing": is_typing,
                },
                room=doc_id,
                include_self=False,
            )

    @socketio.on("heartbeat")
    def handle_heartbeat(data: dict):
        """Touch participant activity timestamp to prevent timeout."""
        doc_id = data.get("doc_id")
        sid = request.sid
        if doc_id:
            room_manager.touch_participant(doc_id, sid)
            emit("heartbeat_ack", {"status": "ok"})

    @socketio.on("client_operation")
    def handle_client_operation(data: dict):
        """Process, transform, and broadcast an incoming client text operation."""
        doc_id = data.get("doc_id")
        client_revision = data.get("revision")
        raw_operation = data.get("operation")
        author = data.get("author", "Anonymous")
        sid = request.sid

        if not doc_id or client_revision is None or raw_operation is None:
            emit(
                "operation_error",
                {"error": "Missing required fields: doc_id, revision, operation"},
            )
            return

        try:
            op = TextOperation.from_dict(raw_operation)
            transformed_op, new_version = room_manager.apply_client_operation(
                doc_id=doc_id,
                client_revision=int(client_revision),
                operation=op,
                author=author,
                author_sid=sid,
            )

            # Acknowledge submission to the author
            emit(
                "operation_ack",
                {"doc_id": doc_id, "revision": new_version},
            )

            # Broadcast transformed operation to all other clients in the room
            emit(
                "remote_operation",
                {
                    "doc_id": doc_id,
                    "revision": new_version,
                    "operation": transformed_op.to_dict(),
                    "author": author,
                },
                room=doc_id,
                include_self=False,
            )

        except Exception as exc:
            emit("operation_error", {"doc_id": doc_id, "error": str(exc)})

    @socketio.on("catch_up")
    def handle_catch_up(data: dict):
        """Provide historical operations to client lagging behind server revision."""
        doc_id = data.get("doc_id")
        since_revision = data.get("since_revision", 0)

        if not doc_id:
            emit("operation_error", {"error": "Missing doc_id for catch_up"})
            return

        ops = room_manager.get_catch_up_operations(
            doc_id=doc_id, since_revision=int(since_revision)
        )
        emit(
            "catch_up_response",
            {"doc_id": doc_id, "operations": ops},
        )
