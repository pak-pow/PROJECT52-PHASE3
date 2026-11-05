/**
 * Usage View Controller
 * Visualizes metered resource consumption, progress gauges, and threshold capacity alerts.
 * Features an interactive consumption simulator for testing.
 */

"use strict";

import { Api } from "./api.js";

export const UsageView = {
    async render(container, onUsageRecorded) {
        this.container = container;
        this.onUsageRecorded = onUsageRecorded;

        try {
            const summary = await Api.getUsageSummary();
            this.summary = summary;
            this.buildUI();
        } catch (err) {
            container.innerHTML = `<div class="error-banner">Failed to load usage data: ${err.message}</div>`;
        }
    },

    buildUI() {
        const usageMap = this.summary.usage_summary || {};
        let gaugesHtml = "";

        for (const [metricKey, data] of Object.entries(usageMap)) {
            const label = metricKey.replace(/_/g, " ").toUpperCase();
            const used = data.usage || 0;
            const limit = data.limit;
            const percentage = data.percentage || 0;
            const isUnlimited = data.unlimited;
            const alertBadge = data.threshold_alert;

            let badgeClass = "badge-normal";
            let badgeText = "Normal";
            if (alertBadge === "100%") {
                badgeClass = "badge-danger";
                badgeText = "100% Cap";
            } else if (alertBadge === "90%") {
                badgeClass = "badge-warning";
                badgeText = "90% Near Limit";
            } else if (alertBadge === "80%") {
                badgeClass = "badge-info";
                badgeText = "80% Warning";
            }

            const limitDisplay = isUnlimited ? "Unlimited" : limit.toLocaleString();
            const usedDisplay = used.toLocaleString();

            gaugesHtml += `
            <div class="meter-card" data-metric="${metricKey}">
                <div class="meter-header">
                    <span class="meter-title">${label}</span>
                    <span class="meter-badge ${badgeClass}">${badgeText}</span>
                </div>
                <div class="meter-values">
                    <span class="value-used">${usedDisplay}</span>
                    <span class="value-divider">/</span>
                    <span class="value-limit">${limitDisplay}</span>
                </div>
                <div class="meter-progress-track">
                    <div class="meter-progress-bar ${badgeClass}" style="width: ${Math.min(100, percentage)}%;"></div>
                </div>
                <div class="meter-footer">
                    <span>${isUnlimited ? 'No hard limit' : `${percentage}% consumed`}</span>
                    <span>${isUnlimited ? '' : `${(data.remaining || 0).toLocaleString()} remaining`}</span>
                </div>
            </div>
            `;
        }

        this.container.innerHTML = `
        <div class="usage-view">
            <div class="view-header">
                <h2>Metered Resource Usage</h2>
                <p class="view-subtitle">Real-time consumption tracked against current subscription cycle.</p>
            </div>

            <div class="meters-grid">
                ${gaugesHtml}
            </div>

            <!-- Interactive Consumption Simulator Console -->
            <div class="simulator-card">
                <div class="simulator-header">
                    <h3>Interactive Consumption Simulator</h3>
                    <p class="simulator-sub">Dispatch live resource increments to test quota thresholds and rate limits.</p>
                </div>
                <div class="simulator-actions">
                    <button class="sim-btn" data-metric="monthly_api_calls" data-qty="10">+10 API Calls</button>
                    <button class="sim-btn" data-metric="monthly_api_calls" data-qty="100">+100 API Calls</button>
                    <button class="sim-btn" data-metric="storage_mb" data-qty="50">+50 MB Storage</button>
                    <button class="sim-btn" data-metric="max_projects" data-qty="1">+1 Project</button>
                </div>
                <div class="simulator-custom">
                    <label for="custom-metric">Custom Increment:</label>
                    <div class="custom-row">
                        <select id="custom-metric" class="sim-select">
                            <option value="monthly_api_calls">API Calls</option>
                            <option value="storage_mb">Storage (MB)</option>
                            <option value="max_projects">Projects</option>
                            <option value="team_seats">Team Seats</option>
                        </select>
                        <input id="custom-qty" type="number" min="1" value="5" class="sim-input" placeholder="Qty">
                        <button id="custom-record-btn" class="sim-btn primary">Record</button>
                    </div>
                </div>
                <div id="sim-response-banner" class="sim-response-banner hidden"></div>
            </div>
        </div>
        `;

        this.bindEvents();
    },

    bindEvents() {
        this.container.querySelectorAll(".sim-btn[data-metric]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const metric = btn.getAttribute("data-metric");
                const qty = parseInt(btn.getAttribute("data-qty"), 10);
                await this.recordConsumption(metric, qty);
            });
        });

        const customBtn = this.container.querySelector("#custom-record-btn");
        if (customBtn) {
            customBtn.addEventListener("click", async () => {
                const metric = this.container.querySelector("#custom-metric").value;
                const qty = parseInt(this.container.querySelector("#custom-qty").value, 10) || 1;
                await this.recordConsumption(metric, qty);
            });
        }
    },

    async recordConsumption(metricKey, quantity) {
        const responseBanner = this.container.querySelector("#sim-response-banner");
        try {
            const idempotencyKey = `sim_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
            const res = await Api.recordUsage(metricKey, quantity, idempotencyKey);
            const status = res.quota_status;

            window.showToast(`Recorded +${quantity} on ${metricKey}!`);
            if (responseBanner) {
                responseBanner.classList.remove("hidden", "error");
                responseBanner.classList.add("success");
                responseBanner.innerHTML = `
                    <strong>Usage Recorded:</strong> ${metricKey} (+${quantity}) &bull; 
                    New Used: ${status.usage} / ${status.limit === -1 ? 'Unlimited' : status.limit} &bull; 
                    Alert: <span class="pill-alert">${status.threshold_alert || 'Normal'}</span>
                `;
            }

            if (this.onUsageRecorded) this.onUsageRecorded();
            await this.render(this.container, this.onUsageRecorded);
        } catch (err) {
            window.showToast(`Failed to record usage: ${err.message}`, "error");
            if (responseBanner) {
                responseBanner.classList.remove("hidden", "success");
                responseBanner.classList.add("error");
                responseBanner.textContent = `Error: ${err.message}`;
            }
        }
    },
};
