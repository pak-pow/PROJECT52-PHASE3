/**
 * PulseInfer Main Application Orchestrator.
 * Initializes controllers, coordinates tabs, and synchronizes telemetry.
 */

import { BenchmarkerController } from "./ui/benchmarker.js";
import { DashboardController } from "./ui/dashboard.js";
import { WorkbenchController } from "./ui/workbench.js";

class PulseInferApp {
    constructor() {
        this.workbench = null;
        this.benchmarker = null;
        this.dashboard = null;
        this.navTabs = document.getElementById("navTabs");
        this.healthPill = document.getElementById("gatewayHealthPill");
    }

    async init() {
        this.workbench = new WorkbenchController();
        this.benchmarker = new BenchmarkerController();
        this.dashboard = new DashboardController();

        this.bindNavigation();
        await this.checkHealth();
        await this.loadModels();
    }

    bindNavigation() {
        if (!this.navTabs) return;

        this.navTabs.querySelectorAll(".nav-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                const target = btn.dataset.tab;
                this.selectTab(target);
            });
        });
    }

    selectTab(tabName) {
        if (this.navTabs) {
            this.navTabs.querySelectorAll(".nav-btn").forEach((b) => {
                b.classList.toggle("active", b.dataset.tab === tabName);
            });
        }

        const tabs = ["playground", "benchmarker", "dashboard", "models"];
        tabs.forEach((t) => {
            const section = document.getElementById(`${t}Tab`);
            if (section) {
                section.classList.toggle("hidden", t !== tabName);
                section.classList.toggle("active", t === tabName);
            }
        });

        if (tabName === "dashboard" && this.dashboard) {
            this.dashboard.refresh();
        }
    }

    async checkHealth() {
        if (!this.healthPill) return;
        try {
            const res = await fetch("/api/health");
            if (res.ok) {
                this.healthPill.textContent = "Online - Healthy";
                this.healthPill.className = "health-pill";
            } else {
                this.healthPill.textContent = "Degraded";
                this.healthPill.className = "health-pill degraded";
            }
        } catch {
            this.healthPill.textContent = "Offline";
            this.healthPill.className = "health-pill degraded";
        }
    }

    async loadModels() {
        try {
            const res = await fetch("/api/v1/models");
            if (res.ok) {
                const data = await res.json();
                const models = data.models || [];
                if (this.workbench) this.workbench.setModels(models);
                if (this.dashboard) this.dashboard.renderRegistryExplorer(models);
                return;
            }
        } catch {
            // Graceful baseline fallback
        }

        const defaultModels = [
            {
                id: "nlp-sentiment",
                name: "PulseText Sentiment & Intent Analyzer",
                domain: "nlp",
                description: "Subword vocabulary and Softmax classifier for sentiment and intent detection.",
                active_version: "v1"
            },
            {
                id: "vision-classifier",
                name: "PulseVision Image Feature Classifier",
                domain: "vision",
                description: "Normalized tensor projection network classifying image content and visual quality.",
                active_version: "v1"
            },
            {
                id: "fraud-detector",
                name: "PulseRisk Tabular Fraud Scorer",
                domain: "tabular",
                description: "Calibrated decision boundary model computing transaction risk and anomaly scores.",
                active_version: "v1"
            }
        ];

        if (this.workbench) this.workbench.setModels(defaultModels);
        if (this.dashboard) this.dashboard.renderRegistryExplorer(defaultModels);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const app = new PulseInferApp();
    app.init();
});
