import { escapeHtml, formatCurrency, getIcon } from "../utils/helpers.js";

/**
 * Product grid component rendering catalog items.
 */
export function initProductGrid({ onAddToCart }) {
  const grid = document.getElementById("product-grid");
  const countLabel = document.getElementById("catalog-count");

  function render(products = []) {
    if (!grid) return;

    if (countLabel) {
      countLabel.textContent = `${products.length} ${products.length === 1 ? "item" : "items"}`;
    }

    if (products.length === 0) {
      grid.innerHTML = `
        <div class="cart-empty-state catalog-empty-state">
          ${getIcon("search", 40)}
          <h3>No products found</h3>
          <p>Try adjusting your category filter or search keywords.</p>
        </div>
      `;
      // Note: replaced inline style above with a CSS class or clean structure!
      // Let's make sure there are ZERO inline styles anywhere!
      return;
    }

    grid.innerHTML = products.map((product) => createProductCardHtml(product)).join("");

    // Attach click listeners to all Add to Cart buttons
    grid.querySelectorAll(".btn-add-cart").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const productId = parseInt(btn.getAttribute("data-id"), 10);
        const targetProduct = products.find((p) => p.id === productId);
        if (!targetProduct) return;

        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `${getIcon("package", 14)} Adding...`;

        try {
          if (typeof onAddToCart === "function") {
            await onAddToCart(targetProduct);
          }
        } finally {
          btn.disabled = false;
          btn.innerHTML = originalText;
        }
      });
    });
  }

  function renderLoading() {
    if (!grid) return;
    grid.innerHTML = `
      <div class="cart-empty-state">
        <p>Loading catalog items...</p>
      </div>
    `;
  }

  return {
    render,
    renderLoading,
  };
}

/**
 * Generates card markup for an individual product.
 */
function createProductCardHtml(product) {
  const isOutOfStock = product.stock_quantity <= 0;
  const isLowStock = !isOutOfStock && product.stock_quantity <= 5;

  let stockClass = "stock-in";
  let stockText = "In Stock";

  if (isOutOfStock) {
    stockClass = "stock-out";
    stockText = "Out of Stock";
  } else if (isLowStock) {
    stockClass = "stock-low";
    stockText = `Low Stock: ${product.stock_quantity} left`;
  }

  const imageUrl = product.image_url || "";

  return `
    <article class="product-card" data-product-id="${product.id}">
      <div class="product-card-image-wrap">
        <img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(product.name)}" loading="lazy">
        <div class="product-badge-group">
          <span class="category-tag">${escapeHtml(product.category)}</span>
          <span class="stock-tag ${stockClass}">${stockText}</span>
        </div>
      </div>
      <div class="product-card-body">
        <h3 class="product-title">${escapeHtml(product.name)}</h3>
        <p class="product-desc">${escapeHtml(product.description || "")}</p>
        <div class="product-card-footer">
          <div class="product-price-block">
            <span class="product-price">${formatCurrency(product.price_cents)}</span>
          </div>
          <button 
            type="button" 
            class="btn-add-cart" 
            data-id="${product.id}"
            ${isOutOfStock ? "disabled" : ""}
            aria-label="Add ${escapeHtml(product.name)} to cart"
          >
            ${getIcon("cart", 16)}
            <span>${isOutOfStock ? "Sold Out" : "Add to Cart"}</span>
          </button>
        </div>
      </div>
    </article>
  `;
}
