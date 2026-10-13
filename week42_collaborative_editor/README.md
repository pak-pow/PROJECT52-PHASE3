# Week 42: PulsePad - Real-Time Collaborative Editor

A production-grade, Google Docs-style real-time collaborative text editor built with an authoritative Operational Transformation (OT) synchronization engine, bidirectional WebSockets, multi-user presence, and point-in-time revision history.

---

## Architecture Overview

PulsePad ensures mathematical convergence across distributed clients using atomic operation primitives (`retain`, `insert`, `delete`), server-authoritative revision numbering, and dynamic presence tracking:

- **Operational Transformation Engine:** Client and server edits converge to identical document states regardless of network delays or interleaved operations.
- **Bidirectional WebSocket Protocol:** Low-latency Socket.IO room management with monotonic revision sequencing and automatic version drift catch-up.
- **Dynamic Presence & Remote Cursors:** Broadcasts remote caret offsets, text selection ranges, and distinct identity colors.
- **Persistence & Revisions:** SQLite WAL-mode transactional storage with debounced auto-save and timeline recovery.

---

## Project Structure

```
week42_collaborative_editor/
├── backend/
│   ├── app/
│   │   ├── config/          # Application configuration and environment variables
│   │   ├── db/              # SQLite connection and schema initializers
│   │   ├── engine/          # Operational Transformation (OT) engine algorithms
│   │   ├── models/          # Document and revision data models
│   │   ├── routes/          # REST endpoints for document management
│   │   ├── services/        # Business logic and persistence coordination
│   │   └── socket/          # Socket.IO handlers, room manager, and presence
│   ├── data/                # Database schema and seed scripts
│   ├── tests/               # Pytest suite with unit, socket, and convergence tests
│   └── run.py               # Server launcher
├── frontend/
│   ├── public/              # HTML workbench shell
│   └── src/
│       ├── assets/          # Dark/light theme design tokens and styles
│       ├── engine/          # Client-side OT state machine and cursor tracking
│       ├── socket/          # WebSocket client communication layer
│       └── ui/              # Presence bar, split-view simulator, and timeline
└── README.md
```

---

## 7-Day Implementation Plan

- **Day 1: Architecture Scaffolding and Directory Setup** (Completed)
- **Day 2: Operational Transformation (OT) Core Engine**
- **Day 3: Real-Time WebSocket Synchronization Protocol**
- **Day 4: Multi-User Presence, Awareness, and Remote Cursors**
- **Day 5: Collaborative Frontend Editor Workbench**
- **Day 6: Persistence, Revisions Timeline, and Auto-Save**
- **Day 7: E2E Integration Suite, Stress Testing, Quality Gates & Production Handover**

---

## Getting Started

### 1. Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python data/seed.py
python run.py
```

### 2. Run Test Suite
```bash
cd backend
pytest -v --cov=app
```
