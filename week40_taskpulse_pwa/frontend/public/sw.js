/**
 * TaskPulse Service Worker
 * Production-grade offline-first caching and lifecycle management.
 */

const CACHE_VERSION = "v1";
const STATIC_CACHE = `taskpulse-static-${CACHE_VERSION}`;
const RUNTIME_CACHE = `taskpulse-runtime-${CACHE_VERSION}`;

const PRECACHE_ASSETS = [
  "./",
  "./index.html",
  "./offline.html",
  "./manifest.json",
  "./icon.svg",
  "../src/main.js",
  "../src/swRegister.js",
  "../src/assets/base.css",
  "../src/assets/app.css",
  "../src/utils/helpers.js",
];

/**
 * Install Event: Precache App Shell assets and immediately activate.
 */
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => {
        return cache.addAll(PRECACHE_ASSETS).catch((err) => {
          // Log non-fatal error if individual module path differs in dev server
          console.warn("[SW] Precache asset load warning:", err);
        });
      })
      .then(() => self.skipWaiting())
  );
});

/**
 * Activate Event: Clean up stale caches from previous versions and claim clients.
 */
self.addEventListener("activate", (event) => {
  const allowedCaches = [STATIC_CACHE, RUNTIME_CACHE];
  event.waitUntil(
    caches
      .keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames.map((name) => {
            if (!allowedCaches.includes(name)) {
              return caches.delete(name);
            }
            return null;
          })
        );
      })
      .then(() => self.clients.claim())
  );
});

/**
 * Fetch Event: Multi-strategy request routing.
 */
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Non-GET requests (POST, PUT, DELETE) pass directly to network
  // (Offline mutations are queued client-side via IndexedDB)
  if (request.method !== "GET") {
    return;
  }

  // 1. Navigation Requests (HTML Pages) -> Network-First with Offline Fallback
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          if (cached) return cached;

          // Default fallback to index.html or offline.html
          const appShell = await caches.match("./index.html");
          if (appShell) return appShell;

          const offlinePage = await caches.match("./offline.html");
          return offlinePage || new Response("Offline", { status: 503 });
        })
    );
    return;
  }

  // 2. API Endpoints (/api/*) -> Network-First with Runtime Cache Fallback
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // 3. Static Assets (CSS, JS, SVG, Fonts) -> Cache-First with Network Fallback
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }

      return fetch(request)
        .then((networkResponse) => {
          if (
            networkResponse &&
            networkResponse.status === 200 &&
            request.url.startsWith("http")
          ) {
            const clone = networkResponse.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, clone));
          }
          return networkResponse;
        })
        .catch(() => {
          // If asset is missing while offline, return empty response or graceful stub
          return new Response("", { status: 408, statusText: "Offline" });
        });
    })
  );
});

/**
 * Message Event: Client-to-worker communication (e.g., skip waiting, version query).
 */
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});
