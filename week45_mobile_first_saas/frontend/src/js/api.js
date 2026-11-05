/**
 * PulseSub REST API Client Service
 * Communicates with backend endpoints using signed bearer tokens or X-User-ID headers.
 */

"use strict";

const API_BASE = "";

function getHeaders(customHeaders = {}) {
    const headers = {
        "Content-Type": "application/json",
        ...customHeaders,
    };
    const token = localStorage.getItem("pulsesub_token");
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }
    const userId = localStorage.getItem("pulsesub_user_id") || "usr_demo_alice";
    headers["X-User-ID"] = userId;
    return headers;
}

async function request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const opts = {
        ...options,
        headers: getHeaders(options.headers || {}),
    };

    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof String)) {
        opts.body = JSON.stringify(opts.body);
    }

    const response = await fetch(url, opts);
    const contentType = response.headers.get("content-type") || "";

    let data = null;
    if (contentType.includes("application/json")) {
        data = await response.json();
    } else {
        data = await response.text();
    }

    if (!response.ok) {
        const errorMsg = (data && data.message) || (data && data.error) || `HTTP ${response.status}`;
        const err = new Error(errorMsg);
        err.status = response.status;
        err.data = data;
        err.response = response;
        throw err;
    }

    return { data, status: response.status, headers: response.headers };
}

export const Api = {
    // Health Check
    async getHealth() {
        const res = await request("/api/health");
        return res.data;
    },

    // Authentication
    async login(email, password) {
        const res = await request("/api/v1/auth/login", {
            method: "POST",
            body: { email, password },
        });
        if (res.data && res.data.token) {
            localStorage.setItem("pulsesub_token", res.data.token);
            if (res.data.user && res.data.user.id) {
                localStorage.setItem("pulsesub_user_id", res.data.user.id);
            }
        }
        return res.data;
    },

    async register(email, password, fullName) {
        const res = await request("/api/v1/auth/register", {
            method: "POST",
            body: { email, password, full_name: fullName },
        });
        if (res.data && res.data.token) {
            localStorage.setItem("pulsesub_token", res.data.token);
            if (res.data.user && res.data.user.id) {
                localStorage.setItem("pulsesub_user_id", res.data.user.id);
            }
        }
        return res.data;
    },

    async getMe() {
        const res = await request("/api/v1/auth/me");
        return res.data;
    },

    // Plans
    async getPlans() {
        const res = await request("/api/v1/plans");
        return res.data.plans || [];
    },

    async getPlan(planId) {
        const res = await request(`/api/v1/plans/${planId}`);
        return res.data.plan;
    },

    // Subscriptions & Proration
    async getCurrentSubscription() {
        const res = await request("/api/v1/subscriptions/current");
        return res.data;
    },

    async subscribe(planId, billingInterval = "monthly") {
        const res = await request("/api/v1/subscriptions/subscribe", {
            method: "POST",
            body: { plan_id: planId, billing_interval: billingInterval },
        });
        return res.data;
    },

    async changeTier(newPlanId, newInterval = null, previewOnly = false) {
        const payload = {
            new_plan_id: newPlanId,
            preview_only: previewOnly,
        };
        if (newInterval) {
            payload.new_interval = newInterval;
        }
        const res = await request("/api/v1/subscriptions/change-tier", {
            method: "POST",
            body: payload,
        });
        return res.data;
    },

    async cancelSubscription(immediate = false) {
        const res = await request("/api/v1/subscriptions/cancel", {
            method: "POST",
            body: { immediate },
        });
        return res.data;
    },

    async resumeSubscription() {
        const res = await request("/api/v1/subscriptions/resume", {
            method: "POST",
        });
        return res.data;
    },

    // Entitlements
    async getMyFeatures() {
        const res = await request("/api/v1/entitlements/my-features");
        return res.data;
    },

    async checkFeature(featureKey) {
        const res = await request(`/api/v1/entitlements/check?feature=${encodeURIComponent(featureKey)}`);
        return res.data;
    },

    // Metered Usage
    async recordUsage(metricKey, quantity = 1, idempotencyKey = null) {
        const payload = {
            metric_key: metricKey,
            quantity: quantity,
        };
        if (idempotencyKey) {
            payload.idempotency_key = idempotencyKey;
        }
        const res = await request("/api/v1/usage/record", {
            method: "POST",
            body: payload,
        });
        return res.data;
    },

    async getUsageSummary() {
        const res = await request("/api/v1/usage/summary");
        return res.data;
    },

    // Invoices & Billing
    async getInvoices() {
        const res = await request("/api/v1/billing/invoices");
        return res.data.invoices || [];
    },

    async getInvoice(invoiceId) {
        const res = await request(`/api/v1/billing/invoices/${invoiceId}`);
        return res.data.invoice;
    },

    async getInvoiceReceipt(invoiceId) {
        const res = await request(`/api/v1/billing/invoices/${invoiceId}/receipt`);
        return res.data;
    },

    async payInvoice(invoiceId) {
        const res = await request(`/api/v1/billing/invoices/${invoiceId}/pay`, {
            method: "POST",
        });
        return res.data;
    },

    // Webhooks & Sandbox Simulation
    async dispatchWebhook(rawBody, signatureHeader) {
        const res = await request("/api/v1/webhooks/stripe", {
            method: "POST",
            headers: {
                "Stripe-Signature": signatureHeader,
                "Content-Type": "application/json",
            },
            body: rawBody,
        });
        return res.data;
    },

    async getWebhookEvents() {
        const res = await request("/api/v1/webhooks/events");
        return res.data.events || [];
    },
};
