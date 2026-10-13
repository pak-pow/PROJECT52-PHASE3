"""Server entrypoint for PulsePad collaborative editor."""

from flask_socketio import SocketIO

from app import create_app
from app.socket.editor_events import register_socket_events

app = create_app()
socketio = SocketIO(
    app,
    cors_allowed_origins=app.config.get("CORS_ALLOWED_ORIGINS", "*"),
    async_mode="threading",
)
register_socket_events(socketio)

if __name__ == "__main__":
    socketio.run(
        app,
        host="127.0.0.1",
        port=5000,
        debug=app.config.get("DEBUG", False),
    )
