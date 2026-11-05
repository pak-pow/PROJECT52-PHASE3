/**
 * PulseSub Mobile-First Frontend Application Controller
 * Coordinates mobile-first navigation, view rendering, theme switching, and global state.
 */

"use strict";

import { Api } from "./api.js";
import { DeviceFrame } from "./device_frame.js";
import { PortalView } from "./portal_view.js";
import { PricingView } from "./pricing_view.js";
import { SandboxConsole } from "./sandbox_console.js";
import { UsageView } from "./usage_view.js";

// Global toast helper
window.showToast = function (message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast-item toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add("fade-out");
        setTimeout(() => toast.remove(), 300);
    }, 3200);
};

class AppController {
    constructor() {
        this.activeTab = "overview";
        this.state = {
            user: null,
            plan: null,
            subscription: null,
            usageSummary: {},
        };
    }

    async init() {
        this.initTheme();
        this.initModal();
        DeviceFrame.init();
        this.initNavigation();
        await this.refreshState();
        this.renderActiveView();
        this.checkHealth();
    }

    initTheme() {
        const themeBtn = document.getElementById("theme-toggle-btn");
        const htmlEl = document.documentElement;
        const savedTheme = localStorage.getItem("pulse_theme") || "dark";
        htmlEl.setAttribute("data-theme", savedTheme);

        if (themeBtn) {
            themeBtn.addEventListener("click", () => {
                const current = htmlEl.getAttribute("data-theme") || "dark";
                const next = current === "dark" ? "light" : "dark";
                htmlEl.setAttribute("data-theme", next);
                localStorage.setItem("pulse_theme", next);
            });
        }
    }

    initModal() {
        const modal = document.getElementById("bottom-modal");
        const backdrop = document.getElementById("modal-backdrop");
        const closeBtn = document.getElementById("modal-close-btn");

        const closeModal = () => {
            if (modal) modal.classList.remove("open");
        };

        if (backdrop) backdrop.addEventListener("click", closeModal);
        if (closeBtn) closeBtn.addEventListener("click", closeModal);
    }

    initNavigation() {
        const navItems = document.querySelectorAll(".nav-item");
        navItems.forEach((btn) => {
            btn.addEventListener("click", () => {
                const tab = btn.getAttribute("data-tab");
                if (tab && tab !== this.activeTab) {
                    this.switchTab(tab);
                }
            });
        });
    }

    switchTab(tabName) {
        this.activeTab = tabName;
        document.querySelectorAll(".nav-item").forEach((btn) => {
            if (btn.getAttribute("data-tab") === tabName) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });
        this.renderActiveView();
    }

    async refreshState() {
        try {
            const data = await Api.getMyFeatures();
            this.state.plan = data.plan;
            this.state.subscription = data.subscription;
            this.state.usageSummary = data.usage_summary || {};

            const pill = document.getElementById("current-tier-pill");
            if (pill) {
                const tierName = (data.plan.name || "Free").toUpperCase();
                pill.textContent = `${tierName} PLAN`;
                pill.className = `tier-pill tier-${data.plan.tier}`;
            }
        } catch (err) {
            console.warn("Could not refresh state:", err);
        }
    }

    renderActiveView() {
        const container = document.getElementById("main-view-container");
        if (!container) return;

        const onStateChanged = async () => {
            await this.refreshState();
        };

        switch (this.activeTab) {
            case "overview":
                this.renderOverview(container);
                break;
            case "usage":
                UsageView.render(container, onStateChanged);
                break;
            case "plans":
                PricingView.render(container, onStateChanged);
                break;
            case "portal":
                PortalView.render(container, onStateChanged);
                break;
            case "sandbox":
                SandboxConsole.render(container, onStateChanged);
                break;
            default:
                this.renderOverview(container);
                break;
        }
    }

    renderOverview(container) {
        const plan = this.state.plan || { name: "Pro", tier: "pro" };
        const sub = this.state.subscription;
        const usage = this.state.usageSummary;

        const apiUsage = usage["monthly_api_calls"] || { usage: 0, limit: 50000, percentage: 0 };
        const projUsage = usage["max_projects"] || { usage: 1, limit: -1, percentage: 0, unlimited: true };
        const storageUsage = usage["storage_mb"] || { usage: 200, limit: 5000, percentage: 4 };

        const statusLabel = sub ? sub.status.toUpperCase() : "ACTIVE";
        const intervalLabel = sub ? sub.billing_interval.toUpperCase() : "MONTHLY";
        const daysRemaining = sub ? Math.max(0, Math.floor((new Date(sub.current_period_end) - new Date()) / 86400000)) : 30;

        container.innerHTML = `
        <div class="overview-view">
            <!-- Account Summary Card -->
            <div class="overview-hero-card">
                <div class="hero-top-row">
                    <div>
                        <span class="eyebrow">Active Subscription</span>
                        <h2 class="hero-plan-title">${plan.name} Tier</h2>
                    </div>
                    <span class="status-pill status-${sub ? sub.status : 'active'}">${statusLabel}</span>
                </div>
                <div class="hero-stats-row">
                    <div class="stat-box">
                        <span class="stat-num">${daysRemaining}</span>
                        <span class="stat-txt">Days in Cycle</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-num">${intervalLabel}</span>
                        <span class="stat-txt">Interval</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-num">${plan.features ? plan.features.length : 6}</span>
                        <span class="stat-txt">Features</span>
                    </div>
                </div>
            </div>

            <!-- Resource Snapshot Cards -->
            <div class="section-heading">
                <h3>Live Resource Consumption</h3>
                <button id="overview-go-usage-btn" class="text-link-btn">Detailed View &rarr;</button>
            </div>

            <div class="overview-meters-grid">
                <div class="mini-meter-card">
                    <div class="mini-meter-head">
                        <span>API Calls</span>
                        <strong>${apiUsage.usage.toLocaleString()} / ${apiUsage.limit === -1 ? 'Unlimited' : apiUsage.limit.toLocaleString()}</strong>
                    </div>
                    <div class="mini-progress-track">
                        <div class="mini-progress-fill" style="width: ${Math.min(100, apiUsage.percentage)}%;"></div>
                    </div>
                </div>

                <div class="mini-meter-card">
                    <div class="mini-meter-head">
                        <span>Cloud Storage</span>
                        <strong>${storageUsage.usage}MB / ${storageUsage.limit}MB</strong>
                    </div>
                    <div class="mini-progress-track">
                        <div class="mini-progress-fill" style="width: ${Math.min(100, storageUsage.percentage)}%;"></div>
                    </div>
                </div>

                <div class="mini-meter-card">
                    <div class="mini-meter-head">
                        <span>Projects</span>
                        <strong>${projUsage.unlimited ? 'Unlimited' : `${projUsage.usage} / ${projUsage.limit}`}</strong>
                    </div>
                    <div class="mini-progress-track">
                        <div class="mini-progress-fill" style="width: ${projUsage.unlimited ? 15 : Math.min(100, projUsage.percentage)}%;"></div>
                    </div>
                </div>
            </div>

            <!-- Quick Action Buttons -->
            <div class="section-heading">
                <h3>Quick Actions</h3>
            </div>
            <div class="quick-actions-grid">
                <button id="btn-quick-pricing" class="quick-card-btn">
                    <span class="btn-title">Compare Plans</span>
                    <span class="btn-sub">View tiers & preview proration</span>
                </button>
                <button id="btn-quick-usage" class="quick-card-btn">
                    <span class="btn-title">Simulate Usage</span>
                    <span class="btn-sub">Increment API calls & quotas</span>
                </button>
                <button id="btn-quick-portal" class="quick-card-btn">
                    <span class="btn-title">Billing & Receipts</span>
                    <span class="btn-sub">View past invoices & print</span>
                </button>
                <button id="btn-quick-sandbox" class="quick-card-btn">
                    <span class="btn-title">Webhook Simulator</span>
                    <span class="btn-sub">Fire Stripe lifecycle events</span>
                </button>
            </div>
        </div>
        `;

        // Wire quick links
        const goUsage = container.querySelector("#overview-go-usage-btn");
        if (goUsage) goUsage.onclick = () => this.switchTab("usage");

        const qPricing = container.querySelector("#btn-quick-pricing");
        if (qPricing) qPricing.onclick = () => this.switchTab("plans");

        const qUsage = container.querySelector("#btn-quick-usage");
        if (qUsage) qUsage.onclick = () => this.switchTab("usage");

        const qPortal = container.querySelector("#btn-quick-portal");
        if (qPortal) qPortal.onclick = () => this.switchTab("portal");

        const qSandbox = container.querySelector("#btn-quick-sandbox");
        if (qSandbox) qSandbox.onclick = () => this.switchTab("sandbox");
    }

    async checkHealth() {
        const statusMeta = document.getElementById("status-meta-text");
        const indicator = document.querySelector(".status-indicator");
        try {
            const data = await Api.getHealth();
            if (statusMeta) {
                statusMeta.textContent = `WAL DB: ${data.database} | Engine: ${data.service} v${data.version}`;
            }
            if (indicator) {
                indicator.classList.add("online");
            }
        } catch (err) {
            if (statusMeta) {
                statusMeta.textContent = `Backend error: ${err.message}`;
            }
            if (indicator) {
                indicator.classList.remove("online");
            }
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const app = new AppController();
    app.init();
});
