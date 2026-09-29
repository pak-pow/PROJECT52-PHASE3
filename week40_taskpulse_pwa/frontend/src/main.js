import { initHeader } from "./components/header.js";
import { SwRegister } from "./swRegister.js";
import { getIcon } from "./utils/helpers.js";

/**
 * TaskPulse Application State
 */
const state = {
  isOnline: navigator.onLine,
  deferredInstallPrompt: null,
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
        <button type="button" class="filter-btn active" data-filter="all">All Tasks</button>
        <button type="button" class="filter-btn" data-filter="work">Work</button>
        <button type="button" class="filter-btn" data-filter="personal">Personal</button>
        <button type="button" class="filter-btn" data-filter="urgent">Urgent</button>
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
        <span>IndexedDB Ready</span>
      </div>
    </section>

    <!-- Task Items List Mount -->
    <section id="tasks-mount" class="tasks-list">
      <div class="empty-state">
        ${getIcon("check", 40)}
        <h3 class="empty-state-title">No tasks found</h3>
        <p>Get started by clicking New Task above. Everything works offline!</p>
      </div>
    </section>
  `;
}

/**
 * Application Bootstrap
 */
function init() {
  // Render Header & Baseline Workspace
  header.render(state.isOnline);
  renderWorkspace();
  updateOfflineBanner(state.isOnline);

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
