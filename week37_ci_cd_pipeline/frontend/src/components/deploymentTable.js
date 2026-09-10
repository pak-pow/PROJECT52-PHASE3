/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Deployments History & Audit Table Component
 */

import { copyToClipboard, escapeHtml, formatRelativeTime, formatTimestamp, getStatusBadgeHtml } from '../utils/helpers.js';

/**
 * Renders the deployment history table.
 * @param {HTMLElement} container
 * @param {Object} props
 * @param {Array} props.deployments - Array of deployment objects
 * @param {string} props.currentFilter - 'all' | 'staging' | 'production' | 'development'
 * @param {Function} props.onFilterChange - Callback when filter changes
 */
export function renderDeploymentTable(container, props = {}) {
  const {
    deployments = [],
    currentFilter = 'all',
    onFilterChange = null,
  } = props;

  const filtered = deployments.filter(d => {
    if (currentFilter === 'all') return true;
    return (d.environment || '').toLowerCase() === currentFilter.toLowerCase();
  });

  const emptyMessage = currentFilter === 'all'
    ? 'No deployments recorded yet. Trigger a pipeline run to record your first deployment.'
    : `No deployments recorded for environment: <strong>${escapeHtml(currentFilter)}</strong>`;

  const rowsHtml = filtered.length === 0
    ? `
      <tr>
        <td colspan="7">
          <div class="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <p>${emptyMessage}</p>
          </div>
        </td>
      </tr>
    `
    : filtered.map(d => {
        const envBadgeClass = d.environment === 'production'
          ? 'badge-success'
          : d.environment === 'staging'
            ? 'badge-primary'
            : 'badge-subtle';

        const commitShort = (d.commit_hash || 'HEAD').slice(0, 7);

        return `
          <tr>
            <td><strong>#${escapeHtml(d.id)}</strong></td>
            <td><span class="badge ${envBadgeClass}">${escapeHtml(d.environment)}</span></td>
            <td><code>${escapeHtml(d.version || '1.0.0')}</code></td>
            <td>
              <button class="commit-sha-pill" data-sha="${escapeHtml(d.commit_hash)}" title="Click to copy full commit hash">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="4"></circle>
                  <line x1="1.05" y1="12" x2="7" y2="12"></line>
                  <line x1="17.01" y1="12" x2="22.96" y2="12"></line>
                </svg>
                ${escapeHtml(commitShort)}
              </button>
            </td>
            <td><span class="badge badge-subtle">${escapeHtml(d.triggered_by || 'pipeline')}</span></td>
            <td>${getStatusBadgeHtml(d.status)}</td>
            <td title="${escapeHtml(formatTimestamp(d.deployed_at))}">${escapeHtml(formatRelativeTime(d.deployed_at))}</td>
          </tr>
        `;
      }).join('');

  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="card-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
          </svg>
          Deployment Audit Log
        </div>

        <div class="stepper-actions">
          <label for="deployment-env-filter" class="form-label" style="margin: 0; align-self: center;">Filter:</label>
          <select id="deployment-env-filter" class="form-select" style="padding: 0.35rem 0.75rem; font-size: 0.8125rem;">
            <option value="all" ${currentFilter === 'all' ? 'selected' : ''}>All Environments</option>
            <option value="staging" ${currentFilter === 'staging' ? 'selected' : ''}>Staging</option>
            <option value="production" ${currentFilter === 'production' ? 'selected' : ''}>Production</option>
            <option value="development" ${currentFilter === 'development' ? 'selected' : ''}>Development</option>
          </select>
        </div>
      </div>

      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Environment</th>
              <th>Version</th>
              <th>Commit Hash</th>
              <th>Triggered By</th>
              <th>Status</th>
              <th>Deployed</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    </div>
  `;

  // Attach filter change listener
  const filterSelect = container.querySelector('#deployment-env-filter');
  if (filterSelect && onFilterChange) {
    filterSelect.addEventListener('change', (e) => {
      onFilterChange(e.target.value);
    });
  }

  // Attach commit hash copy listeners
  const commitPills = container.querySelectorAll('.commit-sha-pill');
  commitPills.forEach(pill => {
    pill.addEventListener('click', () => {
      const sha = pill.getAttribute('data-sha');
      copyToClipboard(sha, `Commit hash ${sha} copied!`);
    });
  });
}
