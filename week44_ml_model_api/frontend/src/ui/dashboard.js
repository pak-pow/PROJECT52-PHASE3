/**
 * PulseInfer Observability Dashboard & Telemetry Visualizer Controller.
 */

export class DashboardController {
    constructor() {
        // Global Metrics
        this.statTotalRequests = document.getElementById("statTotalRequests");
        this.statAvgLatency = document.getElementById("statAvgLatency");
        this.statCacheHit = document.getElementById("statCacheHit");
        this.statThroughput = document.getElementById("statThroughput");
        this.statErrorRate = document.getElementById("statErrorRate");

        // Percentiles
        this.statP50 = document.getElementById("statP50");
        this.statP90 = document.getElementById("statP90");
        this.statP95 = document.getElementById("statP95");
        this.statP99 = document.getElementById("statP99");

        // Cache Health
        this.cacheOccupancyVal = document.getElementById("cacheOccupancyVal");
        this.cacheHitsVal = document.getElementById("cacheHitsVal");
        this.cacheMissesVal = document.getElementById("cacheMissesVal");
        this.cacheEvictionsVal = document.getElementById("cacheEvictionsVal");

        // Per-Model Grid
        this.modelTelemetryGrid = document.getElementById("modelTelemetryGrid");

        // Logs and Registry
        this.logsTableBody = document.getElementById("logsTableBody");
        this.logFilterModel = document.getElementById("logFilterModel");
        this.registryGrid = document.getElementById("registryGrid");

        // Controls
        this.refreshLogsBtn = document.getElementById("refreshLogsBtn");
        this.clearCacheBtn = document.getElementById("clearCacheBtn");
        this.resetTelemetryBtn = document.getElementById("resetTelemetryBtn");
        this.autoRefreshToggle = document.getElementById("autoRefreshToggle");

        this.autoRefreshInterval = null;

        this.bindEvents();
    }

    bindEvents() {
        if (this.refreshLogsBtn) {
            this.refreshLogsBtn.addEventListener("click", () => this.refresh());
        }
        if (this.clearCacheBtn) {
            this.clearCacheBtn.addEventListener("click", () => this.clearCache());
        }
        if (this.resetTelemetryBtn) {
            this.resetTelemetryBtn.addEventListener("click", () => this.resetTelemetry());
        }
        if (this.logFilterModel) {
            this.logFilterModel.addEventListener("change", () => this.loadLogs());
        }
        if (this.autoRefreshToggle) {
            this.autoRefreshToggle.addEventListener("change", (e) => {
                this.toggleAutoRefresh(e.target.checked);
            });
            this.toggleAutoRefresh(this.autoRefreshToggle.checked);
        }
    }

    toggleAutoRefresh(enabled) {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
        if (enabled) {
            this.autoRefreshInterval = setInterval(() => {
                // Only refresh if dashboard tab is visible
                const dashboardTab = document.getElementById("dashboardTab");
                if (dashboardTab && !dashboardTab.classList.contains("hidden")) {
                    this.refresh();
                }
            }, 3000);
        }
    }

    async refresh() {
        await Promise.all([this.loadMetrics(), this.loadLogs()]);
    }

    async clearCache() {
        try {
            await fetch("/api/v1/cache/clear", { method: "POST" });
            await this.refresh();
        } catch {
            // Ignore error
        }
    }

    async resetTelemetry() {
        try {
            await fetch("/api/v1/metrics/reset", { method: "POST" });
            await this.refresh();
        } catch {
            // Ignore error
        }
    }

    async loadMetrics() {
        try {
            const res = await fetch("/api/v1/metrics");
            if (!res.ok) return;
            const data = await res.json();

            const globalStats = data.global || {};
            const latencies = globalStats.latencies || {};
            const cacheStats = data.cache || {};
            const models = data.models || {};

            // Global Metrics
            if (this.statTotalRequests) {
                this.statTotalRequests.textContent = globalStats.total_requests || 0;
            }
            if (this.statAvgLatency) {
                this.statAvgLatency.textContent = `${(latencies.mean || 0).toFixed(2)} ms`;
            }
            if (this.statCacheHit) {
                this.statCacheHit.textContent = `${((globalStats.cache_hit_ratio || 0) * 100).toFixed(1)}%`;
            }
            if (this.statThroughput) {
                this.statThroughput.textContent = `${(globalStats.throughput_rps || 0).toFixed(1)} req/s`;
            }
            if (this.statErrorRate) {
                this.statErrorRate.textContent = `${((globalStats.error_rate || 0) * 100).toFixed(1)}%`;
            }

            // Percentiles
            if (this.statP50) this.statP50.textContent = `${(latencies.p50 || 0).toFixed(2)} ms`;
            if (this.statP90) this.statP90.textContent = `${(latencies.p90 || 0).toFixed(2)} ms`;
            if (this.statP95) this.statP95.textContent = `${(latencies.p95 || 0).toFixed(2)} ms`;
            if (this.statP99) this.statP99.textContent = `${(latencies.p99 || 0).toFixed(2)} ms`;

            // Cache Stats
            if (this.cacheOccupancyVal) {
                this.cacheOccupancyVal.textContent = `${cacheStats.size || 0} / ${cacheStats.max_size || 1024}`;
            }
            if (this.cacheHitsVal) this.cacheHitsVal.textContent = cacheStats.hits || 0;
            if (this.cacheMissesVal) this.cacheMissesVal.textContent = cacheStats.misses || 0;
            if (this.cacheEvictionsVal) this.cacheEvictionsVal.textContent = cacheStats.evictions || 0;

            // Render Per-Model Telemetry Grid
            this.renderModelTelemetry(models);
        } catch {
            // Graceful baseline fallback
        }
    }

    renderModelTelemetry(models) {
        if (!this.modelTelemetryGrid) return;
        const entries = Object.entries(models || {});

        if (entries.length === 0) {
            this.modelTelemetryGrid.innerHTML = '<span style="color: var(--text-muted); font-size: 0.85rem;">No active models reporting telemetry yet.</span>';
            return;
        }

        this.modelTelemetryGrid.innerHTML = entries.map(([modelId, stats]) => {
            const lat = stats.latencies || {};
            const hitRatio = ((stats.cache_hit_ratio || 0) * 100).toFixed(1);
            return `
                <div class="model-telemetry-card">
                    <div class="model-telemetry-header">
                        <span class="model-telemetry-id">${modelId}</span>
                        <span class="badge ${hitRatio > 50 ? 'cached' : ''}">Cache: ${hitRatio}%</span>
                    </div>
                    <div class="model-stat-row">
                        <span>Client Requests:</span>
                        <strong>${stats.total_requests || 0}</strong>
                    </div>
                    <div class="model-stat-row">
                        <span>Backend Inferences:</span>
                        <strong>${stats.total_inferences || 0}</strong>
                    </div>
                    <div class="model-stat-row">
                        <span>Average Latency:</span>
                        <strong>${(lat.mean || 0).toFixed(2)} ms</strong>
                    </div>
                    <div class="model-stat-row">
                        <span>Throughput:</span>
                        <strong>${(stats.throughput_rps || 0).toFixed(1)} req/s</strong>
                    </div>
                </div>
            `;
        }).join("");
    }

    async loadLogs() {
        if (!this.logsTableBody) return;
        const modelFilter = this.logFilterModel ? this.logFilterModel.value : "";
        const url = `/api/v1/logs?limit=40${modelFilter ? `&model_id=${encodeURIComponent(modelFilter)}` : ""}`;

        try {
            const res = await fetch(url);
            if (!res.ok) return;
            const data = await res.json();
            const logs = data.logs || [];

            if (logs.length === 0) {
                this.logsTableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No execution logs recorded yet.</td></tr>';
                return;
            }

            this.logsTableBody.innerHTML = logs.map((log) => {
                const isSuccess = log.status === "success";
                const isCached = Boolean(log.cached);
                return `
                    <tr>
                        <td style="color: var(--text-muted); font-size: 0.8rem;">${log.created_at || "Just now"}</td>
                        <td><code>${log.model_id}</code></td>
                        <td><span class="version-tag">${log.version}</span></td>
                        <td>${log.batch_size}</td>
                        <td><strong>${Number(log.latency_ms).toFixed(2)} ms</strong></td>
                        <td>
                            <span class="badge ${isCached ? 'cached' : ''}">
                                ${isCached ? 'Hit' : 'Miss'}
                            </span>
                        </td>
                        <td>
                            <span style="color: ${isSuccess ? 'var(--accent-emerald)' : 'var(--accent-rose)'}; font-weight: 600;">
                                ${log.status}
                            </span>
                        </td>
                    </tr>
                `;
            }).join("");
        } catch {
            // Endpoint fallback
        }
    }

    renderRegistryExplorer(models) {
        if (!this.registryGrid) return;
        this.registryGrid.innerHTML = (models || []).map((m) => `
            <div class="registry-card">
                <div class="registry-card-header">
                    <div>
                        <h3 style="font-size: 1.05rem; font-weight: 700;">${m.name}</h3>
                        <span style="font-size: 0.75rem; color: var(--text-muted);">Model ID: <code>${m.id}</code></span>
                    </div>
                    <span class="domain-tag">${m.domain}</span>
                </div>
                <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45;">${m.description || ""}</p>
                <div class="registry-card-meta">
                    <div class="registry-meta-item">
                        <span class="meta-label">Active Version</span>
                        <span class="version-tag">${m.active_version || "v1"}</span>
                    </div>
                    <div class="registry-meta-item">
                        <span class="meta-label">Status</span>
                        <span style="color: var(--accent-emerald); font-weight: 600; font-size: 0.8rem;">Ready for Serving</span>
                    </div>
                </div>
            </div>
        `).join("");
    }
}
