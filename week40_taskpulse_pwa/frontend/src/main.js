import { initHeader } from "./components/header.js";
import { initTaskGrid } from "./components/taskGrid.js";
import { initTaskModal } from "./components/taskModal.js";
import { showToast } from "./components/toast.js";
import { IdbManager } from "./storage/idbManager.js";
import { SyncQueue } from "./storage/syncQueue.js";
import { SwRegister } from "./swRegister.js";
import { getIcon } from "./utils/helpers.js";

/**
 * TaskPulse Application State
 */
const state = {
  isOnline: navigator.onLine,
  deferredInstallPrompt: null,
  activeFilter: "all",
  tasks: [],
};

// Initialize Header Component
const header = initHeader({
  onInstallClick: async (promptEvent) => {
    if (!promptEvent) return;
    promptEvent.prompt();
    const { outcome } = await promptEvent.userChoice;
    console.info(`[PWA] Install prompt outcome: ${outcome}`);
    header.hideInstallButton();
  },
});

// Initialize Task Modal Component
const taskModal = initTaskModal({
  onSaveTask: async (taskData) => {
    try {
      const savedTask = await IdbManager.saveTask(taskData);

      // If currently offline, buffer creation mutation to sync queue
      if (!state.isOnline) {
        await SyncQueue.enqueue("CREATE", savedTask.id, savedTask);
      }

      showToast("Task saved locally to IndexedDB", "success");
      await refreshTasks();
    } catch (err) {
      showToast("Failed to save task to local database.", "error");
    }
  },
});

// Initialize Task Grid Component
const taskGrid = initTaskGrid({
  onToggleTask: async (taskId) => {
    try {
      const updated = await IdbManager.toggleTaskCompleted(taskId);

      // If currently offline, buffer toggle mutation to sync queue
      if (!state.isOnline) {
        await SyncQueue.enqueue("TOGGLE", taskId, { completed: updated.completed });
      }

      showToast(
        updated.completed ? "Task marked completed" : "Task marked pending",
        "info"
      );
      await refreshTasks();
    } catch (err) {
      showToast("Could not update task status.", "error");
    }
  },
  onDeleteTask: async (taskId) => {
    try {
      await IdbManager.deleteTask(taskId);

      // If currently offline, buffer delete mutation to sync queue
      if (!state.isOnline) {
        await SyncQueue.enqueue("DELETE", taskId);
      }

      showToast("Task removed from local storage", "info");
      await refreshTasks();
    } catch (err) {
      showToast("Could not delete task.", "error");
    }
  },
});

/**
 * Reloads tasks from IndexedDB applying current active category filter.
 */
async function refreshTasks() {
  try {
    const tasks = await IdbManager.getAllTasks({
      category: state.activeFilter,
    });
    state.tasks = tasks;
    taskGrid.render(tasks);

    // Update Summary Stats & Quotas
    const stats = await IdbManager.getTaskStats();
    const pendingQueueCount = await SyncQueue.getPendingCount();

    const totalEl = document.getElementById("stat-total-tasks");
    const pendingEl = document.getElementById("stat-pending-tasks");
    const queueEl = document.getElementById("stat-sync-queue");

    if (totalEl) totalEl.textContent = stats.total;
    if (pendingEl) pendingEl.textContent = stats.pending;
    if (queueEl) queueEl.textContent = pendingQueueCount;

    // Refresh browser storage quota display
    const quota = await IdbManager.getStorageQuota();
    const quotaLabel = document.getElementById("stat-storage-quota");
    if (quotaLabel) {
      quotaLabel.textContent = `${quota.formattedUsage} used (${quota.percentUsed}%)`;
    }
  } catch (err) {
    console.error("[App] Failed to refresh tasks from IndexedDB:", err);
  }
}

/**
 * Updates offline warning banner in the sticky banner stack.
 */
function updateOfflineBanner(isOnline) {
  const bannerMount = document.getElementById("pwa-banner-mount");
  if (!bannerMount) return;

  const existingBanner = bannerMount.querySelector(".offline-banner");
  if (!isOnline) {
    if (!existingBanner) {
      const banner = document.createElement("div");
      banner.className = "offline-banner";
      banner.innerHTML = `
        ${getIcon("wifiOff", 14)}
        <span>Working Offline - All task changes saved to local IndexedDB</span>
      `;
      bannerMount.prepend(banner);
    }
  } else if (existingBanner) {
    existingBanner.remove();
  }
}

/**
 * Displays update prompt banner when a new Service Worker version is installed.
 */
function showUpdateNotification(newWorker) {
  const bannerMount = document.getElementById("pwa-banner-mount");
  if (!bannerMount) return;

  let updateBanner = bannerMount.querySelector(".update-banner");
  if (!updateBanner) {
    updateBanner = document.createElement("div");
    updateBanner.className = "update-banner";
    updateBanner.innerHTML = `
      <span>A new version of TaskPulse is ready to install.</span>
      <button type="button" class="btn-update" id="btn-apply-update">Update Now</button>
    `;
    bannerMount.appendChild(updateBanner);

    const btn = updateBanner.querySelector("#btn-apply-update");
    if (btn) {
      btn.addEventListener("click", () => {
        SwRegister.applyUpdate(newWorker);
        window.location.reload();
      });
    }
  }
}

/**
 * Renders the baseline workspace controls and summary card.
 */
function renderWorkspace() {
  const mainMount = document.getElementById("main-mount");
  if (!mainMount) return;

  mainMount.innerHTML = `
    <!-- Controls & Category Filters -->
    <section class="controls-bar">
      <div class="filter-group" id="filter-tabs">
        <button type="button" class="filter-btn ${state.activeFilter === "all" ? "active" : ""}" data-filter="all">All Tasks</button>
        <button type="button" class="filter-btn ${state.activeFilter === "work" ? "active" : ""}" data-filter="work">Work</button>
        <button type="button" class="filter-btn ${state.activeFilter === "personal" ? "active" : ""}" data-filter="personal">Personal</button>
        <button type="button" class="filter-btn ${state.activeFilter === "urgent" ? "active" : ""}" data-filter="urgent">Urgent</button>
      </div>
      <button type="button" id="btn-open-create" class="btn-add-task">
        ${getIcon("plus", 14)}
        <span>New Task</span>
      </button>
    </section>

    <!-- PWA Storage & System Health Summary -->
    <section class="status-card">
      <div class="status-stat-group">
        <div class="status-stat">
          <span class="status-stat-val" id="stat-total-tasks">0</span>
          <span class="status-stat-label">Total Tasks</span>
        </div>
        <div class="status-stat">
          <span class="status-stat-val" id="stat-pending-tasks">0</span>
          <span class="status-stat-label">Pending</span>
        </div>
        <div class="status-stat">
          <span class="status-stat-val" id="stat-sync-queue">0</span>
          <span class="status-stat-label">Offline Queue</span>
        </div>
      </div>
      <div class="network-status-badge ${state.isOnline ? "network-online" : "network-offline"}">
        ${getIcon("database", 14)}
        <span id="stat-storage-quota">IndexedDB Ready</span>
      </div>
    </section>

    <!-- Task Items List Mount -->
    <section id="tasks-mount" class="tasks-list"></section>
  `;

  // Bind Open Task Modal Button
  const openModalBtn = document.getElementById("btn-open-create");
  if (openModalBtn) {
    openModalBtn.addEventListener("click", () => {
      taskModal.open();
    });
  }

  // Bind Filter Tabs
  const filterTabs = document.querySelectorAll("#filter-tabs .filter-btn");
  filterTabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      filterTabs.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.activeFilter = btn.getAttribute("data-filter") || "all";
      refreshTasks();
    });
  });
}

/**
 * Application Bootstrap
 */
async function init() {
  // Render Header, Workspace, and Modal
  header.render(state.isOnline);
  renderWorkspace();
  taskModal.render();
  updateOfflineBanner(state.isOnline);

  // Initialize and Seed IndexedDB on First Run
  await IdbManager.seedInitialTasksIfEmpty();
  await refreshTasks();

  // Register Service Worker with Lifecycle Callbacks
  SwRegister.register({
    onInstalled: () => {
      console.info("[App] TaskPulse App Shell precached for offline use.");
    },
    onUpdated: (worker) => {
      showUpdateNotification(worker);
    },
    onOnline: () => {
      state.isOnline = true;
      header.updateNetworkStatus(true);
      updateOfflineBanner(true);
    },
    onOffline: () => {
      state.isOnline = false;
      header.updateNetworkStatus(false);
      updateOfflineBanner(false);
    },
  });

  // Listen for Native PWA Install Prompt
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    state.deferredInstallPrompt = e;
    header.setInstallPrompt(e);
  });

  // Track Successful PWA Installation
  window.addEventListener("appinstalled", () => {
    console.info("[PWA] TaskPulse successfully installed on device.");
    header.hideInstallButton();
  });
}

// Boot application when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
