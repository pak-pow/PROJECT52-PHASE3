import { escapeHtml, formatCurrency, getIcon } from "../utils/helpers.js";

/**
 * Slide-out Cart Drawer Component
 */
export function initCartDrawer({
  onUpdateQuantity,
  onRemoveItem,
  onApplyPromo,
  onRemovePromo,
  onCheckout,
}) {
  const mount = document.getElementById("cart-drawer-mount");
  if (!mount) return null;

  let currentCart = null;

  // Mount structure
  mount.innerHTML = `
    <div id="cart-overlay" class="cart-drawer-overlay" aria-hidden="true">
      <aside class="cart-drawer-panel" role="dialog" aria-label="Shopping Cart">
        <header class="cart-header">
          <div class="cart-header-title">
            ${getIcon("cart", 20)}
            <span>Your Cart</span>
            <span id="cart-item-count-badge" class="stock-tag stock-in">0 items</span>
          </div>
          <button type="button" id="cart-close-btn" class="cart-close-btn" aria-label="Close cart">
            ${getIcon("close", 18)}
          </button>
        </header>

        <section class="cart-shipping-meter">
          <p id="shipping-meter-text" class="shipping-meter-label">Add items to unlock free shipping</p>
          <div class="shipping-progress-track">
            <div id="shipping-progress-bar" class="shipping-progress-fill"></div>
          </div>
        </section>

        <div id="cart-items-list" class="cart-items-container">
          <!-- Items will render here -->
        </div>

        <footer class="cart-footer">
          <div id="promo-section" class="promo-section-wrap">
            <!-- Promo code input or active tag -->
          </div>

          <div class="summary-table">
            <div class="summary-row">
              <span>Subtotal</span>
              <span id="cart-subtotal" class="summary-value">$0.00</span>
            </div>
            <div id="cart-discount-row" class="summary-row discount-row hidden">
              <span>Discount</span>
              <span id="cart-discount" class="summary-value">-$0.00</span>
            </div>
            <div class="summary-row">
              <span>Estimated Tax (8.25%)</span>
              <span id="cart-tax" class="summary-value">$0.00</span>
            </div>
            <div class="summary-row">
              <span>Shipping</span>
              <span id="cart-shipping" class="summary-value">$0.00</span>
            </div>
            <div class="summary-row total-row">
              <span>Total</span>
              <span id="cart-total" class="summary-value">$0.00</span>
            </div>
          </div>

          <button type="button" id="btn-proceed-checkout" class="btn-checkout" disabled>
            <span>Proceed to Checkout</span>
            ${getIcon("arrowRight", 16)}
          </button>
        </footer>
      </aside>
    </div>
  `;

  const overlay = document.getElementById("cart-overlay");
  const closeBtn = document.getElementById("cart-close-btn");
  const checkoutBtn = document.getElementById("btn-proceed-checkout");

  function open() {
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

  checkoutBtn.addEventListener("click", () => {
    close();
    if (typeof onCheckout === "function") {
      onCheckout(currentCart);
    }
  });

  function render(cart) {
    currentCart = cart;
    if (!cart) return;

    // 1. Update Header count
    const countBadge = document.getElementById("cart-item-count-badge");
    const count = (cart.items || []).reduce((sum, i) => sum + i.quantity, 0);
    countBadge.textContent = `${count} ${count === 1 ? "item" : "items"}`;

    // 2. Update Free Shipping Meter ($50.00 = 5000 cents threshold)
    const shippingText = document.getElementById("shipping-meter-text");
    const shippingFill = document.getElementById("shipping-progress-bar");
    const pricing = cart.pricing || {};
    const subtotal = pricing.subtotal_cents || 0;
    const threshold = 5000;

    if (subtotal >= threshold) {
      shippingText.textContent = "You qualified for free standard shipping!";
      shippingFill.style.width = "100%";
    } else {
      const remaining = threshold - subtotal;
      const pct = Math.min(100, Math.round((subtotal / threshold) * 100));
      shippingText.textContent = `Add ${formatCurrency(remaining)} more for free shipping`;
      shippingFill.style.width = `${pct}%`;
    }

    // 3. Render Cart Items
    const itemsList = document.getElementById("cart-items-list");
    const items = cart.items || [];

    if (items.length === 0) {
      itemsList.innerHTML = `
        <div class="cart-empty-state">
          ${getIcon("cart", 36)}
          <p>Your shopping cart is empty.</p>
        </div>
      `;
      checkoutBtn.disabled = true;
    } else {
      checkoutBtn.disabled = false;
      itemsList.innerHTML = items
        .map(
          (item) => `
        <div class="cart-item-row" data-id="${item.product_id}">
          <img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.title)}" class="cart-item-image">
          <div class="cart-item-details">
            <div class="cart-item-title-row">
              <span class="cart-item-title">${escapeHtml(item.title)}</span>
              <span class="cart-item-price">${formatCurrency(item.price_cents * item.quantity)}</span>
            </div>
            <div class="cart-item-bottom-row">
              <div class="stepper-group">
                <button type="button" class="stepper-btn btn-qty-minus" data-id="${item.product_id}" data-qty="${item.quantity - 1}" ${item.quantity <= 1 ? "disabled" : ""} aria-label="Decrease quantity">
                  ${getIcon("minus", 12)}
                </button>
                <span class="stepper-qty">${item.quantity}</span>
                <button type="button" class="stepper-btn btn-qty-plus" data-id="${item.product_id}" data-qty="${item.quantity + 1}" ${item.quantity >= item.stock_quantity ? "disabled" : ""} aria-label="Increase quantity">
                  ${getIcon("plus", 12)}
                </button>
              </div>
              <button type="button" class="cart-item-remove-btn" data-id="${item.product_id}" aria-label="Remove ${escapeHtml(item.title)} from cart">
                ${getIcon("trash", 16)}
              </button>
            </div>
          </div>
        </div>
      `
        )
        .join("");

      // Quantity Minus Listeners
      itemsList.querySelectorAll(".btn-qty-minus").forEach((btn) => {
        btn.addEventListener("click", () => {
          const productId = parseInt(btn.getAttribute("data-id"), 10);
          const newQty = parseInt(btn.getAttribute("data-qty"), 10);
          if (newQty >= 1 && typeof onUpdateQuantity === "function") {
            onUpdateQuantity(productId, newQty);
          }
        });
      });

      // Quantity Plus Listeners
      itemsList.querySelectorAll(".btn-qty-plus").forEach((btn) => {
        btn.addEventListener("click", () => {
          const productId = parseInt(btn.getAttribute("data-id"), 10);
          const newQty = parseInt(btn.getAttribute("data-qty"), 10);
          if (typeof onUpdateQuantity === "function") {
            onUpdateQuantity(productId, newQty);
          }
        });
      });

      // Remove Listeners
      itemsList.querySelectorAll(".cart-item-remove-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const productId = parseInt(btn.getAttribute("data-id"), 10);
          if (typeof onRemoveItem === "function") {
            onRemoveItem(productId);
          }
        });
      });
    }

    // 4. Promo Section
    const promoSection = document.getElementById("promo-section");
    if (cart.promo_code) {
      promoSection.innerHTML = `
        <div class="promo-active-tag">
          <span>Active Code: <strong>${escapeHtml(cart.promo_code)}</strong></span>
          <span id="btn-remove-promo" class="promo-remove-link" role="button" tabindex="0">Remove</span>
        </div>
      `;
      const removePromoBtn = document.getElementById("btn-remove-promo");
      if (removePromoBtn) {
        removePromoBtn.addEventListener("click", () => {
          if (typeof onRemovePromo === "function") {
            onRemovePromo();
          }
        });
      }
    } else {
      promoSection.innerHTML = `
        <form id="promo-code-form" class="promo-form">
          <input type="text" id="promo-code-input" class="promo-input" placeholder="Promo code (e.g. DISCOUNT10)" maxlength="20">
          <button type="submit" class="promo-apply-btn">Apply</button>
        </form>
      `;
      const promoForm = document.getElementById("promo-code-form");
      const promoInput = document.getElementById("promo-code-input");
      if (promoForm && promoInput) {
        promoForm.addEventListener("submit", (e) => {
          e.preventDefault();
          const code = promoInput.value.trim().toUpperCase();
          if (code && typeof onApplyPromo === "function") {
            onApplyPromo(code);
          }
        });
      }
    }

    // 5. Cost Breakdown
    document.getElementById("cart-subtotal").textContent = formatCurrency(pricing.subtotal_cents);

    const discountRow = document.getElementById("cart-discount-row");
    const discountVal = document.getElementById("cart-discount");
    if (pricing.discount_cents && pricing.discount_cents > 0) {
      discountRow.classList.remove("hidden");
      discountVal.textContent = `-${formatCurrency(pricing.discount_cents)}`;
    } else {
      discountRow.classList.add("hidden");
    }

    document.getElementById("cart-tax").textContent = formatCurrency(pricing.tax_cents);
    document.getElementById("cart-shipping").textContent =
      pricing.shipping_cents === 0 ? "FREE" : formatCurrency(pricing.shipping_cents);
    document.getElementById("cart-total").textContent = formatCurrency(pricing.total_cents);
  }

  return {
    open,
    close,
    render,
  };
}
