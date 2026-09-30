/**
 * Service Worker Registration and Lifecycle Coordinator
 */

export const SwRegister = {
  registration: null,

  /**
   * Registers the Service Worker and binds lifecycle callbacks.
   * @param {object} options
   * @param {function} [options.onInstalled]
   * @param {function} [options.onUpdated]
   * @param {function} [options.onOnline]
   * @param {function} [options.onOffline]
   * @returns {Promise<ServiceWorkerRegistration|null>}
   */
  async register({ onInstalled, onUpdated, onOnline, onOffline } = {}) {
    if (!("serviceWorker" in navigator)) {
      console.info("[SW] Service Workers are not supported in this browser.");
      return null;
    }

    // Attach online/offline network listeners
    window.addEventListener("online", () => {
      if (typeof onOnline === "function") {
        onOnline();
      }
    });

    window.addEventListener("offline", () => {
      if (typeof onOffline === "function") {
        onOffline();
      }
    });

    try {
      // Register sw.js relative to public root
      const reg = await navigator.serviceWorker.register("./sw.js", {
        scope: "./",
      });

      this.registration = reg;

      // Handle update discovery
      reg.addEventListener("updatefound", () => {
        const newWorker = reg.installing;
        if (!newWorker) return;

        newWorker.addEventListener("statechange", () => {
          if (newWorker.state === "installed") {
            if (navigator.serviceWorker.controller) {
              // Existing controller present -> new version waiting
              console.info("[SW] New TaskPulse update is ready.");
              if (typeof onUpdated === "function") {
                onUpdated(newWorker);
              }
            } else {
              // First installation -> content is cached for offline use
              console.info("[SW] TaskPulse is cached for offline use.");
              if (typeof onInstalled === "function") {
                onInstalled();
              }
            }
          }
        });
      });

      return reg;
    } catch (err) {
      console.warn("[SW] Registration failed:", err);
      return null;
    }
  },

  /**
   * Instructs the waiting Service Worker to activate immediately.
   * @param {ServiceWorker} [worker]
   */
  applyUpdate(worker) {
    const target = worker || (this.registration && this.registration.waiting);
    if (target) {
      target.postMessage({ type: "SKIP_WAITING" });
    }
  },

  /**
   * Returns current network status.
   * @returns {boolean}
   */
  isOnline() {
    return navigator.onLine;
  },

  /**
   * Requests a background sync registration from the service worker if supported.
   * @param {string} [tag]
   * @returns {Promise<boolean>}
   */
  async requestBackgroundSync(tag = "taskpulse-sync") {
    if (this.registration && "sync" in this.registration) {
      try {
        await this.registration.sync.register(tag);
        return true;
      } catch (err) {
        console.warn("[SW] Background sync registration failed:", err);
        return false;
      }
    }
    return false;
  },

  /**
   * Listens for messages dispatched from the active Service Worker.
   * @param {function} handler
   */
  onMessage(handler) {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.addEventListener("message", (event) => {
        if (typeof handler === "function") {
          handler(event.data);
        }
      });
    }
  },
};

