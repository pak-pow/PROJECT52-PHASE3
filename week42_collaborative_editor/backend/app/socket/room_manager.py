"""In-memory room and presence manager for collaborative editing sessions."""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.engine.cursor import get_user_color, transform_selection
from app.engine.operation import TextOperation
from app.engine.transform import transform


@dataclass
class Participant:
    """Connected user participant metadata and presence awareness."""

    sid: str
    user_name: str
    color: str
    cursor_pos: int = 0
    selection_end: Optional[int] = None
    is_typing: bool = False
    last_active: float = field(default_factory=time.time)
    status: str = "active"

    def to_dict(self) -> Dict[str, Any]:
        """Convert participant to dictionary."""
        return {
            "sid": self.sid,
            "user_name": self.user_name,
            "color": self.color,
            "cursor_pos": self.cursor_pos,
            "selection_end": self.selection_end,
            "is_typing": self.is_typing,
            "last_active": self.last_active,
            "status": self.status,
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
        self,
        doc_id: str,
        sid: str,
        user_name: str,
        color: Optional[str] = None,
    ) -> Participant:
        """Add participant to a document room with assigned color."""
        room = self.get_or_create_room(doc_id)
        assigned_color = color or get_user_color(user_name)
        participant = Participant(
            sid=sid,
            user_name=user_name,
            color=assigned_color,
            last_active=time.time(),
        )
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

    def update_participant_cursor(
        self,
        doc_id: str,
        sid: str,
        cursor_pos: int,
        selection_end: Optional[int] = None,
    ) -> Optional[Participant]:
        """Update participant cursor position and text selection boundaries."""
        if doc_id not in self.rooms or sid not in self.rooms[doc_id].participants:
            return None
        participant = self.rooms[doc_id].participants[sid]
        participant.cursor_pos = max(0, cursor_pos)
        participant.selection_end = selection_end
        participant.last_active = time.time()
        participant.status = "active"
        return participant

    def update_participant_typing(
        self, doc_id: str, sid: str, is_typing: bool
    ) -> Optional[Participant]:
        """Update participant typing indicator state."""
        if doc_id not in self.rooms or sid not in self.rooms[doc_id].participants:
            return None
        participant = self.rooms[doc_id].participants[sid]
        participant.is_typing = is_typing
        participant.last_active = time.time()
        return participant

    def touch_participant(self, doc_id: str, sid: str) -> None:
        """Mark participant as recently active."""
        if doc_id in self.rooms and sid in self.rooms[doc_id].participants:
            p = self.rooms[doc_id].participants[sid]
            p.last_active = time.time()
            p.status = "active"

    def prune_inactive_participants(
        self, doc_id: str, timeout_sec: float = 60.0
    ) -> List[str]:
        """Prune or mark idle participants who have timed out."""
        if doc_id not in self.rooms:
            return []
        now = time.time()
        pruned_sids: List[str] = []
        room = self.rooms[doc_id]
        for sid, p in list(room.participants.items()):
            if now - p.last_active > timeout_sec:
                room.participants.pop(sid, None)
                pruned_sids.append(sid)
        return pruned_sids

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
        author_sid: Optional[str] = None,
    ) -> Tuple[TextOperation, int]:
        """Apply an incoming client operation with catch-up transformation.

        Also shifts remote peers' cursor positions dynamically so remote
        cursors do not drift when text is inserted or deleted.
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
            for _, hist_op, _ in room.history[client_revision:]:
                op, _ = transform(op, hist_op, priority=True)

        # Apply transformed operation to current server document
        room.content = op.apply(room.content)
        room.version += 1
        room.history.append((room.version, op, author))

        # Shift cursors of all other participants in the room
        for sid, peer in room.participants.items():
            if sid != author_sid:
                new_start, new_end = transform_selection(
                    peer.cursor_pos, peer.selection_end, op
                )
                peer.cursor_pos = new_start
                peer.selection_end = new_end

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
