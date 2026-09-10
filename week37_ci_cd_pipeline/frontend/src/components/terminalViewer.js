/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Interactive Terminal Window & Console Output Component
 */

import { copyToClipboard, escapeHtml } from '../utils/helpers.js';

export class TerminalViewer {
  /**
   * @param {HTMLElement} container
   * @param {Object} options
   */
  constructor(container, options = {}) {
    this.container = container;
    this.activeFilter = options.initialFilter || 'all';
    this.logs = []; // Array of { stage: string, text: string, type: string, time: string }
    this.autoScroll = true;

    this.render();
  }

  /**
   * Sets active log filter tab.
   * @param {string} filter - 'all' | 'lint' | 'security' | 'test' | 'build' | 'deploy'
   */
  setFilter(filter) {
    this.activeFilter = filter.toLowerCase();
    this.updateTabButtons();
    this.renderLogs();
  }

  /**
   * Clears all current logs.
   */
  clear() {
    this.logs = [];
    this.renderLogs();
  }

  /**
   * Appends a log line to the terminal.
   * @param {string} stage - 'lint' | 'security' | 'test' | 'build' | 'deploy' | 'system'
   * @param {string} text - The log message text
   * @param {'ok'|'fail'|'cmd'|'warn'|'info'} [type='info']
   */
  appendLog(stage, text, type = 'info') {
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0] + '.' + String(now.getMilliseconds()).padStart(3, '0');

    this.logs.push({
      stage: stage.toLowerCase(),
      text,
      type,
      time: timeStr,
    });

    this.renderLogs();

    if (this.autoScroll) {
      const body = this.container.querySelector('.terminal-body');
      if (body) {
        body.scrollTop = body.scrollHeight;
      }
    }
  }

  /**
   * Copies the currently filtered log text.
   */
  copyLogs() {
    const filtered = this.getFilteredLogs();
    const rawText = filtered.map(l => `[${l.time}] [${l.stage.toUpperCase()}] ${l.text}`).join('\n');
    copyToClipboard(rawText, 'Terminal logs copied to clipboard!');
  }

  /**
   * Returns logs matching activeFilter.
   */
  getFilteredLogs() {
    if (this.activeFilter === 'all') return this.logs;
    return this.logs.filter(l => l.stage === this.activeFilter || l.stage === 'system');
  }

  updateTabButtons() {
    const tabs = this.container.querySelectorAll('.terminal-tab-btn');
    tabs.forEach(btn => {
      const filter = btn.getAttribute('data-filter');
      if (filter === this.activeFilter) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }

  renderLogs() {
    const body = this.container.querySelector('.terminal-body');
    if (!body) return;

    const filtered = this.getFilteredLogs();

    if (filtered.length === 0) {
      body.innerHTML = `
        <div class="log-line">
          <span class="log-timestamp">00:00:00.000</span>
          <span class="log-content" style="color: var(--terminal-muted)">Terminal ready. Click "Trigger Pipeline Run" to execute stages.</span>
        </div>
      `;
      return;
    }

    body.innerHTML = filtered.map(log => {
      let tagClass = 'log-tag-info';
      if (log.type === 'ok' || log.text.includes('[OK]') || log.text.includes('PASSED')) tagClass = 'log-tag-ok';
      else if (log.type === 'fail' || log.text.includes('[FAILED]') || log.text.includes('FAILED')) tagClass = 'log-tag-fail';
      else if (log.type === 'cmd' || log.text.startsWith('>>') || log.text.startsWith('$')) tagClass = 'log-tag-cmd';
      else if (log.type === 'warn') tagClass = 'log-tag-warn';

      return `
        <div class="log-line">
          <span class="log-timestamp">${escapeHtml(log.time)}</span>
          <span class="log-content ${tagClass}">${escapeHtml(log.text)}</span>
        </div>
      `;
    }).join('') + '<span class="terminal-cursor"></span>';
  }

  render() {
    this.container.innerHTML = `
      <div class="terminal-card">
        <div class="terminal-header">
          <div class="terminal-window-dots">
            <span class="dot dot-red"></span>
            <span class="dot dot-yellow"></span>
            <span class="dot dot-green"></span>
            <span class="terminal-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="4 17 10 11 4 5"></polyline>
                <line x1="12" y1="19" x2="20" y2="19"></line>
              </svg>
              Console Output & Execution Stream
            </span>
          </div>

          <div class="terminal-tabs">
            <button class="terminal-tab-btn ${this.activeFilter === 'all' ? 'active' : ''}" data-filter="all">All</button>
            <button class="terminal-tab-btn ${this.activeFilter === 'lint' ? 'active' : ''}" data-filter="lint">Lint</button>
            <button class="terminal-tab-btn ${this.activeFilter === 'security' ? 'active' : ''}" data-filter="security">Security</button>
            <button class="terminal-tab-btn ${this.activeFilter === 'test' ? 'active' : ''}" data-filter="test">Test</button>
            <button class="terminal-tab-btn ${this.activeFilter === 'build' ? 'active' : ''}" data-filter="build">Build</button>
            <button class="terminal-tab-btn ${this.activeFilter === 'deploy' ? 'active' : ''}" data-filter="deploy">Deploy</button>
          </div>

          <div class="terminal-actions">
            <button class="terminal-action-btn" id="terminal-copy-btn" title="Copy visible terminal output">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
              Copy
            </button>
            <button class="terminal-action-btn" id="terminal-clear-btn" title="Clear console buffer">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
              Clear
            </button>
          </div>
        </div>

        <div class="terminal-body"></div>
      </div>
    `;

    // Event listeners
    const tabBtns = this.container.querySelectorAll('.terminal-tab-btn');
    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const filter = btn.getAttribute('data-filter');
        this.setFilter(filter);
      });
    });

    const copyBtn = this.container.querySelector('#terminal-copy-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => this.copyLogs());
    }

    const clearBtn = this.container.querySelector('#terminal-clear-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => this.clear());
    }

    this.renderLogs();
  }
}
