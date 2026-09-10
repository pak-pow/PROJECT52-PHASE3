/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Multi-Stage Pipeline Stepper Component
 */

import { escapeHtml, formatDuration } from '../utils/helpers.js';

export const STAGES_CONFIG = [
  {
    id: 'lint',
    name: 'Lint & Style',
    tools: 'Flake8 · Black',
    description: 'PEP 8 formatting & style checks',
  },
  {
    id: 'security',
    name: 'Security Audit',
    tools: 'Bandit (-ll)',
    description: 'Static vulnerability scanner',
  },
  {
    id: 'test',
    name: 'Pytest Matrix',
    tools: 'Pytest (90%+ Cov)',
    description: 'Unit test suite with branch gate',
  },
  {
    id: 'build',
    name: 'Package Bundle',
    tools: 'tar.gz Archive',
    description: 'Release artifact packaging',
  },
  {
    id: 'deploy',
    name: 'Deploy & Smoke',
    tools: 'Staging Probe',
    description: 'Deployment & health smoke test',
  },
];

/**
 * Renders the pipeline stepper inside the target container.
 * @param {HTMLElement} container
 * @param {Object} props
 * @param {Object} props.stageResults - e.g. { lint: { status: 'passed', duration: 0.9 }, ... }
 * @param {string|null} props.runningStage - current stage being executed or null
 * @param {string|null} props.selectedStage - currently selected stage for log filtering
 * @param {Function} props.onStageClick - callback when a stage node is clicked
 */
export function renderPipelineStepper(container, props = {}) {
  const {
    stageResults = {},
    runningStage = null,
    selectedStage = 'all',
    onStageClick = null,
  } = props;

  // Calculate progress bar percentage
  let passedCount = 0;
  let runningIndex = -1;

  STAGES_CONFIG.forEach((stage, idx) => {
    if (stageResults[stage.id]?.status === 'passed') {
      passedCount = idx + 1;
    }
    if (runningStage === stage.id) {
      runningIndex = idx;
    }
  });

  const activeProgressIdx = runningIndex >= 0 ? runningIndex + 0.5 : passedCount;
  const progressPercent = Math.min(Math.max((activeProgressIdx / (STAGES_CONFIG.length - 1)) * 100, 0), 100);

  let stagesHtml = '';

  STAGES_CONFIG.forEach((stage, idx) => {
    const res = stageResults[stage.id];
    let statusClass = 'idle';
    let iconContent = `${idx + 1}`;

    if (runningStage === stage.id) {
      statusClass = 'running';
      iconContent = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="12" y1="2" x2="12" y2="6"></line>
          <line x1="12" y1="18" x2="12" y2="22"></line>
          <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
          <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
          <line x1="2" y1="12" x2="6" y2="12"></line>
          <line x1="18" y1="12" x2="22" y2="12"></line>
          <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
          <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
        </svg>
      `;
    } else if (res?.status === 'passed') {
      statusClass = 'passed';
      iconContent = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `;
    } else if (res?.status === 'failed') {
      statusClass = 'failed';
      iconContent = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      `;
    }

    const durationText = res?.duration !== undefined ? formatDuration(res.duration) : '';
    const isSelected = selectedStage === stage.id ? 'style="outline: 2px dashed var(--color-primary); border-radius: var(--radius-md); padding: 4px;"' : '';

    stagesHtml += `
      <div class="stage-node ${statusClass}" data-stage-id="${escapeHtml(stage.id)}" ${isSelected} title="${escapeHtml(stage.description)} - Click to view logs">
        <div class="node-circle">
          ${iconContent}
        </div>
        <div class="stage-info">
          <div class="stage-title">${escapeHtml(stage.name)}</div>
          <div class="stage-tools">${escapeHtml(stage.tools)}</div>
          ${durationText ? `<span class="stage-duration">${escapeHtml(durationText)}</span>` : ''}
        </div>
      </div>
    `;
  });

  container.innerHTML = `
    <div class="pipeline-stepper-container">
      <div class="pipeline-track">
        <div class="pipeline-progress-bar" style="width: ${progressPercent}%;"></div>
        ${stagesHtml}
      </div>
    </div>
  `;

  // Attach stage click listeners
  if (onStageClick) {
    const nodes = container.querySelectorAll('.stage-node');
    nodes.forEach((node) => {
      node.addEventListener('click', () => {
        const stageId = node.getAttribute('data-stage-id');
        onStageClick(stageId);
      });
    });
  }
}
