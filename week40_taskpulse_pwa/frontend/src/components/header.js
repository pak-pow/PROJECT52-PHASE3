import { getIcon } from "../utils/helpers.js";

/**
 * Header Component with Live Network Status Beacon and PWA Install Prompt
 */
export function initHeader({ onInstallClick } = {}) {
  const mount = document.getElementById("header-mount");
  let installPromptEvent = null;

  function render(isOnline = navigator.onLine) {
    if (!mount) return;

    mount.innerHTML = `
      <div class="header-inner">
        <div class="brand-group">
          <div class="brand-icon-box" aria-hidden="true">
            ${getIcon("check", 22)}
          </div>
          <div class="brand-text">
            <span class="brand-name">TaskPulse</span>
            <span class="brand-tagline">Offline PWA</span>
          </div>
        </div>

        <div class="header-actions">
          <!-- Live Network Status Beacon -->
          <div id="network-badge" class="network-status-badge ${isOnline ? "network-online" : "network-offline"}">
            <span class="status-dot"></span>
            <span id="network-text">${isOnline ? "Online" : "Offline"}</span>
          </div>

          <!-- Install PWA Button (Hidden by default until prompt is ready) -->
          <button type="button" id="btn-pwa-install" class="btn-install hidden" aria-label="Install TaskPulse App">
            ${getIcon("download", 14)}
            <span>Install</span>
          </button>
        </div>
      </div>
    `;

    const installBtn = mount.querySelector("#btn-pwa-install");
    if (installBtn) {
      installBtn.addEventListener("click", async () => {
        if (typeof onInstallClick === "function") {
          onInstallClick(installPromptEvent);
        }
      });
    }
  }

  function updateNetworkStatus(isOnline) {
    const badge = document.getElementById("network-badge");
    const text = document.getElementById("network-text");
    if (badge && text) {
      badge.className = `network-status-badge ${isOnline ? "network-online" : "network-offline"}`;
      text.textContent = isOnline ? "Online" : "Offline";
    }
  }

  function setInstallPrompt(event) {
    installPromptEvent = event;
    const installBtn = document.getElementById("btn-pwa-install");
    if (installBtn && event) {
      installBtn.classList.remove("hidden");
    }
  }

  function hideInstallButton() {
    installPromptEvent = null;
    const installBtn = document.getElementById("btn-pwa-install");
    if (installBtn) {
      installBtn.classList.add("hidden");
    }
  }

  return {
    render,
    updateNetworkStatus,
    setInstallPrompt,
    hideInstallButton,
  };
}
