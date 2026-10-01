import { IdbManager } from "../storage/idbManager.js";
import { SyncQueue } from "../storage/syncQueue.js";
import { escapeHtml, getIcon } from "../utils/helpers.js";
import { showToast } from "./toast.js";

/**
 * Storage Inspector Component
 * Inspects browser storage quota, IndexedDB records, and persistence status.
 */
export function initStorageInspector({ onDataChanged } = {}) {
  let modalMount = document.getElementById("storage-modal-mount");
  if (!modalMount) {
    modalMount = document.createElement("div");
    modalMount.id = "storage-modal-mount";
    document.body.appendChild(modalMount);
  }

  let isOpen = false;

  /**
   * Closes the storage inspector modal dialog.
   */
  function close() {
    isOpen = false;
    modalMount.innerHTML = "";
    document.body.classList.remove("modal-open");
  }

  /**
   * Opens the storage inspector and renders live storage metrics.
   */
  async function open() {
    isOpen = true;
    document.body.classList.add("modal-open");
    await renderContent();
  }

  /**
   * Fetches latest storage metrics and renders the modal DOM.
   */
  async function renderContent() {
    if (!isOpen) return;

    // Fetch storage quota
    let quotaInfo = {
      usage: 0,
      quota: 0,
      formattedUsage: "0 KB",
      formattedQuota: "Unknown",
      percentUsed: 0,
    };
    if (navigator.storage && navigator.storage.estimate) {
      try {
        const est = await navigator.storage.estimate();
        const usage = est.usage || 0;
        const quota = est.quota || 1;
        const usageMb = (usage / (1024 * 1024)).toFixed(2);
        const quotaGb = (quota / (1024 * 1024 * 1024)).toFixed(2);
        const percent = ((usage / quota) * 100).toFixed(2);

        quotaInfo = {
          usage,
          quota,
          formattedUsage: `${usageMb} MB`,
          formattedQuota: `${quotaGb} GB`,
          percentUsed: Math.max(0.1, parseFloat(percent)),
        };
      } catch (err) {
        console.warn("[Storage] Could not retrieve storage estimate:", err);
      }
    }

    // Check persistence status
    let isPersisted = false;
    if (navigator.storage && navigator.storage.persisted) {
      try {
        isPersisted = await navigator.storage.persisted();
      } catch (err) {
        console.warn("[Storage] Could not check persistence:", err);
      }
    }

    // Fetch database and queue stats
    const tasks = await IdbManager.getAllTasks();
    const completedTasks = tasks.filter((t) => t.completed);
    const pendingTasks = tasks.filter((t) => !t.completed);
    const queueCount = await SyncQueue.getPendingCount();

    modalMount.innerHTML = `
      <div class="modal-overlay" id="storage-overlay">
        <div class="modal-card storage-card" role="dialog" aria-modal="true" aria-labelledby="storage-modal-title">
          <header class="modal-header">
            <div class="storage-title-group">
              <span class="storage-icon-box">
                ${getIcon("database", 18)}
              </span>
              <h2 id="storage-modal-title" class="modal-title">Storage & Quota Inspector</h2>
            </div>
            <button type="button" class="btn-modal-close" id="btn-close-storage" aria-label="Close storage modal">
              ${getIcon("close", 16)}
            </button>
          </header>

          <div class="modal-body storage-body">
            <!-- Quota Meter Card -->
            <section class="storage-section">
              <div class="storage-section-header">
                <span class="storage-section-title">Disk Storage Quota</span>
                <span class="storage-quota-text">${escapeHtml(quotaInfo.formattedUsage)} / ${escapeHtml(quotaInfo.formattedQuota)} (${quotaInfo.percentUsed}%)</span>
              </div>
              <progress class="quota-meter-progress" value="${quotaInfo.percentUsed}" max="100"></progress>
              <p class="storage-hint">Managed automatically by browser storage manager.</p>
            </section>

            <!-- Persistence Status Card -->
            <section class="storage-section persistence-box">
              <div class="persistence-info">
                <span class="storage-section-title">Eviction Protection</span>
                <p class="persistence-desc">
                  ${
                    isPersisted
                      ? "Persistent Storage is GRANTED. The browser will not evict TaskPulse data under storage pressure."
                      : "Best-effort storage. The browser may evict local cache if your device runs critically low on disk space."
                  }
                </p>
              </div>
              <div class="persistence-action">
                ${
                  isPersisted
                    ? `<span class="badge-persisted">${getIcon("check", 14)} Persisted</span>`
                    : `<button type="button" class="btn-persist" id="btn-request-persist">Request Persistence</button>`
                }
              </div>
            </section>

            <!-- Storage Records Breakdown -->
            <section class="storage-section">
              <span class="storage-section-title">Local IndexedDB Breakdown</span>
              <div class="storage-stats-grid">
                <div class="storage-stat-tile">
                  <span class="storage-stat-num">${tasks.length}</span>
                  <span class="storage-stat-name">Total Tasks</span>
                </div>
                <div class="storage-stat-tile">
                  <span class="storage-stat-num">${pendingTasks.length}</span>
                  <span class="storage-stat-name">Pending</span>
                </div>
                <div class="storage-stat-tile">
                  <span class="storage-stat-num">${completedTasks.length}</span>
                  <span class="storage-stat-name">Completed</span>
                </div>
                <div class="storage-stat-tile">
                  <span class="storage-stat-num">${queueCount}</span>
                  <span class="storage-stat-name">Sync Queue Items</span>
                </div>
              </div>
            </section>

            <!-- Data Management Actions -->
            <section class="storage-section">
              <span class="storage-section-title">Maintenance & Backup</span>
              <div class="storage-actions-row">
                <button type="button" class="btn-storage-action" id="btn-export-backup">
                  ${getIcon("download", 14)}
                  <span>Export JSON Backup</span>
                </button>
                <button type="button" class="btn-storage-action" id="btn-purge-completed">
                  ${getIcon("trash", 14)}
                  <span>Purge Completed (${completedTasks.length})</span>
                </button>
                <button type="button" class="btn-storage-action btn-danger" id="btn-reset-db">
                  ${getIcon("alert", 14)}
                  <span>Reset All Data</span>
                </button>
              </div>
            </section>
          </div>
        </div>
      </div>
    `;

    bindEvents();
  }

  /**
   * Binds click handlers for all buttons in the storage inspector.
   */
  function bindEvents() {
    const overlay = modalMount.querySelector("#storage-overlay");
    const closeBtn = modalMount.querySelector("#btn-close-storage");

    if (overlay) {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) close();
      });
    }

    if (closeBtn) {
      closeBtn.addEventListener("click", close);
    }

    // Request Persistence
    const persistBtn = modalMount.querySelector("#btn-request-persist");
    if (persistBtn) {
      persistBtn.addEventListener("click", async () => {
        if (navigator.storage && navigator.storage.persist) {
          const granted = await navigator.storage.persist();
          if (granted) {
            showToast("Persistent storage granted by browser.", "success");
          } else {
            showToast("Persistent storage request declined by browser.", "info");
          }
          await renderContent();
        }
      });
    }

    // Export Backup JSON
    const exportBtn = modalMount.querySelector("#btn-export-backup");
    if (exportBtn) {
      exportBtn.addEventListener("click", async () => {
        const tasks = await IdbManager.getAllTasks();
        const exportData = {
          app: "TaskPulse PWA",
          version: "1.0.0",
          exported_at: new Date().toISOString(),
          tasks,
        };

        const jsonStr = JSON.stringify(exportData, null, 2);
        const blob = new Blob([jsonStr], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `taskpulse_backup_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast("Backup downloaded successfully.", "success");
      });
    }

    // Purge Completed Tasks
    const purgeBtn = modalMount.querySelector("#btn-purge-completed");
    if (purgeBtn) {
      purgeBtn.addEventListener("click", async () => {
        const tasks = await IdbManager.getAllTasks();
        const completed = tasks.filter((t) => t.completed);

        if (completed.length === 0) {
          showToast("No completed tasks to purge.", "info");
          return;
        }

        for (const task of completed) {
          await IdbManager.deleteTask(task.id);
          await SyncQueue.enqueue("DELETE", task.id);
        }

        showToast(`Purged ${completed.length} completed tasks.`, "info");
        if (typeof onDataChanged === "function") {
          onDataChanged();
        }
        await renderContent();
      });
    }

    // Reset All Data
    const resetBtn = modalMount.querySelector("#btn-reset-db");
    if (resetBtn) {
      resetBtn.addEventListener("click", async () => {
        const confirmed = window.confirm(
          "Are you sure you want to reset all local tasks and offline queue? This cannot be undone."
        );
        if (!confirmed) return;

        await IdbManager.clear();
        await SyncQueue.clear();
        await IdbManager.seedInitialTasksIfEmpty();

        showToast("Database reset to demo state.", "info");
        if (typeof onDataChanged === "function") {
          onDataChanged();
        }
        await renderContent();
      });
    }
  }

  return {
    open,
    close,
  };
}
