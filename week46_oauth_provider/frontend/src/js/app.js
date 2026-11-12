/**
 * PulseAuth Master Frontend Application Controller
 * Strict Zero-Emoji Compliant
 */

import { initPlayground } from "./sandbox_playground.js";
import { initClientPortal } from "./client_portal.js";
import { initUserManager } from "./user_manager.js";
import { initMetadataViewer } from "./metadata_viewer.js";

// Global Toast System
export function showToast(message, type = "info", duration = 3500) {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;

    const textSpan = document.createElement("span");
    textSpan.textContent = message;

    const closeBtn = document.createElement("button");
    closeBtn.className = "btn-sm btn-secondary";
    closeBtn.textContent = "[X]";
    closeBtn.style.padding = "0.1rem 0.4rem";
    closeBtn.style.fontSize = "0.7rem";
    closeBtn.onclick = () => toast.remove();

    toast.appendChild(textSpan);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(8px)";
        toast.style.transition = "all 0.25s ease-out";
        setTimeout(() => toast.remove(), 250);
    }, duration);
}

// Global Copy Helper
export function copyToClipboard(text, successMsg = "Copied to clipboard.") {
    if (!text) {
        showToast("Nothing to copy.", "error");
        return;
    }
    navigator.clipboard.writeText(text).then(() => {
        showToast(`[OK] ${successMsg}`, "success");
    }).catch(() => {
        showToast("Failed to copy to clipboard.", "error");
    });
}

// Navigation & Tab Switching
function initTabNavigation() {
    const navTabs = document.querySelectorAll(".nav-tab");
    const tabPanels = document.querySelectorAll(".tab-panel");

    function activateTab(tabId) {
        navTabs.forEach(tab => {
            const isActive = tab.getAttribute("data-tab") === tabId;
            tab.classList.toggle("active", isActive);
        });

        tabPanels.forEach(panel => {
            const isActive = panel.id === `tab-${tabId}`;
            panel.classList.toggle("active", isActive);
        });

        window.location.hash = tabId;
    }

    navTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const target = tab.getAttribute("data-tab");
            activateTab(target);
        });
    });

    // Hash-based deep linking
    const initialHash = window.location.hash.replace("#", "");
    if (initialHash && document.getElementById(`tab-${initialHash}`)) {
        activateTab(initialHash);
    } else {
        activateTab("playground");
    }

    window.addEventListener("hashchange", () => {
        const hash = window.location.hash.replace("#", "");
        if (hash && document.getElementById(`tab-${hash}`)) {
            activateTab(hash);
        }
    });
}

// Theme Management
function initThemeToggle() {
    const themeBtn = document.getElementById("theme-toggle-btn");
    const currentTheme = localStorage.getItem("pulseauth_theme") || "dark";
    document.documentElement.setAttribute("data-theme", currentTheme);
    if (themeBtn) {
        themeBtn.textContent = currentTheme === "dark" ? "[LIGHT MODE]" : "[DARK MODE]";
        themeBtn.addEventListener("click", () => {
            const now = document.documentElement.getAttribute("data-theme");
            const next = now === "dark" ? "light" : "dark";
            document.documentElement.setAttribute("data-theme", next);
            localStorage.setItem("pulseauth_theme", next);
            themeBtn.textContent = next === "dark" ? "[LIGHT MODE]" : "[DARK MODE]";
        });
    }
}

// Backend Health Ping
async function checkBackendHealth() {
    const badge = document.getElementById("backend-status-badge");
    const text = document.getElementById("backend-status-text");

    try {
        const res = await fetch("/health");
        if (res.ok) {
            badge.className = "status-badge online";
            text.textContent = "CONNECTED (RS256 ONLINE)";
        } else {
            badge.className = "status-badge offline";
            text.textContent = `SERVER STATUS ${res.status}`;
        }
    } catch (err) {
        badge.className = "status-badge offline";
        text.textContent = "BACKEND DISCONNECTED";
    }
}

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
    initThemeToggle();
    initTabNavigation();
    checkBackendHealth();
    setInterval(checkBackendHealth, 30000);

    // Initialize individual functional sub-modules
    initPlayground();
    initClientPortal();
    initUserManager();
    initMetadataViewer();
});
