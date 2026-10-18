"""Document REST routes for PulsePad."""

from flask import Blueprint, Response, current_app, jsonify, request

from app.db.connection import get_db_connection
from app.services.document_service import DocumentService
from app.services.revision_service import RevisionService
from app.socket.editor_events import room_manager

document_bp = Blueprint("documents", __name__)


@document_bp.route("/documents", methods=["GET"])
def list_documents():
    """List all available documents."""
    with get_db_connection() as conn:
        doc_service = DocumentService(conn)
        docs = doc_service.list_documents()

    result = []
    for doc in docs:
        doc_dict = doc.to_dict()
        if doc.id in room_manager.rooms:
            room = room_manager.rooms[doc.id]
            doc_dict["content"] = room.content
            doc_dict["version"] = room.version
            doc_dict["title"] = room.title
        result.append(doc_dict)

    return jsonify({"documents": result}), 200


@document_bp.route("/documents/<doc_id>", methods=["GET"])
def get_document(doc_id: str):
    """Retrieve metadata and content for a single document."""
    with get_db_connection() as conn:
        doc_service = DocumentService(conn)
        doc = doc_service.get_document(doc_id)

    if not doc and doc_id not in room_manager.rooms:
        return jsonify({"error": f"Document '{doc_id}' not found"}), 404

    if doc_id in room_manager.rooms:
        room = room_manager.rooms[doc_id]
        doc_data = {
            "id": doc_id,
            "title": room.title,
            "content": room.content,
            "version": room.version,
            "created_at": doc.created_at if doc else None,
            "updated_at": doc.updated_at if doc else None,
        }
    else:
        doc_data = doc.to_dict()

    return jsonify({"document": doc_data}), 200


@document_bp.route("/documents/<doc_id>/revisions", methods=["GET"])
def get_revisions(doc_id: str):
    """Fetch chronological revision history for a document."""
    with get_db_connection() as conn:
        doc_service = DocumentService(conn)
        doc = doc_service.get_document(doc_id)
        if not doc and doc_id not in room_manager.rooms:
            return jsonify({"error": f"Document '{doc_id}' not found"}), 404

        rev_service = RevisionService(conn)
        revisions = rev_service.get_revisions(doc_id)

    return (
        jsonify(
            {
                "doc_id": doc_id,
                "revisions": [r.to_dict() for r in revisions],
                "count": len(revisions),
            }
        ),
        200,
    )


@document_bp.route("/documents/<doc_id>/rollback", methods=["POST"])
def rollback_document(doc_id: str):
    """Revert document state to a specified historical revision."""
    data = request.get_json(silent=True) or {}
    target_rev = data.get("target_revision")
    author = data.get("author", "System Rollback")

    if target_rev is None or not isinstance(target_rev, int):
        return (
            jsonify({"error": "Missing or invalid 'target_revision' parameter"}),
            400,
        )

    with get_db_connection() as conn:
        doc_service = DocumentService(conn)
        doc = doc_service.get_document(doc_id)
        if not doc:
            return jsonify({"error": f"Document '{doc_id}' not found"}), 404

        if target_rev < 0 or target_rev > doc.version:
            return (
                jsonify(
                    {
                        "error": (
                            f"Target revision {target_rev} out of bounds "
                            f"(valid range: 0-{doc.version})"
                        )
                    }
                ),
                400,
            )

        rev_service = RevisionService(conn)
        try:
            target_content, new_version, rev = rev_service.rollback_document(
                doc_id=doc_id,
                target_revision=target_rev,
                author=author,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    # Synchronize in-memory active room if present
    if doc_id in room_manager.rooms:
        room = room_manager.rooms[doc_id]
        room.content = target_content
        room.version = new_version

    # Broadcast updated document state to all connected socket clients in the room
    socketio = current_app.extensions.get("socketio")
    if socketio and doc_id in room_manager.rooms:
        state = room_manager.get_document_state(doc_id)
        socketio.emit("document_state", state, room=doc_id)

    return (
        jsonify(
            {
                "message": f"Successfully rolled back to revision {target_rev}",
                "doc_id": doc_id,
                "version": new_version,
                "content": target_content,
                "revision": rev.to_dict(),
            }
        ),
        200,
    )


@document_bp.route("/documents/<doc_id>/export", methods=["GET"])
def export_document(doc_id: str):
    """Export document contents as Markdown or Plain Text."""
    fmt = request.args.get("format", "txt").lower()

    with get_db_connection() as conn:
        doc_service = DocumentService(conn)
        doc = doc_service.get_document(doc_id)

    if not doc and doc_id not in room_manager.rooms:
        return jsonify({"error": f"Document '{doc_id}' not found"}), 404

    # If live room is active, export the latest live memory content
    if doc_id in room_manager.rooms:
        room = room_manager.rooms[doc_id]
        content = room.content
    else:
        content = doc.content

    if fmt in ("md", "markdown"):
        filename = f"{doc_id}.md"
        mimetype = "text/markdown; charset=utf-8"
    else:
        filename = f"{doc_id}.txt"
        mimetype = "text/plain; charset=utf-8"

    return Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
