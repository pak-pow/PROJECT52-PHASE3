"""In-memory room and presence manager for collaborative editing sessions."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Participant:
    """Connected user participant metadata."""

    sid: str
    user_name: str
    color: str
    cursor_pos: int = 0
    selection_end: Optional[int] = None


@dataclass
class RoomSession:
    """Active document room tracking connected participants."""

    doc_id: str
    participants: Dict[str, Participant] = field(default_factory=dict)


class RoomManager:
    """Manages active rooms and active socket connections."""

    def __init__(self):
        self.rooms: Dict[str, RoomSession] = {}

    def get_or_create_room(self, doc_id: str) -> RoomSession:
        """Fetch existing room session or create a new session."""
        if doc_id not in self.rooms:
            self.rooms[doc_id] = RoomSession(doc_id=doc_id)
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

    def list_participants(self, doc_id: str) -> List[Participant]:
        """List all active participants in a document room."""
        if doc_id in self.rooms:
            return list(self.rooms[doc_id].participants.values())
        return []
