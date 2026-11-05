/**
 * Sandbox Console View Controller
 * Interactive Stripe Webhook & Billing Event Simulator.
 * Computes authentic HMAC-SHA256 signatures via Web Crypto API and dispatches real webhooks.
 */

"use strict";

import { Api } from "./api.js";

const DEFAULT_SECRET = "whsec_pulsesub_test_secret_key_2026";

async function computeHmacSha256(secret, message) {
    const encoder = new TextEncoder();
    const keyData = encoder.encode(secret);
    const msgData = encoder.encode(message);

    const cryptoKey = await window.crypto.subtle.importKey(
        "raw",
        keyData,
        { name: "HMAC", hash: { name: "SHA-256" } },
        false,
        ["sign"]
    );

    const signatureBuffer = await window.crypto.subtle.sign("HMAC", cryptoKey, msgData);
    const hashArray = Array.from(new Uint8Array(signatureBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export const SandboxConsole = {
    selectedTemplate: "payment_failed",

    getTemplates(userId, subId, invoiceId) {
        const uId = userId || "usr_demo_alice";
        const sId = subId || "sub_demo_alice_pro";
        const invId = invoiceId || "inv_demo_2026_0001";
        const nowSec = Math.floor(Date.now() / 1000);

        return {
            payment_failed: {
                id: `evt_fail_${Date.now()}`,
                type: "invoice.payment_failed",
                data: {
                    object: {
                        id: invId,
                        customer: uId,
                        subscription: sId,
                        amount_due: 4900,
                        attempt_count: 1,
                        next_payment_attempt: nowSec + 86400 * 3,
                    },
                },
            },
            invoice_paid: {
                id: `evt_paid_${Date.now()}`,
                type: "invoice.paid",
                data: {
                    object: {
                        id: invId,
                        customer: uId,
                        subscription: sId,
                        amount_paid: 4900,
                        status: "paid",
                    },
                },
            },
            subscription_updated: {
                id: `evt_upd_${Date.now()}`,
                type: "customer.subscription.updated",
                data: {
                    object: {
                        id: sId,
                        customer: uId,
                        plan: { id: "plan_enterprise" },
                        billing_interval: "annual",
                        status: "active",
                        current_period_start: nowSec - 86400 * 5,
                        current_period_end: nowSec + 86400 * 360,
                        cancel_at_period_end: false,
                    },
                },
            },
            subscription_deleted: {
                id: `evt_del_${Date.now()}`,
                type: "customer.subscription.deleted",
                data: {
                    object: {
                        id: sId,
                        customer: uId,
                        status: "canceled",
                    },
                },
            },
        };
    },

    async render(container, onWebhookDispatched) {
        this.container = container;
        this.onWebhookDispatched = onWebhookDispatched;

        try {
            const [subData, invoices, events] = await Promise.all([
                Api.getCurrentSubscription(),
                Api.getInvoices(),
                Api.getWebhookEvents(),
            ]);
            this.subData = subData;
            this.invoices = invoices;
            this.events = events;

            const uId = subData.user_id;
            const sId = subData.subscription ? subData.subscription.id : "sub_demo_alice_pro";
            const invId = invoices.length > 0 ? invoices[0].id : "inv_demo_2026_0001";
            this.templates = this.getTemplates(uId, sId, invId);

            this.buildUI();
        } catch (err) {
            container.innerHTML = `<div class="error-banner">Failed to initialize Sandbox: ${err.message}</div>`;
        }
    },

    buildUI() {
        const initialJson = JSON.stringify(this.templates[this.selectedTemplate], null, 2);

        let eventRows = "";
        if (this.events.length === 0) {
            eventRows = `<tr><td colspan="4" class="empty-state">No webhook events logged yet.</td></tr>`;
        } else {
            eventRows = this.events.slice(0, 10).map((ev) => `
                <tr>
                    <td class="col-type">${ev.event_type}</td>
                    <td class="col-status"><span class="pill-${ev.status}">${ev.status.toUpperCase()}</span></td>
                    <td class="col-id">${ev.event_id}</td>
                    <td class="col-time">${(ev.received_at || '').substring(11, 19)}</td>
                </tr>
            `).join("");
        }

        this.container.innerHTML = `
        <div class="sandbox-view">
            <div class="view-header">
                <h2>Billing Sandbox & Webhook Simulator</h2>
                <p class="view-subtitle">Simulate external Stripe webhook events and observe real-time subscription reactions.</p>
            </div>

            <div class="sandbox-grid">
                <!-- Left: Event Composer -->
                <div class="sandbox-card composer-card">
                    <div class="composer-header">
                        <label for="template-select">Select Lifecycle Event Template:</label>
                        <select id="template-select" class="sandbox-select">
                            <option value="payment_failed" ${this.selectedTemplate === 'payment_failed' ? 'selected' : ''}>invoice.payment_failed (Trigger Past Due)</option>
                            <option value="invoice_paid" ${this.selectedTemplate === 'invoice_paid' ? 'selected' : ''}>invoice.paid (Reactivate Subscription)</option>
                            <option value="subscription_updated" ${this.selectedTemplate === 'subscription_updated' ? 'selected' : ''}>customer.subscription.updated (Sync Tier)</option>
                            <option value="subscription_deleted" ${this.selectedTemplate === 'subscription_deleted' ? 'selected' : ''}>customer.subscription.deleted (Cancel)</option>
                        </select>
                    </div>

                    <div class="editor-block">
                        <label for="payload-editor">Raw JSON Payload:</label>
                        <textarea id="payload-editor" class="sandbox-editor" rows="12">${initialJson}</textarea>
                    </div>

                    <div class="composer-actions">
                        <button id="dispatch-webhook-btn" class="action-btn primary">
                            Dispatch Webhook to Gateway
                        </button>
                    </div>

                    <div id="sandbox-log-box" class="sandbox-log-box hidden">
                        <h4>Dispatch Execution Log</h4>
                        <pre id="sandbox-log-content"></pre>
                    </div>
                </div>

                <!-- Right: Recent Webhook Events Log -->
                <div class="sandbox-card history-card">
                    <h3 class="card-section-title">Inbound Webhook Audit Log</h3>
                    <div class="table-responsive">
                        <table class="events-table">
                            <thead>
                                <tr>
                                    <th>Event</th>
                                    <th>Status</th>
                                    <th>Event ID</th>
                                    <th>Time</th>
                                </tr>
                            </thead>
                            <tbody id="events-log-tbody">
                                ${eventRows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        `;

        this.bindEvents();
    },

    bindEvents() {
        const select = this.container.querySelector("#template-select");
        const editor = this.container.querySelector("#payload-editor");
        if (select && editor) {
            select.addEventListener("change", () => {
                this.selectedTemplate = select.value;
                editor.value = JSON.stringify(this.templates[this.selectedTemplate], null, 2);
            });
        }

        const dispatchBtn = this.container.querySelector("#dispatch-webhook-btn");
        if (dispatchBtn && editor) {
            dispatchBtn.addEventListener("click", async () => {
                const rawPayload = editor.value.trim();
                await this.executeDispatch(rawPayload);
            });
        }
    },

    async executeDispatch(rawPayload) {
        const logBox = this.container.querySelector("#sandbox-log-box");
        const logContent = this.container.querySelector("#sandbox-log-content");
        const dispatchBtn = this.container.querySelector("#dispatch-webhook-btn");

        try {
            dispatchBtn.disabled = true;
            dispatchBtn.textContent = "Signing & Dispatching...";

            // 1. Generate timestamp and HMAC-SHA256 signature
            const timestamp = Math.floor(Date.now() / 1000);
            const signedPayload = `${timestamp}.${rawPayload}`;
            const signature = await computeHmacSha256(DEFAULT_SECRET, signedPayload);
            const signatureHeader = `t=${timestamp},v1=${signature}`;

            // 2. Dispatch to backend webhook gateway
            const result = await Api.dispatchWebhook(rawPayload, signatureHeader);

            if (logBox && logContent) {
                logBox.classList.remove("hidden");
                logContent.textContent = JSON.stringify({
                    request_header: signatureHeader,
                    gateway_response: result,
                }, null, 2);
            }

            window.showToast(`Webhook executed: ${result.event_type || 'Event'} (${result.status})`);
            if (this.onWebhookDispatched) this.onWebhookDispatched();
            await this.render(this.container, this.onWebhookDispatched);
        } catch (err) {
            window.showToast(`Webhook dispatch failed: ${err.message}`, "error");
            if (logBox && logContent) {
                logBox.classList.remove("hidden");
                logContent.textContent = `Error: ${err.message}`;
            }
        } finally {
            if (dispatchBtn) {
                dispatchBtn.disabled = false;
                dispatchBtn.textContent = "Dispatch Webhook to Gateway";
            }
        }
    },
};
