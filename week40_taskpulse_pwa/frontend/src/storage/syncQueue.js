import { openDatabase } from "./idbManager.js";

/**
 * TaskPulse Offline Sync Queue Manager
 * Buffers local mutations (CREATE, UPDATE, DELETE, TOGGLE) into IndexedDB
 * so they can be securely replayed to the backend when connectivity returns.
 */

export const SyncQueue = {
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
};
