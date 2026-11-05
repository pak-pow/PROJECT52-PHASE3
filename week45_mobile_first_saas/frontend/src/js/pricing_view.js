/**
 * Pricing View Controller
 * Plan comparison matrix with Monthly/Annual discount switch and live proration bottom-sheet modal.
 */

"use strict";

import { Api } from "./api.js";

export const PricingView = {
    interval: "monthly",
    plans: [],
    currentSub: null,
    targetPlanForUpgrade: null,

    async render(container, onSubUpdated) {
        this.container = container;
        this.onSubUpdated = onSubUpdated;

        try {
            const [plans, subData] = await Promise.all([
                Api.getPlans(),
                Api.getCurrentSubscription(),
            ]);
            this.plans = plans;
            this.currentSub = subData.subscription;
            this.currentPlan = subData.plan;

            this.buildUI();
        } catch (err) {
            container.innerHTML = `<div class="error-banner">Failed to load plans: ${err.message}</div>`;
        }
    },

    buildUI() {
        const isAnnual = this.interval === "annual";
        const currentPlanId = this.currentPlan ? this.currentPlan.id : "plan_free";

        let cardsHtml = "";
        for (const plan of this.plans) {
            const isCurrent = plan.id === currentPlanId;
            const priceCents = isAnnual ? plan.price_annual_cents : plan.price_monthly_cents;
            const priceStr = priceCents === 0 ? "$0" : `$${(priceCents / 100).toFixed(0)}`;
            const periodStr = priceCents === 0 ? "forever" : isAnnual ? "/ year" : "/ month";

            const limitsHtml = Object.entries(plan.limits || {})
                .map(([k, v]) => {
                    const label = k.replace(/_/g, " ");
                    const val = v === -1 ? "Unlimited" : v.toLocaleString();
                    return `<li class="limit-item"><strong>${val}</strong> <span>${label}</span></li>`;
                })
                .join("");

            const featuresHtml = (plan.features || [])
                .map((f) => `<li class="feature-item"><span class="check-icon">&#10003;</span> ${f.replace(/_/g, " ")}</li>`)
                .join("");

            let actionBtn = "";
            if (isCurrent) {
                actionBtn = `<button class="plan-btn current" disabled>Current Plan</button>`;
            } else if (!this.currentSub || this.currentPlan.tier === "free") {
                actionBtn = `<button class="plan-btn primary" data-subscribe="${plan.id}">Subscribe</button>`;
            } else {
                actionBtn = `<button class="plan-btn outline" data-switch="${plan.id}">Switch Tier</button>`;
            }

            cardsHtml += `
            <div class="pricing-card ${isCurrent ? 'current-card' : ''}" data-plan-id="${plan.id}">
                ${isCurrent ? '<span class="current-badge">ACTIVE</span>' : ''}
                <div class="card-header">
                    <h3 class="tier-name">${plan.name}</h3>
                    <div class="price-block">
                        <span class="price-val">${priceStr}</span>
                        <span class="price-period">${periodStr}</span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="limits-group">
                        <span class="group-title">Resource Quotas</span>
                        <ul class="limits-list">${limitsHtml}</ul>
                    </div>
                    <div class="features-group">
                        <span class="group-title">Included Capabilities</span>
                        <ul class="features-list">${featuresHtml}</ul>
                    </div>
                </div>
                <div class="card-footer">
                    ${actionBtn}
                </div>
            </div>
            `;
        }

        this.container.innerHTML = `
        <div class="pricing-view">
            <div class="view-header">
                <h2>Subscription Plans</h2>
                <p class="view-subtitle">Select a tier tailored to your workflow and team scale.</p>
                <div class="interval-switch-container">
                    <button class="interval-btn ${!isAnnual ? 'active' : ''}" data-interval="monthly">Monthly</button>
                    <button class="interval-btn ${isAnnual ? 'active' : ''}" data-interval="annual">
                        Annual <span class="discount-pill">Save 20%</span>
                    </button>
                </div>
            </div>
            <div class="pricing-grid">
                ${cardsHtml}
            </div>
        </div>
        `;

        this.bindEvents();
    },

    bindEvents() {
        // Interval toggles
        const intervalBtns = this.container.querySelectorAll(".interval-btn");
        intervalBtns.forEach((btn) => {
            btn.addEventListener("click", () => {
                const targetInterval = btn.getAttribute("data-interval");
                if (targetInterval !== this.interval) {
                    this.interval = targetInterval;
                    this.buildUI();
                }
            });
        });

        // Subscribe / Switch buttons
        this.container.querySelectorAll("[data-subscribe]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const planId = btn.getAttribute("data-subscribe");
                await this.executeSubscribe(planId);
            });
        });

        this.container.querySelectorAll("[data-switch]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const planId = btn.getAttribute("data-switch");
                await this.openProrationModal(planId);
            });
        });
    },

    async executeSubscribe(planId) {
        try {
            const res = await Api.subscribe(planId, this.interval);
            window.showToast(`Subscribed to ${res.subscription.plan_id} successfully!`);
            if (this.onSubUpdated) this.onSubUpdated();
            await this.render(this.container, this.onSubUpdated);
        } catch (err) {
            window.showToast(`Subscription error: ${err.message}`, "error");
        }
    },

    async openProrationModal(targetPlanId) {
        const modal = document.getElementById("bottom-modal");
        const modalTitle = document.getElementById("modal-title");
        const modalBody = document.getElementById("modal-body");
        const modalConfirmBtn = document.getElementById("modal-confirm-btn");

        if (!modal || !modalBody) return;

        modalTitle.textContent = "Preview Plan Change & Proration";
        modalBody.innerHTML = `<div class="loading-spinner">Calculating real-time proration...</div>`;
        modal.classList.add("open");

        try {
            const preview = await Api.changeTier(targetPlanId, this.interval, true);
            const p = preview.proration;

            const formatMoney = (cents) => {
                const sign = cents < 0 ? "-" : "";
                return `${sign}$${(Math.abs(cents) / 100).toFixed(2)}`;
            };

            const itemsHtml = (p.line_items || p.to_line_items || [])
                .map((it) => `
                <div class="proration-line-item">
                    <span>${it.description}</span>
                    <strong class="${it.unit_amount_cents < 0 ? 'text-credit' : ''}">${formatMoney(it.unit_amount_cents)}</strong>
                </div>
            `).join("") || `
                <div class="proration-line-item">
                    <span>Unused credit on ${p.current_plan_name}</span>
                    <strong class="text-credit">-${formatMoney(p.unused_credit_cents)}</strong>
                </div>
                <div class="proration-line-item">
                    <span>Charge for remainder on ${p.new_plan_name}</span>
                    <strong>${formatMoney(p.new_plan_charge_cents)}</strong>
                </div>
            `;

            modalBody.innerHTML = `
            <div class="proration-breakdown">
                <div class="plans-transition">
                    <span class="pill-plan">${p.current_plan_name}</span>
                    <span class="arrow-icon">&rarr;</span>
                    <span class="pill-plan highlight">${p.new_plan_name}</span>
                </div>
                <div class="items-list">
                    ${itemsHtml}
                </div>
                <div class="proration-total">
                    <span>Net Amount Due Today:</span>
                    <span class="total-amount">${formatMoney(p.net_amount_due_cents)}</span>
                </div>
                ${p.credit_remaining_cents > 0 ? `
                <div class="credit-banner">
                    Account balance credit remaining: ${formatMoney(p.credit_remaining_cents)}
                </div>` : ''}
            </div>
            `;

            modalConfirmBtn.textContent = p.is_upgrade ? "Confirm & Upgrade" : "Confirm Plan Change";
            modalConfirmBtn.onclick = async () => {
                modalConfirmBtn.disabled = true;
                modalConfirmBtn.textContent = "Processing...";
                try {
                    await Api.changeTier(targetPlanId, this.interval, false);
                    window.showToast(`Plan successfully changed to ${p.new_plan_name}!`);
                    modal.classList.remove("open");
                    if (this.onSubUpdated) this.onSubUpdated();
                    await this.render(this.container, this.onSubUpdated);
                } catch (err) {
                    window.showToast(`Failed to update tier: ${err.message}`, "error");
                } finally {
                    modalConfirmBtn.disabled = false;
                }
            };
        } catch (err) {
            modalBody.innerHTML = `<div class="error-banner">Proration calculation error: ${err.message}</div>`;
        }
    },
};
