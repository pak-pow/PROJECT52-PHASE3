/**
 * TaskPulse Web Notifications & App Badging Service
 * Manages notification permissions, system tray alerts, and App Badging API.
 */

export const NotificationService = {
  /**
   * Checks whether the browser supports the Notification API.
   * @returns {boolean}
   */
  isSupported() {
    return typeof window !== "undefined" && "Notification" in window;
  },

  /**
   * Checks whether the App Badging API is supported.
   * @returns {boolean}
   */
  isBadgingSupported() {
    return typeof navigator !== "undefined" && "setAppBadge" in navigator;
  },

  /**
   * Retrieves current notification permission status.
   * @returns {"granted"|"denied"|"default"}
   */
  getPermission() {
    if (!this.isSupported()) return "denied";
    return Notification.permission;
  },

  /**
   * Requests user permission to display desktop/mobile notifications.
   * @returns {Promise<boolean>}
   */
  async requestPermission() {
    if (!this.isSupported()) {
      return false;
    }

    try {
      const permission = await Notification.requestPermission();
      return permission === "granted";
    } catch (err) {
      console.warn("[Notifications] Permission request error:", err);
      return false;
    }
  },

  /**
   * Dispatches a notification via the Service Worker registration or window fallback.
   * @param {string} title
   * @param {object} [options]
   * @param {string} [options.body]
   * @param {string} [options.tag]
   * @param {object} [options.data]
   * @param {Array<object>} [options.actions]
   * @param {ServiceWorkerRegistration} [registration]
   * @returns {Promise<boolean>}
   */
  async showNotification(title, options = {}, registration = null) {
    if (!this.isSupported() || this.getPermission() !== "granted") {
      return false;
    }

    const defaultOptions = {
      body: options.body || "",
      icon: "./icon.svg",
      badge: "./icon.svg",
      tag: options.tag || "taskpulse-alert",
      data: options.data || { url: "./index.html" },
      actions: options.actions || [
        { action: "view", title: "Open App" },
      ],
      ...options,
    };

    try {
      if (registration && "showNotification" in registration) {
        await registration.showNotification(title, defaultOptions);
        return true;
      }

      // Fallback to standard window Notification constructor
      new Notification(title, defaultOptions);
      return true;
    } catch (err) {
      console.warn("[Notifications] Failed to display notification:", err);
      return false;
    }
  },

  /**
   * Updates the native app icon badge number (e.g. pending tasks count).
   * @param {number} count
   * @returns {Promise<void>}
   */
  async updateBadge(count) {
    if (!this.isBadgingSupported()) return;

    try {
      if (typeof count === "number" && count > 0) {
        await navigator.setAppBadge(count);
      } else {
        await navigator.clearAppBadge();
      }
    } catch (err) {
      // Non-fatal if platform restricts background badging
      console.debug("[Badging] Badge update skipped:", err);
    }
  },

  /**
   * Clears the native app icon badge.
   * @returns {Promise<void>}
   */
  async clearBadge() {
    if (!this.isBadgingSupported()) return;

    try {
      await navigator.clearAppBadge();
    } catch (err) {
      console.debug("[Badging] Badge clear skipped:", err);
    }
  },
};
