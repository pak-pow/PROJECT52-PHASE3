import { escapeHtml, formatCurrency, getIcon } from "../utils/helpers.js";

/**
 * Interactive Checkout Modal Component with Payment Simulation.
 */
export function initCheckoutModal({ onSubmitCheckout }) {
  const mount = document.getElementById("modal-mount");
  if (!mount) return null;

  let currentCart = null;

  mount.innerHTML = `
    <div id="checkout-modal-overlay" class="modal-overlay" aria-hidden="true">
      <div class="modal-card" role="dialog" aria-labelledby="checkout-modal-title">
        <header class="modal-header">
          <div class="modal-title-group">
            <h2 id="checkout-modal-title" class="modal-title">Complete Your Order</h2>
            <span class="modal-subtitle">Fast and secure mock checkout simulation</span>
          </div>
          <button type="button" id="modal-close-btn" class="modal-close-btn" aria-label="Close checkout modal">
            ${getIcon("close", 18)}
          </button>
        </header>

        <form id="checkout-form" class="checkout-form">
          <div class="modal-body">
            <div class="form-row">
              <div class="form-group">
                <label for="checkout-name" class="form-label">Full Name</label>
                <input type="text" id="checkout-name" class="form-input" placeholder="Alex Morgan" required autocomplete="name">
              </div>
              <div class="form-group">
                <label for="checkout-email" class="form-label">Email Address</label>
                <input type="email" id="checkout-email" class="form-input" placeholder="alex.morgan@example.com" required autocomplete="email">
              </div>
            </div>

            <div class="form-group">
              <label for="checkout-address" class="form-label">Shipping Address</label>
              <textarea id="checkout-address" class="form-input" rows="2" placeholder="104 Market St, Suite 400, San Francisco, CA 94105" required autocomplete="street-address"></textarea>
            </div>

            <div class="simulation-box">
              <span class="simulation-box-title">Select Payment Simulation Scenario</span>
              <div class="simulation-options">
                <label class="simulation-option-label selected" id="label-scenario-success">
                  <input type="radio" name="payment_scenario" value="success" checked>
                  <span class="scenario-name">Success</span>
                  <span class="scenario-card-num">Visa ...4242</span>
                </label>
                <label class="simulation-option-label" id="label-scenario-decline">
                  <input type="radio" name="payment_scenario" value="decline">
                  <span class="scenario-name">Decline</span>
                  <span class="scenario-card-num">Visa ...0002</span>
                </label>
                <label class="simulation-option-label" id="label-scenario-funds">
                  <input type="radio" name="payment_scenario" value="insufficient_funds">
                  <span class="scenario-name">No Funds</span>
                  <span class="scenario-card-num">Visa ...9995</span>
                </label>
              </div>
            </div>

            <div class="summary-table">
              <div class="summary-row total-row">
                <span>Total Due Now</span>
                <span id="checkout-total-cents" class="summary-value">$0.00</span>
              </div>
            </div>
          </div>

          <footer class="modal-footer">
            <button type="button" id="modal-cancel-btn" class="category-tab-btn">Cancel</button>
            <button type="submit" id="btn-submit-payment" class="btn-checkout">
              ${getIcon("card", 16)}
              <span id="btn-pay-text">Authorize & Pay</span>
            </button>
          </footer>
        </form>
      </div>
    </div>
  `;

  const overlay = document.getElementById("checkout-modal-overlay");
  const closeBtn = document.getElementById("modal-close-btn");
  const cancelBtn = document.getElementById("modal-cancel-btn");
  const form = document.getElementById("checkout-form");
  const submitBtn = document.getElementById("btn-submit-payment");
  const submitText = document.getElementById("btn-pay-text");

  // Scenario radio selection styling
  const scenarioLabels = [
    document.getElementById("label-scenario-success"),
    document.getElementById("label-scenario-decline"),
    document.getElementById("label-scenario-funds"),
  ];

  scenarioLabels.forEach((label) => {
    if (!label) return;
    const radio = label.querySelector('input[type="radio"]');
    if (radio) {
      radio.addEventListener("change", () => {
        scenarioLabels.forEach((l) => l && l.classList.remove("selected"));
        if (radio.checked) {
          label.classList.add("selected");
        }
      });
    }
  });

  function open(cart) {
    currentCart = cart;
    const totalEl = document.getElementById("checkout-total-cents");
    if (totalEl && cart) {
      totalEl.textContent = formatCurrency(cart.total_cents);
    }
    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
  }

  function close() {
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
  }

  closeBtn.addEventListener("click", close);
  cancelBtn.addEventListener("click", close);

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      close();
    }
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && overlay.classList.contains("open")) {
      close();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const name = document.getElementById("checkout-name").value.trim();
    const email = document.getElementById("checkout-email").value.trim();
    const address = document.getElementById("checkout-address").value.trim();
    const scenarioRadio = form.querySelector('input[name="payment_scenario"]:checked');
    const scenario = scenarioRadio ? scenarioRadio.value : "success";

    if (!name || !email || !address) {
      return;
    }

    submitBtn.disabled = true;
    submitText.textContent = "Processing payment...";

    try {
      if (typeof onSubmitCheckout === "function") {
        await onSubmitCheckout({
          customer_name: name,
          customer_email: email,
          shipping_address: address,
          scenario,
        });
      }
      close();
    } catch (err) {
      // Error handled by parent with toast
    } finally {
      submitBtn.disabled = false;
      submitText.textContent = "Authorize & Pay";
    }
  });

  return {
    open,
    close,
  };
}
