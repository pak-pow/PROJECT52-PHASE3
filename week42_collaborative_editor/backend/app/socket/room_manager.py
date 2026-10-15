"""In-memory room and presence manager for collaborative editing sessions."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.engine.operation import TextOperation
from app.engine.transform import transform


@dataclass
class Participant:
    """Connected user participant metadata."""

    sid: str
    user_name: str
    color: str
    cursor_pos: int = 0
    selection_end: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert participant to dictionary."""
        return {
            "sid": self.sid,
            "user_name": self.user_name,
            "color": self.color,
            "cursor_pos": self.cursor_pos,
            "selection_end": self.selection_end,
        }


@dataclass
class RoomSession:
    """Active document room tracking document state, history, and peers."""

    doc_id: str
    title: str = "Untitled Document"
    content: str = ""
    version: int = 0
    history: List[Tuple[int, TextOperation, str]] = field(default_factory=list)
    participants: Dict[str, Participant] = field(default_factory=dict)


class RoomManager:
    """Manages active rooms and authoritative operational transformation sync."""

    def __init__(self):
        self.rooms: Dict[str, RoomSession] = {}

    def get_or_create_room(
        self,
        doc_id: str,
        title: str = "Untitled Document",
        initial_content: str = "",
        initial_version: int = 0,
    ) -> RoomSession:
        """Fetch existing room session or create a new initialized session."""
        if doc_id not in self.rooms:
            self.rooms[doc_id] = RoomSession(
                doc_id=doc_id,
                title=title,
                content=initial_content,
                version=initial_version,
            )
        return self.rooms[doc_id]

    def add_participant(
        self, doc_id: str, sid: str, user_name: str, color: str
    ) -> Participant:
        """Add participant to a document room."""
        room = self.get_or_create_room(doc_id)
        participant = Participant(sid=sid, user_name=user_name, color=color)
        room.participants[sid] = participant
        return participant

    def remove_participant(self, doc_id: str, sid: str) -> Optional[Participant]:
        """Remove participant from document room."""
        if doc_id in self.rooms and sid in self.rooms[doc_id].participants:
            return self.rooms[doc_id].participants.pop(sid)
        return None

    def find_participant_room(self, sid: str) -> Optional[Tuple[str, Participant]]:
        """Find the document room and participant by socket ID."""
        for doc_id, room in self.rooms.items():
            if sid in room.participants:
                return doc_id, room.participants[sid]
        return None

    def list_participants(self, doc_id: str) -> List[Participant]:
        """List all active participants in a document room."""
        if doc_id in self.rooms:
            return list(self.rooms[doc_id].participants.values())
        return []

    def get_document_state(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full state payload for a document room."""
        if doc_id not in self.rooms:
            return None
        room = self.rooms[doc_id]
        return {
            "doc_id": room.doc_id,
            "title": room.title,
            "content": room.content,
            "version": room.version,
            "participants": [p.to_dict() for p in room.participants.values()],
        }

    def apply_client_operation(
        self,
        doc_id: str,
        client_revision: int,
        operation: TextOperation,
        author: str = "Anonymous",
    ) -> Tuple[TextOperation, int]:
        """Apply an incoming client operation with catch-up transformation.

        Args:
            doc_id: Identifier of target document room.
            client_revision: Revision number client based their operation on.
            operation: Incoming client TextOperation.
            author: Name or identifier of submitting user.

        Returns:
            Tuple of (transformed_operation, new_server_revision).

        Raises:
            ValueError: On invalid revisions, missing rooms, or length mismatch.
        """
        if doc_id not in self.rooms:
            raise ValueError(f"Document room '{doc_id}' does not exist")

        room = self.rooms[doc_id]

        if client_revision < 0:
            raise ValueError("Client revision cannot be negative")

        if client_revision > room.version:
            raise ValueError(
                f"Client revision {client_revision} is ahead of "
                f"server revision {room.version}"
            )

        op = operation.copy()

        # If client is behind, transform against intervening historical ops
        if client_revision < room.version:
            # Slices history from client_revision up to current version
            for _, hist_op, _ in room.history[client_revision:]:
                op, _ = transform(op, hist_op, priority=True)

        # Apply transformed operation to current server document
        room.content = op.apply(room.content)
        room.version += 1
        room.history.append((room.version, op, author))

        return op, room.version

    def get_catch_up_operations(
        self, doc_id: str, since_revision: int
    ) -> List[Dict[str, Any]]:
        """Retrieve list of historical operations since a given revision."""
        if doc_id not in self.rooms:
            return []
        room = self.rooms[doc_id]
        if since_revision < 0 or since_revision >= room.version:
            return []

        result = []
        for rev_num, op, author in room.history[since_revision:]:
            result.append(
                {
                    "revision": rev_num,
                    "operation": op.to_dict(),
                    "author": author,
                }
            )
        return result
