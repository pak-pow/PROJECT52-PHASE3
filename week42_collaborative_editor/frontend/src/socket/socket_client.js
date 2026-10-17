/**
 * Socket.IO communication client for real-time document synchronization.
 */

export class SocketClient {
  constructor(serverUrl = "http://127.0.0.1:5000") {
    this.serverUrl = serverUrl;
    this.socket = null;
    this.connected = false;
    this.listeners = new Map();
  }

  connect() {
    if (this.socket) return;

    // Use global io if available (from socket.io.min.js)
    if (typeof io !== "undefined") {
      this.socket = io(this.serverUrl, {
        transports: ["websocket", "polling"],
        reconnectionAttempts: 5,
        reconnectionDelay: 1000,
      });

      this.socket.on("connect", () => {
        this.connected = true;
        this._trigger("connect");
      });

      this.socket.on("disconnect", () => {
        this.connected = false;
        this._trigger("disconnect");
      });

      this.socket.on("document_state", (data) => this._trigger("document_state", data));
      this.socket.on("operation_ack", (data) => this._trigger("operation_ack", data));
      this.socket.on("remote_operation", (data) => this._trigger("remote_operation", data));
      this.socket.on("cursor_update", (data) => this._trigger("cursor_update", data));
      this.socket.on("typing_update", (data) => this._trigger("typing_update", data));
      this.socket.on("participant_joined", (data) => this._trigger("participant_joined", data));
      this.socket.on("participant_left", (data) => this._trigger("participant_left", data));
      this.socket.on("catch_up_response", (data) => this._trigger("catch_up_response", data));
      this.socket.on("operation_error", (data) => this._trigger("operation_error", data));
    } else {
      console.warn("Socket.IO client library not loaded. Running in local standalone mode.");
    }
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  _trigger(event, data) {
    const handlers = this.listeners.get(event) || [];
    for (const handler of handlers) {
      try {
        handler(data);
      } catch (err) {
        console.error(`Error in event listener for ${event}:`, err);
      }
    }
  }

  joinDocument(docId, userName, color) {
    if (this.socket && this.connected) {
      this.socket.emit("join_document", {
        doc_id: docId,
        user_name: userName,
        color: color,
      });
    }
  }

  leaveDocument(docId) {
    if (this.socket && this.connected) {
      this.socket.emit("leave_document", { doc_id: docId });
    }
  }

  sendOperation(docId, revision, operation, author) {
    if (this.socket && this.connected) {
      this.socket.emit("client_operation", {
        doc_id: docId,
        revision: revision,
        operation: operation.toDict(),
        author: author,
      });
    }
  }

  sendCursor(docId, cursorPos, selectionEnd = null) {
    if (this.socket && this.connected) {
      this.socket.emit("cursor_move", {
        doc_id: docId,
        cursor_pos: cursorPos,
        selection_end: selectionEnd,
      });
    }
  }

  sendTypingStatus(docId, isTyping) {
    if (this.socket && this.connected) {
      this.socket.emit("typing_status", {
        doc_id: docId,
        is_typing: isTyping,
      });
    }
  }

  sendHeartbeat(docId) {
    if (this.socket && this.connected) {
      this.socket.emit("heartbeat", { doc_id: docId });
    }
  }
}
