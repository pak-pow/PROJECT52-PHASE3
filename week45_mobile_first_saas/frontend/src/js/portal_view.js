/**
 * Portal View Controller
 * Customer billing portal managing active subscriptions, cancellation/resumption,
 * invoice statements, settlement actions, and printable receipts.
 */

"use strict";

import { Api } from "./api.js";

export const PortalView = {
    async render(container, onPortalUpdated) {
        this.container = container;
        this.onPortalUpdated = onPortalUpdated;

        try {
            const [subData, invoices] = await Promise.all([
                Api.getCurrentSubscription(),
                Api.getInvoices(),
            ]);
            this.subData = subData;
            this.invoices = invoices;
            this.buildUI();
        } catch (err) {
            container.innerHTML = `<div class="error-banner">Failed to load portal data: ${err.message}</div>`;
        }
    },

    buildUI() {
        const sub = this.subData.subscription;
        const plan = this.subData.plan;
        const daysRemaining = this.subData.days_remaining || 0;

        let subCardHtml = "";
        if (sub) {
            const statusClass = `status-${sub.status}`;
            const isCanceling = sub.cancel_at_period_end;

            subCardHtml = `
            <div class="portal-card subscription-detail-card">
                <div class="card-header-row">
                    <div>
                        <span class="sub-label">Current Subscription</span>
                        <h3 class="plan-heading">${plan.name} Plan</h3>
                    </div>
                    <span class="status-pill ${statusClass}">${sub.status.toUpperCase()}</span>
                </div>
                <div class="sub-meta-grid">
                    <div class="meta-item">
                        <span class="meta-label">Billing Cycle</span>
                        <span class="meta-value">${sub.billing_interval.toUpperCase()}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Days Remaining</span>
                        <span class="meta-value">${daysRemaining} Days</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Period Ends</span>
                        <span class="meta-value">${sub.current_period_end.substring(0, 10)}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Scheduled Cancel</span>
                        <span class="meta-value">${isCanceling ? 'YES (at period end)' : 'No'}</span>
                    </div>
                </div>

                <div class="sub-actions-row">
                    ${isCanceling || sub.status === 'canceled' ? `
                        <button id="resume-sub-btn" class="action-btn success">Resume Subscription</button>
                    ` : `
                        <button id="cancel-sub-btn" class="action-btn danger">Cancel Subscription</button>
                    `}
                </div>
            </div>
            `;
        } else {
            subCardHtml = `
            <div class="portal-card subscription-detail-card">
                <div class="card-header-row">
                    <div>
                        <span class="sub-label">Account Tier</span>
                        <h3 class="plan-heading">Free Tier</h3>
                    </div>
                    <span class="status-pill status-active">ACTIVE</span>
                </div>
                <p class="sub-description">You are currently using the default free tier. Upgrade to unlock custom domains, team seats, and expanded API quotas.</p>
            </div>
            `;
        }

        let invoicesHtml = "";
        if (this.invoices.length === 0) {
            invoicesHtml = `<div class="empty-state">No past invoice statements found.</div>`;
        } else {
            const rows = this.invoices.map((inv) => {
                const dateStr = (inv.created_at || "").substring(0, 10);
                const amtStr = `$${(inv.amount_due_cents / 100).toFixed(2)}`;
                const statusPill = inv.status === "paid" 
                    ? `<span class="pill-paid">PAID</span>` 
                    : `<span class="pill-open">${inv.status.toUpperCase()}</span>`;

                const payBtn = inv.status === "open"
                    ? `<button class="btn-table-action pay-btn" data-pay-id="${inv.id}">Pay Now</button>`
                    : "";

                return `
                <tr>
                    <td class="col-num">${inv.invoice_number}</td>
                    <td class="col-date">${dateStr}</td>
                    <td class="col-amt">${amtStr}</td>
                    <td class="col-status">${statusPill}</td>
                    <td class="col-actions">
                        <button class="btn-table-action receipt-btn" data-receipt-id="${inv.id}">Receipt</button>
                        <a href="/api/v1/billing/invoices/${inv.id}/html" target="_blank" class="btn-table-action print-btn">Print</a>
                        ${payBtn}
                    </td>
                </tr>
                `;
            }).join("");

            invoicesHtml = `
            <div class="table-responsive">
                <table class="invoices-table">
                    <thead>
                        <tr>
                            <th>Invoice</th>
                            <th>Date</th>
                            <th>Amount</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
            `;
        }

        this.container.innerHTML = `
        <div class="portal-view">
            <div class="view-header">
                <h2>Customer Billing Portal</h2>
                <p class="view-subtitle">Manage payment statements, recurring intervals, and printable receipts.</p>
            </div>

            ${subCardHtml}

            <div class="portal-card history-card">
                <h3 class="card-section-title">Invoice & Payment History</h3>
                ${invoicesHtml}
            </div>
        </div>
        `;

        this.bindEvents();
    },

    bindEvents() {
        const cancelBtn = this.container.querySelector("#cancel-sub-btn");
        if (cancelBtn) {
            cancelBtn.addEventListener("click", async () => {
                const confirmed = confirm("Are you sure you want to cancel? Your access will continue until the end of your billing cycle.");
                if (confirmed) {
                    try {
                        await Api.cancelSubscription(false);
                        window.showToast("Subscription scheduled for cancellation at period end.");
                        if (this.onPortalUpdated) this.onPortalUpdated();
                        await this.render(this.container, this.onPortalUpdated);
                    } catch (err) {
                        window.showToast(`Cancellation error: ${err.message}`, "error");
                    }
                }
            });
        }

        const resumeBtn = this.container.querySelector("#resume-sub-btn");
        if (resumeBtn) {
            resumeBtn.addEventListener("click", async () => {
                try {
                    await Api.resumeSubscription();
                    window.showToast("Subscription reactivated successfully!");
                    if (this.onPortalUpdated) this.onPortalUpdated();
                    await this.render(this.container, this.onPortalUpdated);
                } catch (err) {
                    window.showToast(`Resume error: ${err.message}`, "error");
                }
            });
        }

        this.container.querySelectorAll("[data-pay-id]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const invId = btn.getAttribute("data-pay-id");
                btn.disabled = true;
                btn.textContent = "Paying...";
                try {
                    const res = await Api.payInvoice(invId);
                    window.showToast("Invoice settled! Subscription active.");
                    if (this.onPortalUpdated) this.onPortalUpdated();
                    await this.render(this.container, this.onPortalUpdated);
                } catch (err) {
                    window.showToast(`Payment error: ${err.message}`, "error");
                }
            });
        });

        this.container.querySelectorAll("[data-receipt-id]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const invId = btn.getAttribute("data-receipt-id");
                await this.openReceiptModal(invId);
            });
        });
    },

    async openReceiptModal(invoiceId) {
        const modal = document.getElementById("bottom-modal");
        const modalTitle = document.getElementById("modal-title");
        const modalBody = document.getElementById("modal-body");
        const modalConfirmBtn = document.getElementById("modal-confirm-btn");

        if (!modal || !modalBody) return;

        modalTitle.textContent = "Statement Receipt";
        modalBody.innerHTML = `<div class="loading-spinner">Loading invoice receipt...</div>`;
        modal.classList.add("open");

        try {
            const data = await Api.getInvoiceReceipt(invoiceId);

            const itemsHtml = (data.line_items || []).map((it) => `
                <div class="receipt-item-row">
                    <div>
                        <strong>${it.description}</strong>
                        <span class="item-qty">Qty: ${it.quantity}</span>
                    </div>
                    <span class="item-amount">$${((it.unit_amount_cents * it.quantity) / 100).toFixed(2)}</span>
                </div>
            `).join("");

            modalBody.innerHTML = `
            <div class="receipt-modal-content">
                <div class="receipt-header-box">
                    <span class="receipt-inv-num">${data.invoice_number}</span>
                    <span class="receipt-status ${data.status === 'paid' ? 'status-paid' : 'status-open'}">${data.status.toUpperCase()}</span>
                </div>
                <div class="receipt-customer-box">
                    <p><strong>Billed To:</strong> ${data.customer_name || 'Customer'}</p>
                    <p><strong>Email:</strong> ${data.customer_email || 'customer@pulsesub.io'}</p>
                    <p><strong>Date:</strong> ${data.created_at.substring(0, 10)}</p>
                </div>
                <div class="receipt-items-box">
                    ${itemsHtml}
                </div>
                <div class="receipt-total-box">
                    <span>Total Paid:</span>
                    <span class="total-bold">${data.amount_paid_formatted}</span>
                </div>
            </div>
            `;

            modalConfirmBtn.textContent = "Open Printable Receipt";
            modalConfirmBtn.onclick = () => {
                window.open(`/api/v1/billing/invoices/${invoiceId}/html`, "_blank");
            };
        } catch (err) {
            modalBody.innerHTML = `<div class="error-banner">Failed to load receipt: ${err.message}</div>`;
        }
    },
};
