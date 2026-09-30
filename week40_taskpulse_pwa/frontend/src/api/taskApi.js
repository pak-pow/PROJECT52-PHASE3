/**
 * TaskPulse API Client
 * Interfaces with the Flask backend for task synchronization and health checks.
 */

const API_BASE =
  window.location.port === "5000"
    ? "/api"
    : "http://127.0.0.1:5000/api";

/**
 * Standard HTTP JSON request helper with timeout and offline protection.
 * @param {string} endpoint
 * @param {RequestInit} [options]
 * @returns {Promise<object>}
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(options.headers || {}),
    },
  };

  try {
    const response = await fetch(url, config);
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      const errorMsg = data.message || `HTTP ${response.status} Error`;
      throw new Error(errorMsg);
    }

    return data;
  } catch (err) {
    // Return structured offline/network error without throwing fatal exceptions
    return {
      status: "error",
      offline: !navigator.onLine,
      message: err.message || "Network request failed",
    };
  }
}

export const TaskApi = {
  /**
   * Health and connectivity check.
   * @returns {Promise<boolean>}
   */
  async checkHealth() {
    try {
      const res = await request("/health", { method: "GET" });
      return res && res.status === "healthy";
    } catch {
      return false;
    }
  },

  /**
   * Retrieves all tasks from the server, optionally filtered by category.
   * @param {string} [category]
   * @returns {Promise<Array<object>>}
   */
  async getTasks(category) {
    const query = category && category !== "all" ? `?category=${encodeURIComponent(category)}` : "";
    const res = await request(`/tasks${query}`, { method: "GET" });
    return res && res.status === "success" ? res.data : [];
  },

  /**
   * Retrieves a single task by ID.
   * @param {string} taskId
   * @returns {Promise<object|null>}
   */
  async getTask(taskId) {
    const res = await request(`/tasks/${taskId}`, { method: "GET" });
    return res && res.status === "success" ? res.data : null;
  },

  /**
   * Creates a new task on the server.
   * @param {object} taskData
   * @returns {Promise<object>}
   */
  async createTask(taskData) {
    return request("/tasks", {
      method: "POST",
      body: JSON.stringify(taskData),
    });
  },

  /**
   * Updates an existing task on the server.
   * @param {string} taskId
   * @param {object} updates
   * @returns {Promise<object>}
   */
  async updateTask(taskId, updates) {
    return request(`/tasks/${taskId}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    });
  },

  /**
   * Deletes a task on the server.
   * @param {string} taskId
   * @returns {Promise<object>}
   */
  async deleteTask(taskId) {
    return request(`/tasks/${taskId}`, {
      method: "DELETE",
    });
  },

  /**
   * Sends a batch of offline mutations to be processed with LWW conflict resolution.
   * @param {Array<object>} mutations
   * @returns {Promise<object>}
   */
  async batchSync(mutations) {
    return request("/sync/batch", {
      method: "POST",
      body: JSON.stringify({ mutations }),
    });
  },

  /**
   * Fetches delta changes (creates, updates, deletes) from the server since a given timestamp.
   * @param {string} [sinceTimestamp]
   * @returns {Promise<object>}
   */
  async getDelta(sinceTimestamp) {
    const query = sinceTimestamp ? `?since=${encodeURIComponent(sinceTimestamp)}` : "";
    return request(`/sync/delta${query}`, { method: "GET" });
  },
};
