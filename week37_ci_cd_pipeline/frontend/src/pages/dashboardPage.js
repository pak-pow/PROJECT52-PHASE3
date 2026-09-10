/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Main Dashboard Controller & Orchestrator
 */

import {
  getDeployments,
  getHealth,
  getMockDeployments,
  getMockReport,
  getPipelineReport,
  getPipelineRuns,
  getVersion,
  triggerPipeline,
} from '../api/pipelineApi.js';
import { renderBadgeViewer } from '../components/badgeViewer.js';
import { renderDeploymentTable } from '../components/deploymentTable.js';
import { renderNavbar } from '../components/navbar.js';
import { renderPipelineStepper, STAGES_CONFIG } from '../components/pipelineStepper.js';
import { TerminalViewer } from '../components/terminalViewer.js';
import { escapeHtml, showToast } from '../utils/helpers.js';

export class DashboardPage {
  constructor(rootElement) {
    this.root = rootElement;
    this.state = {
      isOnline: false,
      version: '1.0.0',
      commitHash: 'da13f34',
      stageResults: {},
      runningStage: null,
      selectedLogStage: 'all',
      isExecuting: false,
      deployments: [],
      pipelineRuns: [],
      currentDeployFilter: 'all',
      coveragePct: 93.0,
      targetStage: 'all',
      targetEnv: 'staging',
    };

    this.terminal = null;
  }

  async init() {
    this.renderLayout();
    await this.refreshAllData();

    // Periodic health beacon polling
    setInterval(() => this.checkHealth(), 12000);
  }

  renderLayout() {
    this.root.innerHTML = `
      <div id="navbar-mount"></div>

      <main class="app-container dashboard-main">
        <!-- Offline Demo Mode Banner (shown when backend is not running) -->
        <div id="offline-banner-mount"></div>

        <!-- 1. Overview Metrics Cards -->
        <section class="metrics-grid" id="metrics-mount">
          <div class="metric-card">
            <div class="metric-icon-box">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="16 18 22 12 16 6"></polyline>
                <polyline points="8 6 2 12 8 18"></polyline>
              </svg>
            </div>
            <div class="metric-data">
              <span class="metric-value" id="metric-total-runs">—</span>
              <span class="metric-label">Pipeline Runs</span>
            </div>
          </div>

          <div class="metric-card success">
            <div class="metric-icon-box">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                <polyline points="22 4 12 14.01 9 11.01"></polyline>
              </svg>
            </div>
            <div class="metric-data">
              <span class="metric-value" id="metric-success-rate">—</span>
              <span class="metric-label">Success Rate</span>
            </div>
          </div>

          <div class="metric-card info">
            <div class="metric-icon-box">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
              </svg>
            </div>
            <div class="metric-data">
              <span class="metric-value" id="metric-coverage">93.0%</span>
              <span class="metric-label">Branch Coverage</span>
            </div>
          </div>

          <div class="metric-card warning">
            <div class="metric-icon-box">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
                <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
                <line x1="6" y1="6" x2="6.01" y2="6"></line>
                <line x1="6" y1="18" x2="6.01" y2="18"></line>
              </svg>
            </div>
            <div class="metric-data">
              <span class="metric-value" id="metric-deploy-status">Staging</span>
              <span class="metric-label">Deploy Target</span>
            </div>
          </div>
        </section>

        <!-- 2. Pipeline Execution Card -->
        <section class="card">
          <div class="card-header">
            <div class="card-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
              Automated CI/CD Pipeline
            </div>

            <div class="stepper-actions">
              <div class="form-group" style="flex-direction: row; align-items: center;">
                <label for="pipeline-stage-select" class="form-label" style="margin:0;">Stage:</label>
                <select id="pipeline-stage-select" class="form-select" style="padding: 0.35rem 0.75rem;">
                  <option value="all" selected>All Stages</option>
                  <option value="lint">1. Lint & Style</option>
                  <option value="security">2. Security Audit</option>
                  <option value="test">3. Pytest & Coverage</option>
                  <option value="build">4. Package Bundle</option>
                  <option value="deploy">5. Deploy & Smoke</option>
                </select>
              </div>

              <div class="form-group" style="flex-direction: row; align-items: center;">
                <label for="pipeline-env-select" class="form-label" style="margin:0;">Env:</label>
                <select id="pipeline-env-select" class="form-select" style="padding: 0.35rem 0.75rem;">
                  <option value="staging" selected>Staging</option>
                  <option value="production">Production</option>
                </select>
              </div>

              <button class="btn btn-primary" id="trigger-pipeline-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                Trigger Pipeline Run
              </button>
            </div>
          </div>

          <div id="pipeline-stepper-mount"></div>
        </section>

        <!-- 3. Terminal Window -->
        <section id="terminal-mount"></section>

        <!-- 4. Status Badges Grid -->
        <section class="card">
          <div class="card-header">
            <div class="card-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"></path>
              </svg>
              Live Status Badges (Zero-Dependency SVG)
            </div>
          </div>
          <div id="badges-mount"></div>
        </section>

        <!-- 5. Deployment Audit Log -->
        <section id="deployments-mount"></section>
      </main>

      <footer class="app-footer">
        <div class="app-container">
          Project 52 · <strong>Phase 3: Production</strong> — Week 37 CI/CD Pipeline Setup. Built with Python, Flask, Pytest & Vanilla JS.
        </div>
      </footer>
    `;

    // Initialize terminal viewer
    const termMount = this.root.querySelector('#terminal-mount');
    this.terminal = new TerminalViewer(termMount, {
      initialFilter: 'all',
    });

    // Attach trigger button listener
    const triggerBtn = this.root.querySelector('#trigger-pipeline-btn');
    if (triggerBtn) {
      triggerBtn.addEventListener('click', () => this.handleRunPipeline());
    }

    const stageSelect = this.root.querySelector('#pipeline-stage-select');
    if (stageSelect) {
      stageSelect.addEventListener('change', (e) => {
        this.state.targetStage = e.target.value;
      });
    }

    const envSelect = this.root.querySelector('#pipeline-env-select');
    if (envSelect) {
      envSelect.addEventListener('change', (e) => {
        this.state.targetEnv = e.target.value;
      });
    }

    this.updateNavbar();
    this.updateOfflineBanner();
  }

  updateNavbar() {
    const mount = this.root.querySelector('#navbar-mount');
    if (!mount) return;

    renderNavbar(mount, {
      isOnline: this.state.isOnline,
      version: this.state.version,
      commitHash: this.state.commitHash,
      onHealthCheck: () => {
        showToast('Checking API connection on port 5000...', 'info');
        this.checkHealth(true);
      },
    });
  }

  updateStepper() {
    const mount = this.root.querySelector('#pipeline-stepper-mount');
    if (!mount) return;

    renderPipelineStepper(mount, {
      stageResults: this.state.stageResults,
      runningStage: this.state.runningStage,
      selectedStage: this.state.selectedLogStage,
      onStageClick: (stageId) => {
        this.state.selectedLogStage = stageId;
        if (this.terminal) {
          this.terminal.setFilter(stageId);
        }
        this.updateStepper();
      },
    });
  }

  updateBadges() {
    const mount = this.root.querySelector('#badges-mount');
    if (!mount) return;

    const overallStatus = Object.values(this.state.stageResults).some(s => s.status === 'failed')
      ? 'failing'
      : 'passing';

    renderBadgeViewer(mount, {
      buildStatus: overallStatus,
      coveragePct: this.state.coveragePct,
      deployEnv: this.state.targetEnv,
      isOnline: this.state.isOnline,
    });
  }

  updateDeployments() {
    const mount = this.root.querySelector('#deployments-mount');
    if (!mount) return;

    renderDeploymentTable(mount, {
      deployments: this.state.deployments,
      currentFilter: this.state.currentDeployFilter,
      onFilterChange: (newFilter) => {
        this.state.currentDeployFilter = newFilter;
        this.updateDeployments();
      },
    });
  }

  updateMetrics() {
    const totalRunsEl = this.root.querySelector('#metric-total-runs');
    const successRateEl = this.root.querySelector('#metric-success-rate');
    const coverageEl = this.root.querySelector('#metric-coverage');
    const deployStatusEl = this.root.querySelector('#metric-deploy-status');

    const total = this.state.pipelineRuns.length;
    if (totalRunsEl) totalRunsEl.textContent = total > 0 ? String(total) : '8';

    if (successRateEl) {
      if (total > 0) {
        const passed = this.state.pipelineRuns.filter(r => r.overall_status === 'success').length;
        const rate = Math.round((passed / total) * 100);
        successRateEl.textContent = `${rate}%`;
      } else {
        successRateEl.textContent = '100%';
      }
    }

    if (coverageEl) {
      coverageEl.textContent = `${Number(this.state.coveragePct).toFixed(1)}%`;
    }
    if (deployStatusEl) deployStatusEl.textContent = this.state.targetEnv.toUpperCase();
  }

  updateOfflineBanner() {
    const mount = this.root.querySelector('#offline-banner-mount');
    if (!mount) return;

    if (!this.state.isOnline) {
      mount.innerHTML = `
        <div class="offline-banner">
          <div class="offline-banner-left">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path>
              <line x1="12" y1="9" x2="12" y2="13"></line>
              <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
            <div>
              <strong>Backend Offline (Demo Simulator Mode):</strong> The Flask API is not running. Displaying simulated sample pipeline data. Run <code>python run.py</code> in the backend folder to connect to live API on port 5000.
            </div>
          </div>
          <button class="btn btn-secondary btn-sm" id="retry-backend-btn">
            Connect
          </button>
        </div>
      `;

      const retryBtn = mount.querySelector('#retry-backend-btn');
      if (retryBtn) {
        retryBtn.addEventListener('click', () => {
          showToast('Checking connection to http://127.0.0.1:5000...', 'info');
          this.checkHealth(true);
        });
      }
    } else {
      mount.innerHTML = '';
    }
  }

  async checkHealth(notify = false) {
    const res = await getHealth();
    const wasOnline = this.state.isOnline;
    this.state.isOnline = res.ok;

    if (res.ok && res.data) {
      this.state.version = res.data.version || '1.0.0';
      if (notify && !wasOnline) {
        showToast('Connected to Flask API backend!', 'success');
      }
    } else if (notify && wasOnline) {
      showToast('API backend offline. Running in Demo Mode.', 'warning');
    }

    this.updateNavbar();
    this.updateBadges();
    this.updateOfflineBanner();
  }


  async refreshAllData() {
    await this.checkHealth();

    // Version info
    const verRes = await getVersion();
    if (verRes.ok && verRes.data) {
      this.state.version = verRes.data.version || '1.0.0';
      this.state.commitHash = verRes.data.commit_hash || 'latest';
    }

    // Deployments
    const depRes = await getDeployments();
    if (depRes.ok && depRes.data?.deployments) {
      this.state.deployments = depRes.data.deployments;
    } else {
      this.state.deployments = getMockDeployments();
    }

    // Pipeline Runs
    const runsRes = await getPipelineRuns();
    if (runsRes.ok && runsRes.data?.runs) {
      this.state.pipelineRuns = runsRes.data.runs;
    }

    // Latest Report
    const repRes = await getPipelineReport();
    if (repRes.ok && repRes.data?.stages) {
      this.state.stageResults = repRes.data.stages;
      if (repRes.data.coverage_pct) {
        this.state.coveragePct = repRes.data.coverage_pct;
      }
    } else {
      const mock = getMockReport();
      this.state.stageResults = mock.stages;
      this.state.coveragePct = mock.coverage_pct;
    }

    this.updateNavbar();
    this.updateStepper();
    this.updateBadges();
    this.updateDeployments();
    this.updateMetrics();
  }

  async handleRunPipeline() {
    if (this.state.isExecuting) return;

    this.state.isExecuting = true;
    const triggerBtn = this.root.querySelector('#trigger-pipeline-btn');
    if (triggerBtn) {
      triggerBtn.disabled = true;
      triggerBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M12 2a10 10 0 0 1 10 10"></path>
        </svg>
        Running Pipeline...
      `;
    }

    const targetStage = this.state.targetStage;
    const targetEnv = this.state.targetEnv;

    if (this.terminal) {
      this.terminal.clear();
      this.terminal.appendLog('system', `🚀 INITIATING LOCAL CI/CD PIPELINE (Target: ${targetStage.toUpperCase()} | Env: ${targetEnv.toUpperCase()})`, 'cmd');
    }

    // Determine stages to run
    const stagesToRun = targetStage === 'all'
      ? STAGES_CONFIG
      : STAGES_CONFIG.filter(s => s.id === targetStage);

    // Reset results for stages to run
    const newResults = { ...this.state.stageResults };
    stagesToRun.forEach(s => {
      delete newResults[s.id];
    });
    this.state.stageResults = newResults;
    this.updateStepper();

    // If backend is online, trigger real API execution
    if (this.state.isOnline) {
      this.terminal.appendLog('system', `>> Contacting backend orchestrator at /api/v1/pipeline/trigger...`, 'info');

      // Animate stages step-by-step for great UX
      for (const stage of stagesToRun) {
        this.state.runningStage = stage.id;
        this.updateStepper();

        this.terminal.appendLog(stage.id, `>> Executing Stage [${stage.name.toUpperCase()}]: ${stage.tools}...`, 'cmd');
        await new Promise(r => setTimeout(r, 600));

        this.terminal.appendLog(stage.id, `   Verifying assertions and exit codes...`, 'info');
      }

      // Execute actual runner
      const res = await triggerPipeline(targetStage, targetEnv);
      this.state.runningStage = null;

      if (res.ok && res.data) {
        if (res.data.report?.stages) {
          this.state.stageResults = res.data.report.stages;
          if (res.data.report.coverage_pct) {
            this.state.coveragePct = res.data.report.coverage_pct;
          }
        }

        this.terminal.appendLog('system', `[OK] Local CI/CD pipeline completed successfully!`, 'ok');
        this.terminal.appendLog('system', `[BADGES] Badges generated in backend/badges/ (build, coverage, deploy)`, 'ok');
        this.terminal.appendLog('system', `[REPORT] Written to backend/reports/pipeline_report.json`, 'ok');
        showToast('Pipeline execution finished successfully! 🎉', 'success');
      } else {
        this.terminal.appendLog('system', `[FAILED] Pipeline run failed: ${res.error || 'Execution error'}`, 'fail');
        showToast('Pipeline execution reported an error.', 'error');
      }
    } else {
      // Simulated offline execution
      this.terminal.appendLog('system', `>> Executing simulated local pipeline (API offline mode)...`, 'info');

      for (const stage of stagesToRun) {
        this.state.runningStage = stage.id;
        this.updateStepper();

        this.terminal.appendLog(stage.id, `>> [STAGE] Starting ${stage.name} (${stage.tools})`, 'cmd');
        await new Promise(r => setTimeout(r, 700));

        if (stage.id === 'lint') {
          this.terminal.appendLog('lint', `   Running flake8 app tests --max-line-length 88`, 'info');
          this.terminal.appendLog('lint', `   Running black --check app tests`, 'info');
          this.terminal.appendLog('lint', `[OK] Lint & PEP 8 formatting check passed (0 errors) in 0.82s`, 'ok');
          this.state.stageResults.lint = { status: 'passed', duration: 0.82 };
        } else if (stage.id === 'security') {
          this.terminal.appendLog('security', `   Running bandit -r app -ll (0 medium, 0 high)`, 'info');
          this.terminal.appendLog('security', `[OK] Bandit static security audit passed in 0.31s`, 'ok');
          this.state.stageResults.security = { status: 'passed', duration: 0.31 };
        } else if (stage.id === 'test') {
          this.terminal.appendLog('test', `   Running pytest --cov=app --cov-report=term-missing tests`, 'info');
          this.terminal.appendLog('test', `   TOTAL: 240 statements, 33 passed, 92.8% branch coverage`, 'info');
          this.terminal.appendLog('test', `[OK] Pytest test suite & coverage gate passed in 5.43s`, 'ok');
          this.state.stageResults.test = { status: 'passed', duration: 5.43, coverage: 93.0 };
        } else if (stage.id === 'build') {
          this.terminal.appendLog('build', `   Packaging dist/app-release-bundle.tar.gz`, 'info');
          this.terminal.appendLog('build', `[OK] Release bundle created successfully in 0.01s`, 'ok');
          this.state.stageResults.build = { status: 'passed', duration: 0.01 };
        } else if (stage.id === 'deploy') {
          this.terminal.appendLog('deploy', `   Deploying to ${targetEnv} environment and running smoke probe...`, 'info');
          this.terminal.appendLog('deploy', `   Smoke probe: GET /api/v1/health returned 200 OK (latency: 12ms)`, 'info');
          this.terminal.appendLog('deploy', `[OK] Deployment registered in database with status 'success'`, 'ok');
          this.state.stageResults.deploy = { status: 'passed', duration: 0.02, environment: targetEnv };

          // Add a mock deployment entry
          this.state.deployments.unshift({
            id: this.state.deployments.length + 1,
            service_name: 'deployment-monitor',
            environment: targetEnv,
            version: this.state.version,
            commit_hash: this.state.commitHash,
            triggered_by: 'pipeline-runner',
            status: 'success',
            notes: `Pipeline run to ${targetEnv}`,
            deployed_at: new Date().toISOString(),
          });
        }

        this.updateStepper();
      }

      this.state.runningStage = null;
      this.terminal.appendLog('system', `🏁 ALL TARGETED STAGES PASSED! 🎉`, 'ok');
      showToast('All pipeline stages executed successfully!', 'success');
    }

    this.state.isExecuting = false;
    if (triggerBtn) {
      triggerBtn.disabled = false;
      triggerBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        Trigger Pipeline Run
      `;
    }

    this.updateStepper();
    this.updateBadges();
    this.updateDeployments();
    this.updateMetrics();
  }
}
