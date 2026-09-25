import { getIcon } from "../utils/helpers.js";

/**
 * Navbar component for the store header.
 */
export function initNavbar({ onCartClick }) {
  const mount = document.getElementById("navbar-mount");
  if (!mount) return null;

  mount.innerHTML = `
    <div class="navbar-inner">
      <a href="#" class="brand-group" id="brand-link">
        <div class="brand-icon-box">
          ${getIcon("package", 20)}
        </div>
        <div class="brand-text-block">
          <span class="brand-name">ShopPulse</span>
          <span class="brand-tagline">Phase 3 Production</span>
        </div>
      </a>

      <div class="nav-actions">
        <button id="nav-cart-btn" class="cart-trigger-btn" aria-label="Open cart">
          ${getIcon("cart", 18)}
          <span>Cart</span>
          <span id="nav-cart-badge" class="cart-badge">0</span>
        </button>
      </div>
    </div>
  `;

  const cartBtn = document.getElementById("nav-cart-btn");
  if (cartBtn && typeof onCartClick === "function") {
    cartBtn.addEventListener("click", () => {
      onCartClick();
    });
  }

  const brandLink = document.getElementById("brand-link");
  if (brandLink) {
    brandLink.addEventListener("click", (e) => {
      e.preventDefault();
      window.location.hash = "";
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  return {
    updateCartCount(count) {
      const badge = document.getElementById("nav-cart-badge");
      if (!badge) return;
      const prevCount = parseInt(badge.textContent, 10) || 0;
      badge.textContent = count;
      if (count > prevCount) {
        badge.classList.remove("bump");
        // Force reflow to replay animation
        void badge.offsetWidth;
        badge.classList.add("bump");
      }
    },
  };
}
