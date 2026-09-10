/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Top Navigation Bar Component with Service Health Beacon
 */

import { escapeHtml } from '../utils/helpers.js';

/**
 * Renders the navbar component.
 * @param {HTMLElement} container
 * @param {Object} props
 * @param {boolean} props.isOnline
 * @param {string} props.version
 * @param {string} props.commitHash
 * @param {Function} props.onHealthCheck
 */
export function renderNavbar(container, props = {}) {
  const {
    isOnline = false,
    version = '1.0.0',
    commitHash = 'latest',
    onHealthCheck = null,
  } = props;

  const beaconStatusClass = isOnline ? 'online' : 'offline';
  const beaconText = isOnline ? 'API Connected (:5000)' : 'API Offline (Demo Mode)';

  container.innerHTML = `
    <header class="app-navbar">
      <div class="app-container navbar-content">
        <div class="brand-section">
          <div class="brand-logo-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
              <polyline points="2 17 12 22 22 17"></polyline>
              <polyline points="2 12 12 17 22 12"></polyline>
            </svg>
          </div>
          <div class="brand-text">
            <div class="brand-title">
              CI/CD Pipeline Orchestrator
              <span class="badge badge-primary">Week 37</span>
            </div>
            <div class="brand-subtitle">Project 52 · Automated Quality Gates & Deployment System</div>
          </div>
        </div>

        <div class="navbar-actions">
          <div class="health-beacon ${beaconStatusClass}" id="health-beacon-btn" title="Click to refresh connection status">
            <span class="beacon-dot"></span>
            <span id="beacon-text">${escapeHtml(beaconText)}</span>
          </div>

          <div class="version-tag" title="Deployed Release Version">
            <span>${escapeHtml(version)}</span> · <span>#${escapeHtml(commitHash.slice(0, 7))}</span>
          </div>

          <button id="theme-toggle-btn" class="theme-toggle-btn" aria-label="Toggle Dark/Light Mode">
            🌙
          </button>
        </div>
      </div>
    </header>
  `;

  if (onHealthCheck) {
    const beacon = container.querySelector('#health-beacon-btn');
    if (beacon) {
      beacon.addEventListener('click', onHealthCheck);
    }
  }
}
