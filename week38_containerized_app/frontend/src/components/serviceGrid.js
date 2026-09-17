/**
 * Component rendering the multi-service topology status grid with live latency beacons.
 * 
 * The component visualizes Nginx, Flask, PostgreSQL, and Redis health states.
 */

import { escapeHtml, getLatencyBadge } from '../utils/helpers.js';

export class ServiceGrid {
  constructor(container) {
    this.container = container;
  }

  render() {
    this.container.innerHTML = `
      <div class="grid" id="service-grid-cards">
        <!-- 1. Nginx Gateway -->
        <div class="card" id="card-nginx">
          <div>
            <div class="card-header">
              <span class="card-title">Nginx Gateway</span>
              <span class="card-icon">🌐</span>
            </div>
            <p class="card-desc">Reverse proxy ingress on port 8080 handling gzip compression and static UI assets.</p>
          </div>
          <div class="card-footer">
            <span class="card-meta">web:8080 ➔ 80</span>
            <span class="status-badge" id="status-nginx"><span class="status-dot"></span> Active</span>
          </div>
        </div>

        <!-- 2. Flask API -->
        <div class="card" id="card-api">
          <div>
            <div class="card-header">
              <span class="card-title">Flask Service</span>
              <span class="card-icon">🐍</span>
            </div>
            <p class="card-desc">Gunicorn WSGI backend running inside a non-root unprivileged container.</p>
          </div>
          <div class="card-footer">
            <span class="card-meta">api:5000 (Internal)</span>
            <span class="status-badge" id="status-api"><span class="status-dot"></span> Active</span>
          </div>
        </div>

        <!-- 3. PostgreSQL 16 -->
        <div class="card" id="card-db">
          <div>
            <div class="card-header">
              <span class="card-title">PostgreSQL 16</span>
              <span class="card-icon">🐘</span>
            </div>
            <p class="card-desc">Persistent relational database mounted to named volume postgres_data.</p>
          </div>
          <div class="card-footer">
            <span class="card-meta">db:5432</span>
            <span class="status-badge" id="status-db"><span class="status-dot"></span> <span id="ping-db">-- ms</span></span>
          </div>
        </div>

        <!-- 4. Redis 7 Cache -->
        <div class="card" id="card-cache">
          <div>
            <div class="card-header">
              <span class="card-title">Redis 7 Cache</span>
              <span class="card-icon">⚡</span>
            </div>
            <p class="card-desc">In-memory key-value cache and benchmark probe with AOF persistence.</p>
          </div>
          <div class="card-footer">
            <span class="card-meta">cache:6379</span>
            <span class="status-badge" id="status-cache"><span class="status-dot"></span> <span id="ping-cache">-- ms</span></span>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * Updates service latency badges and health dot colors based on live readiness probes.
   */
  updateTelemetry(readyData, livenessData, nginxOk) {
    // 1. Nginx
    const nginxBadge = document.getElementById('status-nginx');
    if (nginxBadge) {
      nginxBadge.innerHTML = nginxOk
        ? `<span class="status-dot dot-green"></span> Online`
        : `<span class="status-dot dot-red"></span> Offline`;
    }

    // 2. Flask API
    const apiBadge = document.getElementById('status-api');
    if (apiBadge && livenessData) {
      const uptimeStr = `${livenessData.uptime_seconds || 0}s`;
      apiBadge.innerHTML = `<span class="status-dot dot-green"></span> Up ${uptimeStr}`;
    }

    // 3. PostgreSQL
    const dbPing = document.getElementById('ping-db');
    if (dbPing && readyData?.database) {
      const dbInfo = readyData.database;
      const badge = getLatencyBadge(dbInfo.latency_ms);
      dbPing.innerHTML = `${badge.text}`;
    }

    // 4. Redis Cache
    const cachePing = document.getElementById('ping-cache');
    if (cachePing && readyData?.cache) {
      const cacheInfo = readyData.cache;
      const badge = getLatencyBadge(cacheInfo.latency_ms);
      cachePing.innerHTML = `${badge.text}`;
    }
  }
}