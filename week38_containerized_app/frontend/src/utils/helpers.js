/**
 * Utility helper functions for sanitization, formatting, and performance metrics.
 * 
 * The module exports pure functions for frontend state representation.
 */

/**
 * Escapes unsafe characters to prevent cross-site scripting (XSS) vulnerabilities.
 * 
 * The sanitizer converts dangerous characters into secure HTML entities.
 */
export function escapeHtml(unsafe) {
  if (unsafe === null || unsafe === undefined) {
    return '';
  }
  return String(unsafe)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Formats timestamps into localized human-readable display strings.
 * 
 * The helper parses ISO date strings or numeric unix timestamps.
 */
export function formatTimestamp(timestamp) {
  if (!timestamp) return 'N/A';
  try {
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) {
      return String(timestamp);
    }
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch (err) {
    return String(timestamp);
  }
}

/**
 * Computes badge styling based on response latency thresholds in milliseconds.
 * 
 * The helper maps response latency to performance classifications.
 */
export function getLatencyBadge(latencyMs) {
  if (latencyMs === undefined || latencyMs === null) {
    return { text: '-- ms', colorClass: 'badge-muted' };
  }
  const ms = parseFloat(latencyMs);
  if (ms < 5) {
    return { text: `${ms.toFixed(2)} ms`, colorClass: 'badge-fast' };
  }
  if (ms < 25) {
    return { text: `${ms.toFixed(2)} ms`, colorClass: 'badge-normal' };
  }
  return { text: `${ms.toFixed(2)} ms`, colorClass: 'badge-slow' };
}\n