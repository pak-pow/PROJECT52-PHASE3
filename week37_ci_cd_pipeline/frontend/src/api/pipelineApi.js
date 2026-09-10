/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Pipeline REST API Client with Offline Fallback
 */

export const API_BASE_URL = window.API_BASE_URL || 'http://127.0.0.1:5000';

/**
 * Generic fetch helper with timeout and JSON parsing.
 */
async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), options.timeout || 6000);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    clearTimeout(timeoutId);

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `HTTP error ${response.status}`);
    }
    return { ok: true, data };
  } catch (err) {
    clearTimeout(timeoutId);
    return { ok: false, error: err.message || 'Connection failed' };
  }
}

/**
 * Health check probe.
 */
export async function getHealth() {
  return await apiRequest('/api/v1/health', { timeout: 3000 });
}

/**
 * Service version and commit metadata.
 */
export async function getVersion() {
  return await apiRequest('/api/v1/version', { timeout: 3000 });
}

/**
 * List recent deployments with optional environment filter.
 */
export async function getDeployments(params = {}) {
  const query = new URLSearchParams();
  if (params.environment && params.environment !== 'all') {
    query.set('environment', params.environment);
  }
  if (params.limit) {
    query.set('limit', params.limit);
  }
  const qs = query.toString() ? `?${query.toString()}` : '';
  return await apiRequest(`/api/v1/deployments${qs}`);
}

/**
 * List recent pipeline execution runs.
 */
export async function getPipelineRuns(limit = 20) {
  return await apiRequest(`/api/v1/pipeline-runs?limit=${limit}`);
}

/**
 * Retrieve latest local pipeline execution report.
 */
export async function getPipelineReport() {
  return await apiRequest('/api/v1/pipeline-report');
}

/**
 * Trigger local pipeline execution on backend.
 */
export async function triggerPipeline(stage = 'all', environment = 'staging') {
  return await apiRequest('/api/v1/pipeline/trigger', {
    method: 'POST',
    body: JSON.stringify({ stage, environment }),
    timeout: 30000, // Pipeline run may take ~6-10s
  });
}

/**
 * Records a new deployment event.
 */
export async function recordDeployment(payload) {
  return await apiRequest('/api/v1/deployments', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Generates mock pipeline report data when backend is not reached.
 */
export function getMockReport() {
  return {
    pipeline: 'Local CI/CD Orchestrator (Demo Mode)',
    target_stage: 'all',
    environment: 'staging',
    overall_status: 'success',
    total_duration_seconds: 6.84,
    coverage_pct: 95.05,
    stages: {
      lint: { status: 'passed', duration: 0.94 },
      security: { status: 'passed', duration: 0.3 },
      test: { status: 'passed', duration: 5.38, coverage: 95.05 },
      build: { status: 'passed', duration: 0.01, artifact: 'dist/app-release-bundle.tar.gz' },
      deploy: { status: 'passed', duration: 0.01, deployment_id: 1, environment: 'staging' },
    },
    timestamp: new Date().toISOString(),
  };
}

const SIMULATED_DEPLOYMENTS_KEY = 'project52_simulated_deployments';

/**
 * Returns mock deployments list.
 */
export function getMockDeployments() {
  try {
    const raw = sessionStorage.getItem(SIMULATED_DEPLOYMENTS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/**
 * Saves a simulated deployment to session storage.
 */
export function saveMockDeployment(deployment) {
  try {
    const list = getMockDeployments();
    list.unshift(deployment);
    sessionStorage.setItem(SIMULATED_DEPLOYMENTS_KEY, JSON.stringify(list));
    return list;
  } catch {
    return [deployment];
  }
}
