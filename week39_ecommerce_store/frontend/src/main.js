import { StoreApi } from "./api/storeApi.js";
import { initCartDrawer } from "./components/cartDrawer.js";
import { initCheckoutModal } from "./components/checkoutModal.js";
import { initNavbar } from "./components/navbar.js";
import { initOrderSuccess } from "./components/orderSuccess.js";
import { initProductGrid } from "./components/productGrid.js";
import { showToast } from "./components/toast.js";
import { clearStoredCartToken, escapeHtml } from "./utils/helpers.js";

/**
 * Application State
 */
const state = {
  activeCategory: "",
  searchQuery: "",
  sortOrder: "",
  products: [],
  cart: null,
};

let navbar;
let productGrid;
let cartDrawer;
let checkoutModal;
let orderSuccess;

/**
 * Initializes the application on DOM ready.
 */
document.addEventListener("DOMContentLoaded", async () => {
  // 1. Initialize Components
  navbar = initNavbar({
    onCartClick: () => {
      cartDrawer.open();
    },
  });

  productGrid = initProductGrid({
    onAddToCart: handleAddToCart,
  });

  cartDrawer = initCartDrawer({
    onUpdateQuantity: handleUpdateQuantity,
    onRemoveItem: handleRemoveItem,
    onApplyPromo: handleApplyPromo,
    onRemovePromo: handleRemovePromo,
    onCheckout: handleStartCheckout,
  });

  checkoutModal = initCheckoutModal({
    onSubmitCheckout: handleSubmitCheckout,
  });

  orderSuccess = initOrderSuccess({
    onDone: () => {
      loadProducts();
      loadCart();
    },
  });

  // 2. Attach Controls (Search & Sort)
  setupControls();

  // 3. Load Initial Data
  await Promise.all([loadCategories(), loadProducts(), loadCart()]);
});

/**
 * Set up search debounce and sort select handlers.
 */
function setupControls() {
  const searchInput = document.getElementById("search-input");
  const sortSelect = document.getElementById("sort-select");

  let searchTimeout = null;
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        state.searchQuery = e.target.value.trim();
        loadProducts();
      }, 250);
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener("change", (e) => {
      state.sortOrder = e.target.value;
      loadProducts();
    });
  }
}

/**
 * Fetches and renders category tab buttons.
 */
async function loadCategories() {
  const container = document.getElementById("category-tabs");
  if (!container) return;

  try {
    const res = await StoreApi.fetchCategories();
    const categories = (res && res.data) || [];

    const tabsHtml = [
      `<button type="button" class="category-tab-btn ${state.activeCategory === "" ? "active" : ""}" data-category="">All Categories</button>`,
      ...categories.map(
        (cat) =>
          `<button type="button" class="category-tab-btn ${state.activeCategory === cat ? "active" : ""}" data-category="${escapeHtml(cat)}">${escapeHtml(cat)}</button>`
      ),
    ].join("");

    container.innerHTML = tabsHtml;

    container.querySelectorAll(".category-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        container.querySelectorAll(".category-tab-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        state.activeCategory = btn.getAttribute("data-category") || "";
        const titleEl = document.getElementById("catalog-title");
        if (titleEl) {
          titleEl.textContent = state.activeCategory ? `${state.activeCategory} Catalog` : "All Products";
        }
        loadProducts();
      });
    });
  } catch (err) {
    showToast("Failed to load category list", "error");
  }
}

/**
 * Fetches products matching current filters and renders to grid.
 */
async function loadProducts() {
  productGrid.renderLoading();
  try {
    const res = await StoreApi.fetchProducts({
      category: state.activeCategory,
      sort: state.sortOrder,
      search: state.searchQuery,
    });
    state.products = (res && res.data) || [];
    productGrid.render(state.products);
  } catch (err) {
    showToast("Could not retrieve catalog items.", "error");
  }
}

/**
 * Fetches current cart state and updates drawer and navbar counter.
 */
async function loadCart() {
  try {
    const res = await StoreApi.fetchCart();
    state.cart = res && res.data;
    if (state.cart) {
      cartDrawer.render(state.cart);
      navbar.updateCartCount(state.cart.item_count || 0);
    }
  } catch (err) {
    // Cart will create on next add action
  }
}

/**
 * Adds an item to the shopping cart.
 */
async function handleAddToCart(product) {
  try {
    const res = await StoreApi.addCartItem(product.id, 1);
    state.cart = res && res.data;
    cartDrawer.render(state.cart);
    navbar.updateCartCount(state.cart.item_count || 0);
    cartDrawer.open();
    showToast(`Added ${product.name} to cart`, "success");
  } catch (err) {
    const msg = err.message || "Failed to add item to cart.";
    showToast(msg, "error");
  }
}

/**
 * Updates cart item quantity.
 */
async function handleUpdateQuantity(productId, newQty) {
  try {
    const res = await StoreApi.updateCartItemQuantity(productId, newQty);
    state.cart = res && res.data;
    cartDrawer.render(state.cart);
    navbar.updateCartCount(state.cart.item_count || 0);
  } catch (err) {
    showToast(err.message || "Could not update item quantity.", "error");
  }
}

/**
 * Removes an item from the cart.
 */
async function handleRemoveItem(productId) {
  try {
    const res = await StoreApi.removeCartItem(productId);
    state.cart = res && res.data;
    cartDrawer.render(state.cart);
    navbar.updateCartCount(state.cart.item_count || 0);
    showToast("Item removed from cart", "info");
  } catch (err) {
    showToast("Could not remove item.", "error");
  }
}

/**
 * Applies a promotional coupon code.
 */
async function handleApplyPromo(promoCode) {
  try {
    const res = await StoreApi.applyPromoCode(promoCode);
    state.cart = res && res.data;
    cartDrawer.render(state.cart);
    showToast(`Promo code "${promoCode}" applied`, "success");
  } catch (err) {
    showToast(err.message || "Invalid or ineligible promo code.", "error");
  }
}

/**
 * Removes active promotional coupon code.
 */
async function handleRemovePromo() {
  try {
    const res = await StoreApi.removePromoCode();
    state.cart = res && res.data;
    cartDrawer.render(state.cart);
    showToast("Promo code removed", "info");
  } catch (err) {
    showToast("Could not remove promo code.", "error");
  }
}

/**
 * Opens checkout modal.
 */
function handleStartCheckout(cart) {
  checkoutModal.open(cart);
}

/**
 * Submits checkout order and simulates payment.
 */
async function handleSubmitCheckout({ customer_name, customer_email, shipping_address, scenario }) {
  try {
    // 1. Create order
    const orderRes = await StoreApi.createOrder({
      customer_name,
      customer_email,
      shipping_address,
    });

    const order = orderRes && orderRes.data;
    if (!order) {
      throw new Error("Order creation failed.");
    }

    // 2. Simulate payment
    const simRes = await StoreApi.simulatePayment({
      payment_intent_id: order.payment_intent_id,
      scenario,
    });

    const updatedOrder = simRes.order;

    if (scenario === "success") {
      clearStoredCartToken();
      showToast("Order placed and payment confirmed", "success");
    } else {
      showToast(`Payment declined: ${scenario.replace("_", " ")}`, "error");
    }

    orderSuccess.show(updatedOrder);
  } catch (err) {
    showToast(err.message || "Checkout transaction encountered an error.", "error");
    throw err;
  }
}
