"""Socket.IO event listeners for editor coordination."""

from flask_socketio import SocketIO

from app.socket.room_manager import RoomManager

room_manager = RoomManager()


def register_socket_events(socketio: SocketIO) -> None:
    """Register WebSocket event handlers with SocketIO instance."""

    @socketio.on("connect")
    def handle_connect():
        """Handle client connection."""
        pass

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection."""
        pass
