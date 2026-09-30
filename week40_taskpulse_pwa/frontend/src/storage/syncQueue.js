import { openDatabase } from "./idbManager.js";

/**
 * TaskPulse Offline Sync Queue Manager & Replay Engine
 * Buffers local mutations (CREATE, UPDATE, DELETE, TOGGLE) into IndexedDB
 * and reconciles bidirectional changes with the backend upon reconnection.
 */

const STORAGE_LAST_SYNC_KEY = "taskpulse_last_server_sync";

export const SyncQueue = {
  /**
   * Retrieves the ISO timestamp of the last successful server synchronization.
   * @returns {string|null}
   */
  getLastSyncTimestamp() {
    return localStorage.getItem(STORAGE_LAST_SYNC_KEY);
  },

  /**
   * Saves the ISO timestamp of the last successful server synchronization.
   * @param {string} timestamp
   */
  setLastSyncTimestamp(timestamp) {
    if (timestamp) {
      localStorage.setItem(STORAGE_LAST_SYNC_KEY, timestamp);
    }
  },

  /**
   * Enqueues an offline mutation into the IndexedDB sync_queue store.
   * @param {"CREATE"|"UPDATE"|"DELETE"|"TOGGLE"} action
   * @param {string} entityId
   * @param {object} [payload]
   * @returns {Promise<number>} Returns the auto-incremented queue item ID.
   */
  async enqueue(action, entityId, payload = {}) {
    const db = await openDatabase();
    const item = {
      action,
      entity_id: entityId,
      payload,
      timestamp: new Date().toISOString(),
    };

    return new Promise((resolve, reject) => {
      const tx = db.transaction(["sync_queue"], "readwrite");
      const store = tx.objectStore("sync_queue");
      const request = store.add(item);

      request.onsuccess = () => resolve(request.result);
      request.onerror = (e) => reject(e.target.error);
    });
  },

  /**
   * Retrieves all pending mutations in chronological order (FIFO).
   * @returns {Promise<Array<object>>}
   */
  async getAll() {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["sync_queue"], "readonly");
      const store = tx.objectStore("sync_queue");
      const index = store.index("timestamp");
      const request = index.getAll();

      request.onsuccess = () => resolve(request.result || []);
      request.onerror = (e) => reject(e.target.error);
    });
  },

  /**
   * Removes a processed mutation from the queue by its queue ID.
   * @param {number} queueId
   * @returns {Promise<boolean>}
   */
  async remove(queueId) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["sync_queue"], "readwrite");
      const store = tx.objectStore("sync_queue");
      const request = store.delete(queueId);

      request.onsuccess = () => resolve(true);
      request.onerror = (e) => reject(e.target.error);
    });
  },

  /**
   * Clears all items from the sync queue.
   * @returns {Promise<boolean>}
   */
  async clear() {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["sync_queue"], "readwrite");
      const store = tx.objectStore("sync_queue");
      const request = store.clear();

      request.onsuccess = () => resolve(true);
      request.onerror = (e) => reject(e.target.error);
    });
  },

  /**
   * Returns the count of pending mutations currently waiting in the queue.
   * @returns {Promise<number>}
   */
  async getPendingCount() {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["sync_queue"], "readonly");
      const store = tx.objectStore("sync_queue");
      const request = store.count();

      request.onsuccess = () => resolve(request.result || 0);
      request.onerror = (e) => reject(e.target.error);
    });
  },

  /**
   * Replays pending mutations to the remote backend and performs delta reconciliation.
   * @param {object} taskApi - TaskApi instance
   * @param {object} idbManager - IdbManager instance
   * @returns {Promise<{success: boolean, processed: number, serverDeltas: number, conflicts: number, reason?: string}>}
   */
  async replayQueue(taskApi, idbManager) {
    if (!navigator.onLine) {
      return { success: false, reason: "offline", processed: 0, serverDeltas: 0, conflicts: 0 };
    }

    const pending = await this.getAll();
    let conflictsCount = 0;
    let processedCount = 0;

    // 1. Flush local mutation queue if there are pending items
    if (pending.length > 0) {
      const batchPayload = pending.map((item) => ({
        action: item.action,
        entity_id: item.entity_id,
        payload: item.payload,
        timestamp: item.timestamp,
      }));

      const syncResult = await taskApi.batchSync(batchPayload);

      if (syncResult && syncResult.status === "success") {
        conflictsCount = syncResult.conflicts || 0;
        processedCount = pending.length;

        // Clean processed mutations from IndexedDB queue
        await Promise.all(pending.map((item) => this.remove(item.id)));
      } else {
        return {
          success: false,
          reason: syncResult?.message || "Batch sync failed",
          processed: 0,
          serverDeltas: 0,
          conflicts: 0,
        };
      }
    }

    // 2. Delta reconciliation: Pull updates and deletions made on server
    const sinceTimestamp = this.getLastSyncTimestamp();
    const deltaResult = await taskApi.getDelta(sinceTimestamp);
    let deltaCount = 0;

    if (deltaResult && deltaResult.status === "success") {
      const deltas = deltaResult.delta || [];
      deltaCount = deltas.length;

      for (const item of deltas) {
        if (item.is_deleted) {
          await idbManager.deleteTask(item.id);
        } else {
          await idbManager.saveTask(item);
        }
      }

      if (deltaResult.server_time) {
        this.setLastSyncTimestamp(deltaResult.server_time);
      }
    }

    return {
      success: true,
      processed: processedCount,
      serverDeltas: deltaCount,
      conflicts: conflictsCount,
    };
  },
};
