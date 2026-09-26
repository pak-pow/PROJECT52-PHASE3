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
 * Returns inline SVG icon markup.
 * @param {string} name
 * @param {number} size
 * @param {string} className
 * @returns {string}
 */
export function getIcon(name, size = 16, className = "") {
  const cls = className ? ` class="${className}"` : "";
  const shared = `xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${cls} aria-hidden="true"`;

  const icons = {
    search: `<svg ${shared}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
    cart: `<svg ${shared}><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>`,
    close: `<svg ${shared}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    plus: `<svg ${shared}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
    minus: `<svg ${shared}><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
    trash: `<svg ${shared}><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`,
    check: `<svg ${shared}><polyline points="20 6 9 17 4 12"/></svg>`,
    alert: `<svg ${shared}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    info: `<svg ${shared}><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
    truck: `<svg ${shared}><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>`,
    tag: `<svg ${shared}><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>`,
    printer: `<svg ${shared}><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>`,
    card: `<svg ${shared}><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>`,
    arrowRight: `<svg ${shared}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`,
    package: `<svg ${shared}><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`,
    keyboard: `<svg ${shared}><rect x="2" y="4" width="20" height="16" rx="2"/><line x1="6" y1="8" x2="6" y2="8.01"/><line x1="10" y1="8" x2="10" y2="8.01"/><line x1="14" y1="8" x2="14" y2="8.01"/><line x1="18" y1="8" x2="18" y2="8.01"/><line x1="6" y1="12" x2="6" y2="12.01"/><line x1="10" y1="12" x2="10" y2="12.01"/><line x1="14" y1="12" x2="14" y2="12.01"/><line x1="18" y1="12" x2="18" y2="12.01"/><line x1="7" y1="16" x2="17" y2="16"/></svg>`,
    headphones: `<svg ${shared}><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>`,
    accessories: `<svg ${shared}><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
    apparel: `<svg ${shared}><path d="M20.38 3.46L16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/></svg>`,
  };

  return icons[name] || "";
}

/**
 * Returns an appropriate SVG icon for a product category.
 * @param {string} categorySlug
 * @param {number} size
 * @returns {string}
 */
export function getCategoryIcon(categorySlug, size = 48) {
  switch (categorySlug) {
    case "keyboards":
      return getIcon("keyboard", size);
    case "audio":
      return getIcon("headphones", size);
    case "accessories":
      return getIcon("accessories", size);
    case "apparel":
      return getIcon("apparel", size);
    default:
      return getIcon("package", size);
  }
}
