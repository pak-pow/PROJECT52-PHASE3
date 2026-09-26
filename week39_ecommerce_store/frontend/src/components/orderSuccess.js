import { escapeHtml, formatCurrency, getIcon } from "../utils/helpers.js";

/**
 * Order Confirmation & Success View Component.
 */
export function initOrderSuccess({ onDone }) {
  const mount = document.getElementById("modal-mount");
  if (!mount) return null;

  function show(order) {
    const isPaid = order.status === "paid";
    const statusClass = isPaid ? "status-paid" : "status-cancelled";
    const statusText = isPaid ? "Payment Confirmed" : "Order Cancelled";

    const modalMarkup = `
      <div id="order-success-overlay" class="modal-overlay open" aria-modal="true" role="dialog">
        <div class="modal-card">
          <header class="modal-header">
            <div class="modal-title-group">
              <h2 class="modal-title">Order Summary</h2>
              <span class="modal-subtitle">Transaction reference: ${escapeHtml(order.order_number)}</span>
            </div>
            <button type="button" id="order-modal-close-btn" class="modal-close-btn" aria-label="Close dialog">
              ${getIcon("close", 18)}
            </button>
          </header>

          <div class="modal-body">
            <div class="order-badge-row">
              <span class="order-status-badge ${statusClass}">
                ${getIcon(isPaid ? "check" : "alert", 14)}
                <span>${statusText}</span>
              </span>
              <span class="catalog-count">${escapeHtml(order.created_at || "")}</span>
            </div>

            <div class="order-info-grid">
              <div class="order-info-item">
                <span class="order-info-label">Customer</span>
                <span class="order-info-val">${escapeHtml(order.customer_name)}</span>
              </div>
              <div class="order-info-item">
                <span class="order-info-label">Email</span>
                <span class="order-info-val">${escapeHtml(order.customer_email)}</span>
              </div>
              <div class="order-info-item">
                <span class="order-info-label">Shipping Destination</span>
                <span class="order-info-val">${escapeHtml(order.shipping_address)}</span>
              </div>
              <div class="order-info-item">
                <span class="order-info-label">Payment ID</span>
                <span class="order-info-val">${escapeHtml(order.payment_intent_id || "N/A")}</span>
              </div>
            </div>

            <table class="order-items-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th class="text-right">Qty</th>
                  <th class="text-right">Price</th>
                  <th class="text-right">Subtotal</th>
                </tr>
              </thead>
              <tbody>
                ${(order.items || [])
                  .map(
                    (it) => `
                  <tr>
                    <td>${escapeHtml(it.product_title)}</td>
                    <td class="text-right">${it.quantity}</td>
                    <td class="text-right">${formatCurrency(it.price_cents)}</td>
                    <td class="text-right">${formatCurrency(it.line_total_cents)}</td>
                  </tr>
                `
                  )
                  .join("")}
              </tbody>
            </table>

            <div class="summary-table">
              <div class="summary-row">
                <span>Subtotal</span>
                <span class="summary-value">${formatCurrency(order.subtotal_cents)}</span>
              </div>
              ${
                order.discount_cents > 0
                  ? `
                <div class="summary-row discount-row">
                  <span>Discount (${escapeHtml(order.promo_code || "")})</span>
                  <span class="summary-value">-${formatCurrency(order.discount_cents)}</span>
                </div>
              `
                  : ""
              }
              <div class="summary-row">
                <span>Tax</span>
                <span class="summary-value">${formatCurrency(order.tax_cents)}</span>
              </div>
              <div class="summary-row">
                <span>Shipping</span>
                <span class="summary-value">${order.shipping_cents === 0 ? "FREE" : formatCurrency(order.shipping_cents)}</span>
              </div>
              <div class="summary-row total-row">
                <span>Total Paid</span>
                <span class="summary-value">${formatCurrency(order.total_cents)}</span>
              </div>
            </div>
          </div>

          <footer class="modal-footer">
            <button type="button" id="btn-print-invoice" class="category-tab-btn">
              ${getIcon("printer", 16)}
              <span>Print Invoice</span>
            </button>
            <button type="button" id="btn-order-done" class="btn-checkout">
              <span>Continue Shopping</span>
            </button>
          </footer>
        </div>
      </div>
    `;

    mount.innerHTML = modalMarkup;

    const overlay = document.getElementById("order-success-overlay");
    const closeBtn = document.getElementById("order-modal-close-btn");
    const doneBtn = document.getElementById("btn-order-done");
    const printBtn = document.getElementById("btn-print-invoice");

    function close() {
      overlay.classList.remove("open");
      mount.innerHTML = "";
      if (typeof onDone === "function") {
        onDone();
      }
    }

    closeBtn.addEventListener("click", close);
    doneBtn.addEventListener("click", close);

    printBtn.addEventListener("click", () => {
      window.print();
    });

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        close();
      }
    });
  }

  return {
    show,
  };
}
