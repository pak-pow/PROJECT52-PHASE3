/**
 * REST API client interacting with the Docker Pulse backend via Nginx reverse proxy.
 * 
 * The client wraps fetch requests for health checks, task CRUD, and benchmarks.
 */

const API_BASE = '/api/v1';

export const opsApi = {
  /**
   * Probes the Nginx gateway directly via the /healthz endpoint.
   */
  async checkNginxHealth() {
    try {
      const res = await fetch('/healthz');
      return res.ok;
    } catch (err) {
      return false;
    }
  },

  /**
   * Retrieves Flask service liveness, uptime, and host metadata.
   */
  async getLiveness() {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`Liveness probe failed with status ${res.status}`);
    return res.json();
  },

  /**
   * Evaluates PostgreSQL database and Redis cache connectivity and latencies.
   */
  async getReadiness() {
    const res = await fetch(`${API_BASE}/ready`);
    return res.json();
  },

  /**
   * Fetches service version and build metadata.
   */
  async getVersion() {
    const res = await fetch(`${API_BASE}/version`);
    if (!res.ok) throw new Error(`Version probe failed with status ${res.status}`);
    return res.json();
  },

  /**
   * Lists stored tasks with optional status/priority filtering and cache header inspection.
   */
  async getTasks(params = {}) {
    const query = new URLSearchParams();
    if (params.status && params.status !== 'all') query.set('status', params.status);
    if (params.priority && params.priority !== 'all') query.set('priority', params.priority);
    if (params.noCache) query.set('no_cache', 'true');

    const res = await fetch(`${API_BASE}/tasks?${query.toString()}`);
    if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.status}`);
    const data = await res.json();
    const cacheHeader = res.headers.get('X-Cache') || (data.cached ? 'HIT' : 'MISS');
    return { ...data, xCache: cacheHeader };
  },

  /**
   * Creates a new operational task in PostgreSQL and invalidates Redis list cache.
   */
  async createTask(taskData) {
    const res = await fetch(`${API_BASE}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(taskData),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error || `Failed to create task (${res.status})`);
    }
    return res.json();
  },

  /**
   * Updates task status in PostgreSQL and invalidates Redis cache.
   */
  async updateTaskStatus(taskId, newStatus) {
    const res = await fetch(`${API_BASE}/tasks/${taskId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) throw new Error(`Failed to update task ${taskId}`);
    return res.json();
  },

  /**
   * Deletes a task from PostgreSQL and purges cache keys.
   */
  async deleteTask(taskId) {
    const res = await fetch(`${API_BASE}/tasks/${taskId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(`Failed to delete task ${taskId}`);
    return res.json();
  },

  /**
   * Executes speed benchmark comparing PostgreSQL query latency vs. Redis cache latency.
   */
  async runBenchmark() {
    const res = await fetch(`${API_BASE}/benchmark`);
    if (!res.ok) throw new Error(`Benchmark failed with status ${res.status}`);
    return res.json();
  },
};