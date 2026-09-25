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
 * Returns accessible pure CSS icon elements without any SVG or external font dependencies.
 * @param {string} name 
 * @param {number} size 
 * @param {string} className 
 * @returns {string}
 */
export function getIcon(name, size = 16, className = "") {
  const sizeClass = size >= 24 ? "icon-lg" : size <= 14 ? "icon-sm" : "";
  const extraClass = className ? ` ${className}` : "";
  const finalClass = `css-icon icon-${name}${sizeClass ? " " + sizeClass : ""}${extraClass}`;
  return `<span class="${finalClass}" aria-hidden="true"></span>`;
}

