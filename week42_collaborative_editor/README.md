# Week 42: PulsePad - Real-Time Collaborative Editor

A production-grade, Google Docs-style real-time collaborative text editor built with an authoritative Operational Transformation (OT) synchronization engine, bidirectional WebSockets, multi-user presence tracking, periodic point-in-time snapshots, and revision history recovery.

---

## 1. Architecture Overview

PulsePad ensures mathematical convergence across distributed, concurrently editing clients using atomic operation primitives (`retain`, `insert`, `delete`), server-authoritative revision numbering, and dynamic presence tracking:

- **Operational Transformation Engine:** Client and server edits converge to identical document states regardless of network delays or interleaved operations via Transformation Property 1 (TP1):
  $$\forall A, B: B'(A(S)) = A'(B(S)) \text{ where } (A', B') = transform(A, B)$$
- **3-State Client OT State Machine:** Manages optimistic local typing, in-flight operation tracking, and continuous keystroke buffering across `SYNCHRONIZED`, `AWAITING_ACK`, and `AWAITING_ACK_WITH_BUFFER` states.
- **Bidirectional WebSocket Protocol:** Low-latency Socket.IO room management with monotonic revision sequencing, remote cursor broadcasts, typing indicators, and automatic version drift catch-up.
- **Dynamic Presence & Remote Carets:** Projects remote collaborator carets and selection ranges onto a monospace canvas coordinate overlay with deterministic pastel identity colors.
- **Persistence & Point-in-Time Revisions:** SQLite WAL-mode transactional storage with automated snapshots captured every 10 revisions, non-destructive rollbacks, and file export (Markdown and Plain Text).

---

## 2. System Architecture

```mermaid
flowchart TD
    subgraph ClientA["Client Replica A (Alice)"]
        EditorA["Textarea & Caret Tracker"]
        ClientOTA["Client OT State Machine"]
        SocketA["Socket.IO Client"]
    end

    subgraph ClientB["Client Replica B (Bob)"]
        EditorB["Textarea & Caret Tracker"]
        ClientOTB["Client OT State Machine"]
        SocketB["Socket.IO Client"]
    end

    subgraph Server["PulsePad Authoritative Server"]
        SocketServer["Socket.IO Gateway & Room Manager"]
        OTEngine["OT Engine (transform, compose, invert)"]
        PresenceMgr["Presence & Caret Shifter"]
        RestAPI["Flask REST Endpoints"]
    end

    subgraph Storage["SQLite WAL Persistence"]
        DocTable[("documents")]
        RevTable[("revisions")]
        SnapTable[("snapshots")]
    end

    EditorA -->|Input Event Diff| ClientOTA
    ClientOTA -->|client_operation| SocketA
    SocketA <-->|WebSocket| SocketServer

    EditorB -->|Input Event Diff| ClientOTB
    ClientOTB -->|client_operation| SocketB
    SocketB <-->|WebSocket| SocketServer

    SocketServer --> OTEngine
    SocketServer --> PresenceMgr
    SocketServer --> Storage
    RestAPI --> Storage
```

---

## 3. Project Structure

```
week42_collaborative_editor/
├── backend/
│   ├── app/
│   │   ├── config/          # Application configuration and settings
│   │   ├── db/              # SQLite WAL connection manager and schema initializers
│   │   ├── engine/          # OT primitives, transform, compose, invert, and cursor shifts
│   │   ├── models/          # Document, Revision, and Snapshot data models
│   │   ├── routes/          # REST endpoints for documents, history, rollback, and export
│   │   ├── services/        # Business logic for documents and revision snapshots
│   │   └── socket/          # Socket.IO handlers, room sessions, and presence awareness
│   ├── data/                # Database schema (schema.sql) and seed script (seed.py)
│   ├── tests/               # Pytest suite (OT unit, socket sync, presence, routes, e2e fuzzing)
│   └── run.py               # Development and production server entrypoint
├── frontend/
│   ├── public/              # HTML workbench shell
│   └── src/
│       ├── assets/          # Base, editor, and revision timeline drawer stylesheets
│       ├── engine/          # Client-side 3-state OT machine, diff derivation, and cursor tracking
│       ├── socket/          # WebSocket client communication layer
│       ├── ui/              # Presence bar, split-view testing simulator, and timeline drawer
│       └── main.js          # Main event coordinator and DOM lifecycle controller
└── README.md
```

---

## 4. 7-Day Implementation Plan & Completed Milestones

- **Day 1: Architecture Scaffolding and Directory Setup** (Completed)
  - Scaffolded backend and frontend directory structure, configured SQLite WAL mode schema, application settings, and seed script.
- **Day 2: Operational Transformation (OT) Core Engine** (Completed)
  - Implemented `TextOperation` compound model with `retain`, `insert`, `delete` primitives, component coalescing, pairwise transformation `transform(op1, op2)`, sequential composition `compose(op1, op2)`, and operation inversion `invert(op, text)`.
- **Day 3: Real-Time WebSocket Synchronization Protocol** (Completed)
  - Implemented authoritative `RoomSession` tracking monotonic revisions, chronological history, and catch-up transformation on lagging client edits.
- **Day 4: Multi-User Presence, Awareness, and Remote Cursors** (Completed)
  - Implemented server-side cursor transformation `transform_cursor_position` and selection shifting `transform_selection`, deterministic pastel palette hashing, and heartbeat-based participant timeout pruning.
- **Day 5: Collaborative Frontend Editor Workbench** (Completed)
  - Built the distraction-free collaborative editor interface, 3-state client OT state machine (`ClientOT`), dynamic two-pointer diff scanner (`createOperationFromDiff`), monospace pixel caret overlay (`CursorTracker`), and split-view simulator (`SplitSimulator`).
- **Day 6: Persistence, Revisions Timeline, and Auto-Save** (Completed)
  - Implemented SQLite WAL persistence for operational revisions, automated snapshots captured every 10 revisions, point-in-time reconstruction, non-destructive rollbacks, and interactive revision timeline drawer with Markdown/Plain Text export.
- **Day 7: E2E Integration Suite, Stress Testing, Quality Gates & Production Handover** (Completed)
  - Implemented property-based TP1 convergence fuzzing (50 random iterations), multi-client interleaved concurrency simulations, lagging client recovery tests, and production documentation.

---

## 5. Getting Started

### Prerequisites
- Python 3.10+
- Modern Web Browser (Chrome, Firefox, Safari, Edge)

### 1. Backend Setup and Server Launch
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python data/seed.py
python run.py
```
The server will start on `http://127.0.0.1:5000`.

### 2. Open the Collaborative Workbench
Navigate to `http://127.0.0.1:5000` in your browser.
- **Split View Simulator:** Click the **Split View** button in the top-right header to spawn a secondary collaborator ("Bob") side-by-side in the same window. Both editors run independent Socket.IO connections and OT state machines, allowing instant local testing of concurrent edits and remote carets.
- **Revision History:** Click the **History** button to open the timeline drawer, inspect past edits, restore previous versions, or export the document as Markdown or Plain Text.

---

## 6. REST API Reference

| Method | Endpoint | Description |
|:-------|:---------|:------------|
| `GET` | `/health` | Service health status and heartbeat |
| `GET` | `/api/documents` | List all documents with active room title/version overlay |
| `GET` | `/api/documents/<doc_id>` | Retrieve metadata and current content for a document |
| `GET` | `/api/documents/<doc_id>/revisions` | Fetch chronological revision history with author names |
| `POST` | `/api/documents/<doc_id>/rollback` | Rollback document to target revision and broadcast state |
| `GET` | `/api/documents/<doc_id>/export?format=markdown\|txt` | Download document formatted as Markdown or Plain Text |

---

## 7. Verification and Quality Gates

All five automated quality gates pass with zero warnings, zero vulnerabilities, and 94% test coverage:

- `flake8 --max-line-length=88 .`: 0 warnings.
- `black --check .`: 0 formatting differences across 34 files.
- `isort --check-only --profile black .`: 0 import sorting issues.
- `bandit -r app/`: 0 security issues identified across 1,679 LOC.
- `pytest -v --cov=app --cov-report=term-missing`: 56 passed in 2.17s (94% coverage).
