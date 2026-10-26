/**
 * PulseInfer Observability Dashboard & Registry Explorer Controller.
 */

export class DashboardController {
    constructor() {
        this.statTotalRequests = document.getElementById("statTotalRequests");
        this.statAvgLatency = document.getElementById("statAvgLatency");
        this.statCacheHit = document.getElementById("statCacheHit");
        this.statErrorRate = document.getElementById("statErrorRate");
        this.logsTableBody = document.getElementById("logsTableBody");
        this.registryGrid = document.getElementById("registryGrid");
        this.refreshLogsBtn = document.getElementById("refreshLogsBtn");

        this.bindEvents();
    }

    bindEvents() {
        if (this.refreshLogsBtn) {
            this.refreshLogsBtn.addEventListener("click", () => this.refresh());
        }
    }

    async refresh() {
        await Promise.all([this.loadMetrics(), this.loadLogs()]);
    }

    async loadMetrics() {
        try {
            const res = await fetch("/api/v1/metrics");
            if (!res.ok) return;
            const data = await res.json();
            if (this.statTotalRequests) {
                this.statTotalRequests.textContent = data.total_requests || 0;
            }
            if (this.statAvgLatency) {
                this.statAvgLatency.textContent = `${(data.avg_latency_ms || 0).toFixed(2)} ms`;
            }
            if (this.statCacheHit) {
                this.statCacheHit.textContent = `${((data.cache_hit_ratio || 0) * 100).toFixed(1)}%`;
            }
            if (this.statErrorRate) {
                this.statErrorRate.textContent = `${((data.error_rate || 0) * 100).toFixed(1)}%`;
            }
        } catch {
            // Graceful fallback in initial development state
        }
    }

    async loadLogs() {
        if (!this.logsTableBody) return;
        try {
            const res = await fetch("/api/v1/logs");
            if (!res.ok) return;
            const data = await res.json();
            const logs = data.logs || [];

            if (logs.length === 0) {
                this.logsTableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No execution logs recorded yet.</td></tr>';
                return;
            }

            this.logsTableBody.innerHTML = logs.map((log) => `
                <tr>
                    <td>${log.created_at || "Just now"}</td>
                    <td><code>${log.model_id}</code></td>
                    <td><span class="version-tag">${log.version}</span></td>
                    <td>${log.batch_size}</td>
                    <td>${Number(log.latency_ms).toFixed(2)} ms</td>
                    <td>${log.cached ? "Yes" : "No"}</td>
                    <td><span style="color: ${log.status === 'success' ? 'var(--accent-emerald)' : 'var(--accent-rose)'};">${log.status}</span></td>
                </tr>
            `).join("");
        } catch {
            // Logs endpoint will be attached in later days
        }
    }

    renderRegistryExplorer(models) {
        if (!this.registryGrid) return;
        this.registryGrid.innerHTML = (models || []).map((m) => `
            <div class="registry-card">
                <div class="registry-card-header">
                    <h3>${m.name}</h3>
                    <span class="domain-tag">${m.domain}</span>
                </div>
                <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;">${m.description || ""}</p>
                <div style="font-size: 0.75rem; color: var(--text-muted); display: flex; justify-content: space-between;">
                    <span>Active Version: <strong>${m.active_version || "v1"}</strong></span>
                    <span>ID: <code>${m.id}</code></span>
                </div>
            </div>
        `).join("");
    }
}
