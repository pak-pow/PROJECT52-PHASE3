/**
 * PulsePad frontend main controller and event coordinator.
 */

import { ClientOT, createOperationFromDiff } from "./engine/client_ot.js";
import { CursorTracker } from "./engine/cursor_tracker.js";
import { SocketClient } from "./socket/socket_client.js";
import { PresenceView } from "./ui/presence_view.js";
import { SplitSimulator } from "./ui/split_simulator.js";
import { TimelineView } from "./ui/timeline_view.js";

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const editorArea = document.getElementById("primary-editor");
  const editorGutter = document.getElementById("primary-gutter");
  const cursorOverlay = document.getElementById("primary-cursor-overlay");
  const docTitleInput = document.getElementById("doc-title-input");
  const syncStatus = document.getElementById("sync-status");
  const presenceBar = document.getElementById("presence-bar");
  const toggleSplitBtn = document.getElementById("toggle-split-btn");
  const toggleTimelineBtn = document.getElementById("toggle-timeline-btn");
  const closeTimelineBtn = document.getElementById("close-timeline-btn");
  const timelineDrawer = document.getElementById("timeline-drawer");
  const timelineList = document.getElementById("timeline-list");
  const exportMdBtn = document.getElementById("export-md-btn");
  const exportTxtBtn = document.getElementById("export-txt-btn");
  const workbenchLayout = document.getElementById("workbench-layout");

  // Determine Document ID and Server URL
  const urlParams = new URLSearchParams(window.location.search);
  const docId = urlParams.get("doc") || "welcome-doc";
  const serverUrl = window.location.origin.includes("5000")
    ? window.location.origin
    : "http://127.0.0.1:5000";

  const userName = "Alice (Primary)";
  const userColor = "#3b82f6"; // Blue

  // Initialize Modules
  const socketClient = new SocketClient(serverUrl);
  const otClient = new ClientOT(0);
  const cursorTracker = new CursorTracker(cursorOverlay, editorArea);
  const presenceView = new PresenceView(presenceBar);
  const splitSimulator = new SplitSimulator(workbenchLayout, docId, serverUrl);
  const timelineView = new TimelineView({
    drawerElement: timelineDrawer,
    listElement: timelineList,
    docId: docId,
    serverUrl: serverUrl,
    onRollback: (result) => {
      setStatus("Rolled back", "synced");
      if (result && result.content !== undefined) {
        isApplyingRemote = true;
        editorArea.value = result.content;
        previousText = result.content;
        isApplyingRemote = false;
        otClient.reset(result.version);
        updateGutter();
      }
    },
  });

  let previousText = "";
  let isApplyingRemote = false;
  let typingTimer = null;


  function setStatus(text, className) {
    if (!syncStatus) return;
    syncStatus.textContent = text;
    syncStatus.className = `status-badge ${className}`;
  }

  function updateGutter() {
    if (!editorGutter || !editorArea) return;
    const lines = editorArea.value.split("\n").length;
    let numbers = "";
    for (let i = 1; i <= lines; i++) {
      numbers += `${i}\n`;
    }
    editorGutter.textContent = numbers;
  }

  // Socket.IO Event Handlers
  socketClient.on("connect", () => {
    setStatus("Synced", "synced");
    socketClient.joinDocument(docId, userName, userColor);
  });

  socketClient.on("disconnect", () => {
    setStatus("Offline", "");
  });

  socketClient.on("document_state", (state) => {
    otClient.reset(state.version);
    isApplyingRemote = true;
    editorArea.value = state.content;
    previousText = state.content;
    isApplyingRemote = false;

    if (docTitleInput && state.title) {
      docTitleInput.value = state.title;
    }
    updateGutter();
    presenceView.setParticipants(state.participants || []);
    setStatus("Synced", "synced");
  });

  socketClient.on("operation_ack", (data) => {
    const nextSend = otClient.serverAck(data.revision);
    if (nextSend) {
      setStatus("Syncing...", "");
      socketClient.sendOperation(docId, nextSend.revision, nextSend.send, userName);
    } else {
      setStatus("Synced", "synced");
    }

    if (timelineView.isOpen()) {
      timelineView.fetchRevisions();
    }
  });

  socketClient.on("remote_operation", (data) => {
    if (data.author === userName) return;

    const remoteOp = {
      components: data.operation.components,
      baseLength: data.operation.base_length,
      targetLength: data.operation.target_length,
    };

    const result = otClient.applyServer(remoteOp);
    if (result && result.applyToDoc) {
      isApplyingRemote = true;
      const currentPos = editorArea.selectionStart;
      const currentEnd = editorArea.selectionEnd;

      editorArea.value = result.applyToDoc.apply(editorArea.value);
      previousText = editorArea.value;

      // Transform local cursor offset
      const [newStart, newEnd] = cursorTracker.transformSelection(
        currentPos,
        currentEnd,
        result.applyToDoc
      );
      editorArea.setSelectionRange(newStart, newEnd);
      isApplyingRemote = false;

      // Transform all remote cursors
      cursorTracker.transformAll(result.applyToDoc);
      updateGutter();

      if (timelineView.isOpen()) {
        timelineView.fetchRevisions();
      }
    }
  });

  socketClient.on("cursor_update", (data) => {
    if (data.user_name === userName) return;
    cursorTracker.updateRemoteCursor(data.sid, data);
  });

  socketClient.on("typing_update", (data) => {
    presenceView.setTyping(data.sid, data.is_typing);
    cursorTracker.updateRemoteCursor(data.sid, { is_typing: data.is_typing });
  });

  socketClient.on("participant_joined", (participant) => {
    presenceView.addOrUpdateParticipant(participant);
  });

  socketClient.on("participant_left", (data) => {
    presenceView.removeParticipant(data.sid);
    cursorTracker.removeRemoteCursor(data.sid);
  });

  // Editor Input and Typing Handling
  editorArea.addEventListener("input", () => {
    if (isApplyingRemote) return;

    const currentText = editorArea.value;
    const op = createOperationFromDiff(previousText, currentText);
    previousText = currentText;

    const action = otClient.applyClient(op);
    if (action && action.send) {
      setStatus("Syncing...", "");
      socketClient.sendOperation(docId, action.revision, action.send, userName);
    }

    updateGutter();
    socketClient.sendCursor(docId, editorArea.selectionStart, editorArea.selectionEnd);

    // Typing status throttle
    socketClient.sendTypingStatus(docId, true);
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => {
      socketClient.sendTypingStatus(docId, false);
    }, 1200);
  });

  // Local Cursor Movement
  const sendCursor = () => {
    socketClient.sendCursor(docId, editorArea.selectionStart, editorArea.selectionEnd);
  };

  editorArea.addEventListener("click", sendCursor);
  editorArea.addEventListener("keyup", sendCursor);

  editorArea.addEventListener("scroll", () => {
    cursorTracker.render();
    if (editorGutter) {
      editorGutter.scrollTop = editorArea.scrollTop;
    }
  });

  // Split View Simulator Toggle
  if (toggleSplitBtn) {
    toggleSplitBtn.addEventListener("click", () => {
      const active = splitSimulator.toggle();
      toggleSplitBtn.textContent = active ? "Close Split" : "Split View";
      toggleSplitBtn.className = active ? "btn btn-primary active" : "btn btn-secondary";
    });
  }

  // Timeline Drawer Toggle & Actions
  if (toggleTimelineBtn) {
    toggleTimelineBtn.addEventListener("click", () => {
      const opened = timelineView.toggle();
      toggleTimelineBtn.className = opened ? "btn btn-primary active" : "btn btn-secondary";
    });
  }

  if (closeTimelineBtn) {
    closeTimelineBtn.addEventListener("click", () => {
      timelineView.close();
      if (toggleTimelineBtn) {
        toggleTimelineBtn.className = "btn btn-secondary";
      }
    });
  }

  if (exportMdBtn) {
    exportMdBtn.addEventListener("click", () => {
      timelineView.exportDocument("markdown");
    });
  }

  if (exportTxtBtn) {
    exportTxtBtn.addEventListener("click", () => {
      timelineView.exportDocument("txt");
    });
  }

  // Connect to backend
  socketClient.connect();
});
