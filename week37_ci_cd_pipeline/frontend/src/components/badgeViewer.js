/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Status Badges Showcase & Markdown Embed Snippets Component
 */

import { copyToClipboard, escapeHtml } from '../utils/helpers.js';
import { API_BASE_URL } from '../api/pipelineApi.js';

/**
 * Generates dynamic Shields.io-style SVG string with accurate proportional dimensions.
 */
function generateSvgBadge(label, message, color) {
  const labelStr = String(label);
  const msgStr = String(message);
  const labelWidth = Math.max(labelStr.length * 7 + 14, 42);
  const msgWidth = Math.max(msgStr.length * 7.5 + 18, 44);
  const totalWidth = labelWidth + msgWidth;
  const labelX = (labelWidth / 2.0) * 10;
  const msgX = (labelWidth + msgWidth / 2.0) * 10;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${totalWidth}" height="20" role="img" aria-label="${escapeHtml(labelStr)}: ${escapeHtml(msgStr)}">
    <title>${escapeHtml(labelStr)}: ${escapeHtml(msgStr)}</title>
    <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
    <clipPath id="r"><rect width="${totalWidth}" height="20" rx="3" fill="#fff"/></clipPath>
    <g clip-path="url(#r)">
      <rect width="${labelWidth}" height="20" fill="#555"/>
      <rect x="${labelWidth}" width="${msgWidth}" height="20" fill="${color}"/>
      <rect width="${totalWidth}" height="20" fill="url(#s)"/>
    </g>
    <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
      <text aria-hidden="true" x="${labelX}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">${escapeHtml(labelStr)}</text>
      <text x="${labelX}" y="140" transform="scale(.1)" fill="#fff">${escapeHtml(labelStr)}</text>
      <text aria-hidden="true" x="${msgX}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">${escapeHtml(msgStr)}</text>
      <text x="${msgX}" y="140" transform="scale(.1)" fill="#fff">${escapeHtml(msgStr)}</text>
    </g>
  </svg>`;
}

function getCoverageColor(pct) {
  const n = parseFloat(pct);
  if (isNaN(n) || n >= 90.0) return '#4c1';
  if (n >= 80.0) return '#dfb317';
  if (n >= 70.0) return '#fe7d37';
  return '#e05d44';
}

export function renderBadgeViewer(container, props = {}) {
  const {
    buildStatus = 'passing',
    coveragePct = 93.0,
    deployEnv = 'staging',
    isOnline = false,
  } = props;

  const formattedCoverage = typeof coveragePct === 'number'
    ? `${coveragePct.toFixed(1)}%`
    : String(coveragePct).endsWith('%') ? coveragePct : `${coveragePct}%`;

  const buildColor = buildStatus === 'passing' ? '#4c1' : '#e05d44';
  const covColor = getCoverageColor(coveragePct);
  const deployColor = deployEnv === 'production' ? '#4c1' : '#007ec6';

  const badges = [
    {
      id: 'build',
      name: 'CI Build Status',
      desc: 'Reflects the latest CI/CD test and linting status',
      filename: 'build.svg',
      fallbackSvg: generateSvgBadge('build', buildStatus, buildColor),
      markdown: `![build](${API_BASE_URL}/api/v1/badges/build.svg)`,
      html: `<img src="${API_BASE_URL}/api/v1/badges/build.svg" alt="build" />`,
      url: `${API_BASE_URL}/api/v1/badges/build.svg`,
    },
    {
      id: 'coverage',
      name: 'Branch Code Coverage',
      desc: 'Enforces strict 90%+ branch and statement testing',
      filename: 'coverage.svg',
      fallbackSvg: generateSvgBadge('coverage', formattedCoverage, covColor),
      markdown: `![coverage](${API_BASE_URL}/api/v1/badges/coverage.svg)`,
      html: `<img src="${API_BASE_URL}/api/v1/badges/coverage.svg" alt="coverage" />`,
      url: `${API_BASE_URL}/api/v1/badges/coverage.svg`,
    },
    {
      id: 'deploy',
      name: 'Deployment Target',
      desc: 'Active environment verified by smoke probe',
      filename: 'deploy.svg',
      fallbackSvg: generateSvgBadge('deploy', deployEnv, deployColor),
      markdown: `![deploy](${API_BASE_URL}/api/v1/badges/deploy.svg)`,
      html: `<img src="${API_BASE_URL}/api/v1/badges/deploy.svg" alt="deploy" />`,
      url: `${API_BASE_URL}/api/v1/badges/deploy.svg`,
    },
  ];

  const cardsHtml = badges.map(b => `
    <div class="badge-card" data-badge-id="${escapeHtml(b.id)}">
      <div class="badge-preview-area">
        <div class="badge-meta">
          <div class="badge-name">${escapeHtml(b.name)}</div>
          <div class="badge-desc">${escapeHtml(b.desc)}</div>
        </div>
        <div class="badge-render">
          ${isOnline
            ? `<img src="${b.url}?t=${Date.now()}" alt="${escapeHtml(b.name)}" class="badge-img" onerror="this.outerHTML = \`${b.fallbackSvg.replace(/`/g, '\\`')}\`" />`
            : b.fallbackSvg}
        </div>
      </div>

      <div class="badge-code-box">${escapeHtml(b.markdown)}</div>

      <div class="badge-action-btns">
        <button class="btn btn-secondary btn-sm copy-md-btn" data-text="${escapeHtml(b.markdown)}">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          Copy Markdown
        </button>
        <button class="btn btn-secondary btn-sm copy-html-btn" data-text="${escapeHtml(b.html)}">
          Copy HTML
        </button>
        <button class="btn btn-secondary btn-sm copy-url-btn" data-text="${escapeHtml(b.url)}">
          Copy URL
        </button>
      </div>
    </div>
  `).join('');

  container.innerHTML = `
    <div class="badges-grid">
      ${cardsHtml}
    </div>
  `;

  // Attach copy event listeners
  const copyMdBtns = container.querySelectorAll('.copy-md-btn');
  copyMdBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.getAttribute('data-text');
      copyToClipboard(text, 'Markdown badge snippet copied!');
    });
  });

  const copyHtmlBtns = container.querySelectorAll('.copy-html-btn');
  copyHtmlBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.getAttribute('data-text');
      copyToClipboard(text, 'HTML badge snippet copied!');
    });
  });

  const copyUrlBtns = container.querySelectorAll('.copy-url-btn');
  copyUrlBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.getAttribute('data-text');
      copyToClipboard(text, 'Badge image URL copied!');
    });
  });
}
