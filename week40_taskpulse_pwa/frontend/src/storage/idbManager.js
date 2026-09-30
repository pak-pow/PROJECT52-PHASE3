import { generateUuid } from "../utils/helpers.js";

/**
 * TaskPulse IndexedDB Storage Engine
 * Modern, zero-dependency Promise wrapper for client-side transactional storage.
 */

const DB_NAME = "taskpulse_db";
const DB_VERSION = 1;

let dbInstance = null;

/**
 * Opens or initializes the IndexedDB database.
 * @returns {Promise<IDBDatabase>}
 */
export function openDatabase() {
  if (dbInstance) {
    return Promise.resolve(dbInstance);
  }

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;

      // 1. Tasks Object Store (Primary Local Data Store)
      if (!db.objectStoreNames.contains("tasks")) {
        const taskStore = db.createObjectStore("tasks", { keyPath: "id" });
        taskStore.createIndex("category", "category", { unique: false });
        taskStore.createIndex("completed", "completed", { unique: false });
        taskStore.createIndex("priority", "priority", { unique: false });
        taskStore.createIndex("updated_at", "updated_at", { unique: false });
        taskStore.createIndex("sync_status", "sync_status", { unique: false });
      }

      // 2. Sync Queue Object Store (Offline Mutation Buffer)
      if (!db.objectStoreNames.contains("sync_queue")) {
        const queueStore = db.createObjectStore("sync_queue", {
          keyPath: "id",
          autoIncrement: true,
        });
        queueStore.createIndex("timestamp", "timestamp", { unique: false });
        queueStore.createIndex("action", "action", { unique: false });
      }
    };

    request.onsuccess = (event) => {
      dbInstance = event.target.result;
      resolve(dbInstance);
    };

    request.onerror = (event) => {
      console.error("[IDB] Failed to open IndexedDB:", event.target.error);
      reject(event.target.error);
    };
  });
}

export const IdbManager = {
  /**
   * Retrieves all tasks with optional category, status, and search filters.
   * @param {object} [filters]
   * @param {string} [filters.category]
   * @param {boolean|null} [filters.completed]
   * @param {string} [filters.priority]
   * @param {string} [filters.search]
   * @returns {Promise<Array<object>>}
   */
  async getAllTasks(filters = {}) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(["tasks"], "readonly");
      const store = transaction.objectStore("tasks");
      const request = store.getAll();

      request.onsuccess = () => {
        let tasks = request.result || [];

        // Sort descending by updated_at
        tasks.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));

        // Apply In-Memory Filtering
        if (filters.category && filters.category !== "all") {
          tasks = tasks.filter(
            (t) => (t.category || "").toLowerCase() === filters.category.toLowerCase()
          );
        }

        if (typeof filters.completed === "boolean") {
          tasks = tasks.filter((t) => Boolean(t.completed) === filters.completed);
        }

        if (filters.priority && filters.priority !== "all") {
          tasks = tasks.filter(
            (t) => (t.priority || "").toLowerCase() === filters.priority.toLowerCase()
          );
        }

        if (filters.search) {
          const q = filters.search.toLowerCase();
          tasks = tasks.filter(
            (t) =>
              (t.title && t.title.toLowerCase().includes(q)) ||
              (t.description && t.description.toLowerCase().includes(q))
          );
        }

        resolve(tasks);
      };

      request.onerror = (e) => reject(e.target.error);
    });
  },

  /**
   * Retrieves a single task by its unique ID.
   * @param {string} id
   * @returns {Promise<object|null>}
   */
  async getTaskById(id) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["tasks"], "readonly");
      const store = tx.objectStore("tasks");
      const request = store.get(id);

      request.onsuccess = () => resolve(request.result || null);
      request.onerror = (e) => reject(e.target.error);
    });
  },

  /**
   * Creates or updates a task in the local IndexedDB store.
   * @param {object} taskData
   * @returns {Promise<object>}
   */
  async saveTask(taskData) {
    const db = await openDatabase();
    const now = new Date().toISOString();

    const task = {
      id: taskData.id || generateUuid(),
      title: (taskData.title || "").trim(),
      description: (taskData.description || "").trim(),
      category: taskData.category || "work",
      priority: taskData.priority || "medium",
      due_date: taskData.due_date || "",
      completed: Boolean(taskData.completed),
      sync_status: taskData.sync_status || "pending",
      created_at: taskData.created_at || now,
      updated_at: now,
    };

    return new Promise((resolve, reject) => {
      const tx = db.transaction(["tasks"], "readwrite");
      const store = tx.objectStore("tasks");
      const request = store.put(task);

      request.onsuccess = () => resolve(task);
      request.onerror = (e) => reject(e.target.error);
    });
  },

  /**
   * Toggles the completion status of an existing task.
   * @param {string} id
   * @returns {Promise<object>}
   */
  async toggleTaskCompleted(id) {
    const task = await this.getTaskById(id);
    if (!task) {
      throw new Error(`Task with id '${id}' not found in IndexedDB.`);
    }

    task.completed = !task.completed;
    task.sync_status = "pending";
    task.updated_at = new Date().toISOString();

    return this.saveTask(task);
  },

  /**
   * Deletes a task by ID from IndexedDB.
   * @param {string} id
   * @returns {Promise<boolean>}
   */
  async deleteTask(id) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["tasks"], "readwrite");
      const store = tx.objectStore("tasks");
      const request = store.delete(id);

      request.onsuccess = () => resolve(true);
      request.onerror = (e) => reject(e.target.error);
    });
  },

  /**
   * Computes summary metrics across all tasks stored locally.
   * @returns {Promise<object>}
   */
  async getTaskStats() {
    const all = await this.getAllTasks();
    const completed = all.filter((t) => t.completed).length;
    const pending = all.length - completed;
    const urgent = all.filter((t) => !t.completed && t.priority === "urgent").length;

    return {
      total: all.length,
      completed,
      pending,
      urgent,
    };
  },

  /**
   * Returns current browser storage quota and usage estimates.
   * @returns {Promise<object>}
   */
  async getStorageQuota() {
    if (navigator.storage && navigator.storage.estimate) {
      const estimate = await navigator.storage.estimate();
      const usage = estimate.usage || 0;
      const quota = estimate.quota || 0;
      const percentUsed = quota > 0 ? ((usage / quota) * 100).toFixed(2) : "0.00";

      return {
        usageBytes: usage,
        quotaBytes: quota,
        percentUsed,
        formattedUsage: this._formatBytes(usage),
        formattedQuota: this._formatBytes(quota),
      };
    }

    return {
      usageBytes: 0,
      quotaBytes: 0,
      percentUsed: "0.00",
      formattedUsage: "0 KB",
      formattedQuota: "Unlimited",
    };
  },

  /**
   * Requests persistent storage permission from the browser.
   * @returns {Promise<boolean>}
   */
  async requestPersistentStorage() {
    if (navigator.storage && navigator.storage.persist) {
      return navigator.storage.persist();
    }
    return false;
  },

  /**
   * Seeds demo tasks if database is empty on first boot.
   */
  async seedInitialTasksIfEmpty() {
    const existing = await this.getAllTasks();
    if (existing.length > 0) return;

    const initialTasks = [
      {
        title: "Explore TaskPulse PWA Offline Storage",
        description: "Verify that creating, toggling, and editing tasks writes immediately to IndexedDB without network.",
        category: "work",
        priority: "urgent",
        completed: false,
      },
      {
        title: "Test Service Worker Cache Invalidation",
        description: "Check Cache Storage in DevTools to confirm App Shell assets are precached under taskpulse-static-v1.",
        category: "work",
        priority: "medium",
        completed: true,
      },
      {
        title: "Install TaskPulse as Standalone Desktop App",
        description: "Click the Install button in the header to run TaskPulse in its own chromeless desktop window.",
        category: "personal",
        priority: "low",
        completed: false,
      },
    ];

    for (const t of initialTasks) {
      await this.saveTask(t);
    }
  },

  _formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  },
};
