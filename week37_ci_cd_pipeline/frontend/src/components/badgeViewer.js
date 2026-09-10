/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Status Badges Showcase & Markdown Embed Snippets Component
 */

import { copyToClipboard, escapeHtml } from '../utils/helpers.js';
import { API_BASE_URL } from '../api/pipelineApi.js';

export function renderBadgeViewer(container, props = {}) {
  const {
    buildStatus = 'passing',
    coveragePct = 93.0,
    deployEnv = 'staging',
    isOnline = false,
  } = props;

  // Build SVG inline fallbacks if running in standalone preview
  const buildSvgFallback = `
    <svg xmlns="http://www.w3.org/2000/svg" width="94" height="20" role="img" aria-label="build: ${escapeHtml(buildStatus)}">
      <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
      <clipPath id="r"><rect width="94" height="20" rx="3" fill="#fff"/></clipPath>
      <g clip-path="url(#r)"><rect width="37" height="20" fill="#555"/><rect x="37" width="57" height="20" fill="${buildStatus === 'passing' ? '#4c1' : '#e05d44'}"/><rect width="94" height="20" fill="url(#s)"/></g>
      <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
        <text aria-hidden="true" x="195" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">build</text>
        <text x="195" y="140" transform="scale(.1)" fill="#fff">build</text>
        <text aria-hidden="true" x="645" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">${escapeHtml(buildStatus)}</text>
        <text x="645" y="140" transform="scale(.1)" fill="#fff">${escapeHtml(buildStatus)}</text>
      </g>
    </svg>
  `;

  const coverageSvgFallback = `
    <svg xmlns="http://www.w3.org/2000/svg" width="108" height="20" role="img" aria-label="coverage: ${coveragePct}%">
      <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
      <clipPath id="r"><rect width="108" height="20" rx="3" fill="#fff"/></clipPath>
      <g clip-path="url(#r)"><rect width="61" height="20" fill="#555"/><rect x="61" width="47" height="20" fill="#4c1"/><rect width="108" height="20" fill="url(#s)"/></g>
      <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
        <text aria-hidden="true" x="315" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">coverage</text>
        <text x="315" y="140" transform="scale(.1)" fill="#fff">coverage</text>
        <text aria-hidden="true" x="835" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">${coveragePct}%</text>
        <text x="835" y="140" transform="scale(.1)" fill="#fff">${coveragePct}%</text>
      </g>
    </svg>
  `;

  const deploySvgFallback = `
    <svg xmlns="http://www.w3.org/2000/svg" width="98" height="20" role="img" aria-label="deploy: ${escapeHtml(deployEnv)}">
      <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
      <clipPath id="r"><rect width="98" height="20" rx="3" fill="#fff"/></clipPath>
      <g clip-path="url(#r)"><rect width="47" height="20" fill="#555"/><rect x="47" width="51" height="20" fill="#007ec6"/><rect width="98" height="20" fill="url(#s)"/></g>
      <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
        <text aria-hidden="true" x="245" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">deploy</text>
        <text x="245" y="140" transform="scale(.1)" fill="#fff">deploy</text>
        <text aria-hidden="true" x="715" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">${escapeHtml(deployEnv)}</text>
        <text x="715" y="140" transform="scale(.1)" fill="#fff">${escapeHtml(deployEnv)}</text>
      </g>
    </svg>
  `;

  const badges = [
    {
      id: 'build',
      name: 'CI Build Status',
      desc: 'Reflects the latest CI/CD test and linting status',
      filename: 'build.svg',
      fallbackSvg: buildSvgFallback,
      markdown: `![build](${API_BASE_URL}/api/v1/badges/build.svg)`,
      html: `<img src="${API_BASE_URL}/api/v1/badges/build.svg" alt="build" />`,
      url: `${API_BASE_URL}/api/v1/badges/build.svg`,
    },
    {
      id: 'coverage',
      name: 'Branch Code Coverage',
      desc: 'Enforces strict 90%+ branch and statement testing',
      filename: 'coverage.svg',
      fallbackSvg: coverageSvgFallback,
      markdown: `![coverage](${API_BASE_URL}/api/v1/badges/coverage.svg)`,
      html: `<img src="${API_BASE_URL}/api/v1/badges/coverage.svg" alt="coverage" />`,
      url: `${API_BASE_URL}/api/v1/badges/coverage.svg`,
    },
    {
      id: 'deploy',
      name: 'Deployment Target',
      desc: 'Active environment verified by smoke probe',
      filename: 'deploy.svg',
      fallbackSvg: deploySvgFallback,
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
