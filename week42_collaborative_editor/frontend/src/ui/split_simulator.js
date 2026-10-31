/**
 * Built-in dual-editor simulator for testing real-time multi-user collaboration in a single window.
 */

import { ClientOT, TextOperation, createOperationFromDiff } from "../engine/client_ot.js";
import { CursorTracker } from "../engine/cursor_tracker.js";
import { SocketClient } from "../socket/socket_client.js";

export class SplitSimulator {
  constructor(containerElement, primaryDocId, serverUrl) {
    this.container = containerElement;
    this.docId = primaryDocId;
    this.serverUrl = serverUrl;
    this.isActive = false;

    this.simulatedPane = null;
    this.simulatedTextarea = null;
    this.simulatedGutter = null;
    this.simulatedOverlay = null;

    this.socketClient = null;
    this.otClient = null;
    this.cursorTracker = null;
    this.userName = "Bob (Collaborator 2)";
    this.userColor = "#ec4899"; // Pink
    this.isApplyingRemote = false;
    this.previousText = "";
  }

  toggle() {
    if (this.isActive) {
      this.destroy();
    } else {
      this.init();
    }
    return this.isActive;
  }

  init() {
    if (this.isActive) return;
    this.isActive = true;

    // Create simulator DOM elements
    this.simulatedPane = document.createElement("div");
    this.simulatedPane.className = "editor-pane simulated-pane";
    this.simulatedPane.id = "simulated-pane";

    this.simulatedPane.innerHTML = `
      <div class="pane-header">
        <span class="user-pill" style="background-color: ${this.userColor}">Bob</span>
        <span class="pane-label">Collaborator 2 (Simulated)</span>
        <span class="status-badge" id="sim-sync-status">Connecting...</span>
      </div>
      <div class="pane-body">
        <div class="editor-gutter" id="simulated-gutter">1</div>
        <div class="editor-container">
          <div class="cursor-overlay" id="simulated-cursor-overlay"></div>
          <textarea id="simulated-editor" class="editor-area" spellcheck="false" placeholder="Type as Collaborator 2..."></textarea>
        </div>
      </div>
    `;

    this.container.appendChild(this.simulatedPane);

    this.simulatedTextarea = this.simulatedPane.querySelector("#simulated-editor");
    this.simulatedGutter = this.simulatedPane.querySelector("#simulated-gutter");
    this.simulatedOverlay = this.simulatedPane.querySelector("#simulated-cursor-overlay");

    // Initialize OT and Socket client for simulated user
    this.otClient = new ClientOT(0);
    this.cursorTracker = new CursorTracker(this.simulatedOverlay, this.simulatedTextarea);
    this.socketClient = new SocketClient(this.serverUrl);

    this._bindEvents();
    this.socketClient.connect();
    this.socketClient.joinDocument(this.docId, this.userName, this.userColor);
  }

  _setSimStatus(text, className) {
    const statusEl = this.simulatedPane ? this.simulatedPane.querySelector("#sim-sync-status") : null;
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.className = `status-badge ${className}`;
    }
  }

  _bindEvents() {
    // Socket connection events
    this.socketClient.on("connect", () => {
      this._setSimStatus("Synced", "synced");
      this.socketClient.joinDocument(this.docId, this.userName, this.userColor);
    });

    this.socketClient.on("disconnect", () => {
      this._setSimStatus("Offline", "");
    });

    // Socket document state & sync events
    this.socketClient.on("document_state", (state) => {
      this.otClient.reset(state.version);
      this.isApplyingRemote = true;
      this.simulatedTextarea.value = state.content;
      this.previousText = state.content;
      this.isApplyingRemote = false;
      this._updateGutter();
      this._setSimStatus("Synced", "synced");
    });

    this.socketClient.on("operation_ack", (data) => {
      const nextSend = this.otClient.serverAck(data.revision);
      if (nextSend) {
        this._setSimStatus("Syncing...", "");
        this.socketClient.sendOperation(
          this.docId,
          nextSend.revision,
          nextSend.send,
          this.userName
        );
      } else {
        this._setSimStatus("Synced", "synced");
      }
    });

    this.socketClient.on("remote_operation", (data) => {
      if (data.author === this.userName) return;

      try {
        const remoteOp = TextOperation.fromDict(data.operation);
        const result = this.otClient.applyServer(remoteOp);
        if (result && result.applyToDoc) {
          this.isApplyingRemote = true;
          try {
            const currentPos = this.simulatedTextarea.selectionStart;
            const currentEnd = this.simulatedTextarea.selectionEnd;

            this.simulatedTextarea.value = result.applyToDoc.apply(this.simulatedTextarea.value);
            this.previousText = this.simulatedTextarea.value;

            // Shift local cursor
            const [newStart, newEnd] = this.cursorTracker.transformSelection(
              currentPos,
              currentEnd,
              result.applyToDoc
            );
            this.simulatedTextarea.setSelectionRange(newStart, newEnd);

            this.cursorTracker.transformAll(result.applyToDoc);
            this._updateGutter();
          } finally {
            this.isApplyingRemote = false;
          }
        }
      } catch (err) {
        console.warn("Simulated user error applying remote operation, resyncing:", err);
        this.socketClient.joinDocument(this.docId, this.userName, this.userColor);
      }
    });

    this.socketClient.on("operation_error", (data) => {
      console.warn("Simulated user operation error, resyncing:", data);
      this.socketClient.joinDocument(this.docId, this.userName, this.userColor);
    });

    this.socketClient.on("cursor_update", (data) => {
      if (data.user_name === this.userName) return;
      this.cursorTracker.updateRemoteCursor(data.sid, data);
    });

    this.socketClient.on("participant_left", (data) => {
      this.cursorTracker.removeRemoteCursor(data.sid);
    });

    // Local textarea edits
    this.simulatedTextarea.addEventListener("input", () => {
      if (this.isApplyingRemote) return;

      const currentText = this.simulatedTextarea.value;
      const op = createOperationFromDiff(this.previousText, currentText);
      this.previousText = currentText;

      const action = this.otClient.applyClient(op);
      if (action && action.send) {
        this._setSimStatus("Syncing...", "");
        this.socketClient.sendOperation(
          this.docId,
          action.revision,
          action.send,
          this.userName
        );
      }

      this._updateGutter();
      this.socketClient.sendCursor(
        this.docId,
        this.simulatedTextarea.selectionStart,
        this.simulatedTextarea.selectionEnd
      );
    });

    // Cursor move & selection
    this.simulatedTextarea.addEventListener("keyup", () => {
      this.socketClient.sendCursor(
        this.docId,
        this.simulatedTextarea.selectionStart,
        this.simulatedTextarea.selectionEnd
      );
    });

    this.simulatedTextarea.addEventListener("click", () => {
      this.socketClient.sendCursor(
        this.docId,
        this.simulatedTextarea.selectionStart,
        this.simulatedTextarea.selectionEnd
      );
    });

    this.simulatedTextarea.addEventListener("scroll", () => {
      this.cursorTracker.render();
      if (this.simulatedGutter) {
        this.simulatedGutter.scrollTop = this.simulatedTextarea.scrollTop;
      }
    });
  }

  _updateGutter() {
    if (!this.simulatedGutter || !this.simulatedTextarea) return;
    const lines = this.simulatedTextarea.value.split("\n").length;
    let numbers = "";
    for (let i = 1; i <= lines; i++) {
      numbers += `${i}\n`;
    }
    this.simulatedGutter.textContent = numbers;
  }

  destroy() {
    if (!this.isActive) return;
    this.isActive = false;

    if (this.socketClient) {
      this.socketClient.leaveDocument(this.docId);
      if (this.socketClient.socket) {
        this.socketClient.socket.disconnect();
      }
    }

    if (this.simulatedPane && this.simulatedPane.parentNode) {
      this.simulatedPane.parentNode.removeChild(this.simulatedPane);
    }

    this.simulatedPane = null;
    this.simulatedTextarea = null;
    this.simulatedGutter = null;
    this.simulatedOverlay = null;
    this.previousText = "";
  }
}
