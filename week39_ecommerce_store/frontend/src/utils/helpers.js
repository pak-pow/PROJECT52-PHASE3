/**
 * Utility helpers for formatting, security escaping, session management, and SVG icons.
 */

const STORAGE_KEY_CART_TOKEN = "shoppulse_cart_token";

/**
 * Formats integer cents to USD currency string.
 * @param {number} cents 
 * @returns {string}
 */
export function formatCurrency(cents) {
  if (typeof cents !== "number" || isNaN(cents)) {
    return "$0.00";
  }
  const dollars = cents / 100;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(dollars);
}

/**
 * Escapes unsafe HTML characters to prevent XSS.
 * @param {string} str 
 * @returns {string}
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Retrieves the stored cart token from localStorage.
 * @returns {string|null}
 */
export function getStoredCartToken() {
  try {
    return localStorage.getItem(STORAGE_KEY_CART_TOKEN);
  } catch (err) {
    return null;
  }
}

/**
 * Persists the cart token in localStorage.
 * @param {string} token 
 */
export function setStoredCartToken(token) {
  try {
    if (token) {
      localStorage.setItem(STORAGE_KEY_CART_TOKEN, token);
    }
  } catch (err) {
    // LocalStorage write unavailable
  }
}

/**
 * Clears the stored cart token.
 */
export function clearStoredCartToken() {
  try {
    localStorage.removeItem(STORAGE_KEY_CART_TOKEN);
  } catch (err) {
    // LocalStorage clear unavailable
  }
}

/**
 * Returns accessible inline SVG icon strings without external CDN dependencies.
 * @param {string} name 
 * @param {number} size 
 * @param {string} className 
 * @returns {string}
 */
export function getIcon(name, size = 16, className = "") {
  const cls = className ? `class="${className}"` : "";
  const attrs = `width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ${cls}`;

  switch (name) {
    case "cart":
      return `<svg ${attrs}><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>`;
    case "search":
      return `<svg ${attrs}><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`;
    case "close":
      return `<svg ${attrs}><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
    case "plus":
      return `<svg ${attrs}><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>`;
    case "minus":
      return `<svg ${attrs}><line x1="5" y1="12" x2="19" y2="12"></line></svg>`;
    case "trash":
      return `<svg ${attrs}><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`;
    case "check":
      return `<svg ${attrs}><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`;
    case "alert":
      return `<svg ${attrs}><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    case "info":
      return `<svg ${attrs}><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
    case "truck":
      return `<svg ${attrs}><rect x="1" y="3" width="15" height="13"></rect><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"></polygon><circle cx="5.5" cy="18.5" r="2.5"></circle><circle cx="18.5" cy="18.5" r="2.5"></circle></svg>`;
    case "tag":
      return `<svg ${attrs}><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"></path><line x1="7" y1="7" x2="7.01" y2="7"></line></svg>`;
    case "printer":
      return `<svg ${attrs}><polyline points="6 9 6 2 18 2 18 9"></polyline><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="6" y="14" width="12" height="8"></rect></svg>`;
    case "card":
      return `<svg ${attrs}><rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect><line x1="1" y1="10" x2="23" y2="10"></line></svg>`;
    case "arrowRight":
      return `<svg ${attrs}><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>`;
    case "package":
      return `<svg ${attrs}><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"></line><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>`;
    default:
      return "";
  }
}
