/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Dark/Light Mode Theme Management
 */

const THEME_STORAGE_KEY = 'p52_w37_theme';

/**
 * Returns current active theme.
 * @returns {'dark'|'light'}
 */
export function getStoredTheme() {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  if (stored === 'dark' || stored === 'light') return stored;
  // Default to dark mode for developer / DevOps aesthetic
  return 'dark';
}

/**
 * Applies the specified theme to the document.
 * @param {'dark'|'light'} theme
 */
export function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_STORAGE_KEY, theme);

  const toggleBtn = document.getElementById('theme-toggle-btn');
  if (toggleBtn) {
    toggleBtn.innerHTML = theme === 'dark' ? '☀️' : '🌙';
    toggleBtn.setAttribute('title', `Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`);
    toggleBtn.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`);
  }
}

/**
 * Initializes theme listener and applies current theme.
 */
export function initTheme() {
  const current = getStoredTheme();
  applyTheme(current);

  const toggleBtn = document.getElementById('theme-toggle-btn');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', toggleTheme);
  }
}

/**
 * Toggles theme between dark and light.
 */
export function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const nextTheme = current === 'dark' ? 'light' : 'dark';
  applyTheme(nextTheme);
}
