# Week 40: TaskPulse PWA - Offline-First Task Management

> Production-grade Progressive Web App (PWA) featuring offline-first client architecture, zero-dependency IndexedDB transactional persistence, background mutation sync queue, storage quota inspector, installability promotion, and native Web Notifications with App Badging.

---

## Architecture Overview

TaskPulse decouples user interface operations from network availability. Every user action (task creation, status toggle, categorization, deletion) executes locally against IndexedDB in under 5 milliseconds with zero UI latency.

```
week40_taskpulse_pwa/
├── backend/
│   ├── app/
│   │   ├── config/settings.py      # App configurations & test overrides
│   │   ├── models/task_model.py    # SQLite CRUD with LWW batch sync & delta query
│   │   ├── routes/health_routes.py # /api/health and /api/version
│   │   ├── routes/sync_routes.py   # /api/sync/batch and /api/sync/delta
│   │   ├── routes/task_routes.py   # RESTful task endpoints
│   │   ├── __init__.py             # Flask application factory with CORS
│   │   └── db.py                   # SQLite connection lifecycle & schema setup
│   ├── data/
│   │   ├── schema.sql              # Database schema with sync indexes
│   │   └── seed.py                 # Initial demo tasks seeder
│   ├── scripts/
│   │   └── run_quality_checks.py   # 5-gate quality runner (Flake8, Black, isort, Bandit, Pytest)
│   ├── tests/                      # 14 Pytest test cases (95.93% coverage)
│   ├── requirements.txt
│   └── run.py                      # Flask server entrypoint (:5000)
└── frontend/
    ├── public/
    │   ├── icon.svg                # Vector app icon (standard & maskable)
    │   ├── index.html              # PWA App Shell mount
    │   ├── manifest.json           # Web App Manifest with shortcuts
    │   ├── offline.html            # Custom branded offline fallback page
    │   └── sw.js                   # Service Worker (precache v3, fetch routing, sync, push)
    └── src/
        ├── api/taskApi.js          # REST client with batch sync & delta polling
        ├── assets/
        │   ├── app.css             # Component styling (zero inline styles)
        │   └── base.css            # Design tokens, variables & typography
        ├── components/
        │   ├── header.js           # Header with network beacon & alerts toggle
        │   ├── storageInspector.js # Quota meter, persistence manager, JSON backup
        │   ├── taskGrid.js         # Interactive task cards with filter tabs
        │   ├── taskModal.js        # Dialog for task creation
        │   └── toast.js            # Transient feedback alerts
        ├── storage/
        │   ├── idbManager.js       # Zero-dependency Promise wrapper for IndexedDB
        │   └── syncQueue.js        # FIFO mutation replay engine with LWW resolution
        ├── utils/
        │   ├── helpers.js          # XSS escaping, date formatters, SVG icons
        │   └── notifications.js    # Notification API & App Badging API manager
        ├── main.js                 # PWA orchestrator & state manager
        └── swRegister.js           # Service Worker lifecycle coordinator
```

---

## Core PWA Features

1. **Service Worker Lifecycle & Caching (`sw.js`):**
   - **Static Cache (App Shell):** Pre-caches core HTML, CSS, JavaScript, and SVG assets for instant loading.
   - **Navigation Requests:** Network-first with automatic fallback to pre-cached `index.html` or custom `offline.html`.
   - **API Requests:** Network-first with runtime cache fallback.
   - **Asset Requests:** Cache-first with network fallback.

2. **Client-Side Transactional Storage (`idbManager.js`):**
   - Database `taskpulse_db` with dedicated `tasks` and `sync_queue` object stores.
   - Multi-field indexes on `category`, `completed`, `priority`, and `updated_at`.
   - Native storage quota inspection via `navigator.storage.estimate()`.

3. **Offline Mutation Queue & Replay Engine (`syncQueue.js`):**
   - Buffers offline user actions (`CREATE`, `UPDATE`, `DELETE`, `TOGGLE`) into IndexedDB.
   - Flushes queued mutations in chronological batches to `/api/sync/batch` upon reconnection.
   - Reconciles server changes using Last-Write-Wins (LWW) conflict resolution and delta queries (`/api/sync/delta`).

4. **Storage & Quota Inspector (`storageInspector.js`):**
   - Real-time disk storage progress meter displaying MB used vs. total GB browser quota.
   - Eviction protection management via `navigator.storage.persist()`.
   - One-click timestamped JSON backup export and database maintenance tools.

5. **PWA Installability & App Shortcuts:**
   - Standalone display mode with custom theme color (`#4f46e5`).
   - Intercepts `beforeinstallprompt` with a custom promotion banner and header install button.
   - Fast action shortcuts: `#new` (Create Task) and `#storage` (Storage Inspector).

6. **Web Notifications & Native App Badging (`notifications.js`):**
   - Native system tray / lock screen notifications for urgent tasks and sync status.
   - `notificationclick` handler focusing the active application window.
   - Native App Badging API (`navigator.setAppBadge`) keeping the unread badge synced with pending tasks.

---

## Running Quality Gates

From the `backend/` directory:

```bash
python scripts/run_quality_checks.py
```

### Quality Gate Results:
- **Flake8 Linter:** PASS (max line length: 88)
- **Black Formatter:** PASS
- **isort Import Sorter:** PASS
- **Bandit Security Audit:** PASS (no high/medium vulnerabilities)
- **Pytest Suite:** 14/14 passed with **95.93% coverage**

---

## Getting Started

### 1. Start Backend API
```bash
cd backend
python run.py
# Server running at http://127.0.0.1:5000
```

### 2. Start Frontend Server
```bash
cd frontend
python -m http.server 8080
# PWA available at http://localhost:8080/public/
```
