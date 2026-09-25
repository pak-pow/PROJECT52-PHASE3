import { escapeHtml, getIcon } from "../utils/helpers.js";

/**
 * Toast Notification Component
 */
export function showToast(message, type = "info", duration = 3500) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.setAttribute("role", "alert");

  const iconName = type === "error" ? "alert" : type === "success" ? "check" : "info";
  const iconHtml = getIcon(iconName, 18, `toast-icon-${type}`);

  toast.innerHTML = `
    ${iconHtml}
    <span class="toast-message">${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);

  const removeTimer = setTimeout(() => {
    dismissToast(toast);
  }, duration);

  toast.addEventListener("click", () => {
    clearTimeout(removeTimer);
    dismissToast(toast);
  });
}

function dismissToast(toastElement) {
  if (!toastElement || !toastElement.parentElement) return;
  toastElement.classList.add("toast-exit");
  toastElement.addEventListener("animationend", () => {
    if (toastElement.parentElement) {
      toastElement.parentElement.removeChild(toastElement);
    }
  });
}
