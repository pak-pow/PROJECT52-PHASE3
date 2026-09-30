import { escapeHtml, getIcon } from "../utils/helpers.js";

/**
 * Toast Notification Service
 * Displays transient alert toasts at the bottom right of the screen.
 */
export function showToast(message, type = "info", duration = 3000) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const iconName = type === "success" ? "check" : type === "error" ? "alert" : "info";
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon" aria-hidden="true">${getIcon(iconName, 18)}</span>
    <span class="toast-msg">${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-exit");
    setTimeout(() => toast.remove(), 250);
  }, duration);
}
