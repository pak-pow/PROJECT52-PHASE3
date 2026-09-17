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
            <p class="card-desc">The Front Door. Welcomes visitors, serves the web pages fast, and keeps traffic secure.</p>
          </div>
          <div class="card-footer">
            <span class="card-meta">web:8080</span>
            <span class="status-badge" id="status-nginx"><span class="status-dot dot-green"></span> Online</span>
          </div>
        </div>

        <!-- 2. Flask API -->
        <div class="card" id="card-api">
          <div>
            <div class="card-header">
              <span class="card-title">Flask Backend</span>
              <span class="card-icon">🐍</span>
            </div>
            <p class="card-desc">The Brain. Runs the Python code securely to process your tasks and verify inputs.</p>
          </div>
          <div class="card-footer">
            <span class="card-meta">api:5000</span>
            <span class="status-badge" id="status-api"><span class="status-dot dot-green"></span> Online</span>
          </div>
        </div>

        <!-- 3. PostgreSQL 16 -->
        <div class="card" id="card-db">
          <div>
            <div class="card-header">
              <span class="card-title">PostgreSQL Database</span>
              <span class="card-icon">🐘</span>
            </div>
            <p class="card-desc">The Filing Cabinet. Safely saves data to permanent disk storage so nothing is lost.</p>
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
              <span class="card-title">Redis Fast Cache</span>
              <span class="card-icon">⚡</span>
            </div>
            <p class="card-desc">The Quick Whiteboard. Holds instant memory copies so frequent reads load in under 1ms.</p>
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
      const isHealthy = livenessData.status === 'healthy';
      apiBadge.innerHTML = isHealthy
        ? `<span class="status-dot dot-green"></span> Online`
        : `<span class="status-dot dot-red"></span> Offline`;
      apiBadge.title = `Service Uptime: ${livenessData.uptime_seconds || 0}s`;
    }

    // 3. PostgreSQL
    const dbBadge = document.getElementById('status-db');
    if (dbBadge && readyData?.database) {
      const dbInfo = readyData.database;
      const badge = getLatencyBadge(dbInfo.latency_ms);
      dbBadge.innerHTML = `<span class="status-dot dot-green"></span> <span id="ping-db" class="${badge.colorClass}">${badge.text}</span>`;
    }

    // 4. Redis Cache
    const cacheBadge = document.getElementById('status-cache');
    if (cacheBadge && readyData?.cache) {
      const cacheInfo = readyData.cache;
      const badge = getLatencyBadge(cacheInfo.latency_ms);
      cacheBadge.innerHTML = `<span class="status-dot dot-green"></span> <span id="ping-cache" class="${badge.colorClass}">${badge.text}</span>`;
    }
  }
}