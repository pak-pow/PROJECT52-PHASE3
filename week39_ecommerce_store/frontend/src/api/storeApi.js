import { getStoredCartToken, setStoredCartToken } from "../utils/helpers.js";

const BASE_URL =
  window.location.port === "5000"
    ? "/api/v1"
    : "http://127.0.0.1:5000/api/v1";

/**
 * Standard fetch wrapper handling JSON payloads, cart tokens, and unified errors.
 * @param {string} endpoint 
 * @param {object} options 
 * @returns {Promise<any>}
 */
async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const headers = {
    Accept: "application/json",
    ...options.headers,
  };

  if (options.body && typeof options.body === "object") {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }

  const token = getStoredCartToken();
  if (token) {
    headers["X-Cart-Token"] = token;
  }

  const response = await fetch(url, { ...options, headers });

  // Update token from response headers if present
  const respToken = response.headers.get("X-Cart-Token");
  if (respToken) {
    setStoredCartToken(respToken);
  }

  let data;
  try {
    data = await response.json();
  } catch (err) {
    data = null;
  }

  // Also check if data returned a cart token
  if (data && data.data && data.data.token) {
    setStoredCartToken(data.data.token);
  }

  if (!response.ok) {
    const errorMsg = (data && data.message) || `Request failed with status ${response.status}`;
    const error = new Error(errorMsg);
    error.status = response.status;
    error.code = data && data.code;
    error.data = data;
    throw error;
  }

  return data;
}

export const StoreApi = {
  /**
   * Fetches product catalog with filtering, search, and sorting.
   */
  async fetchProducts({ category = "", sort = "", search = "", limit = 50, offset = 0 } = {}) {
    const params = new URLSearchParams();
    if (category) params.append("category", category);
    if (sort) params.append("sort", sort);
    if (search) params.append("search", search);
    if (limit) params.append("limit", limit);
    if (offset) params.append("offset", offset);

    const query = params.toString() ? `?${params.toString()}` : "";
    return request(`/products${query}`);
  },

  /**
   * Fetches a single product by its slug.
   */
  async fetchProductBySlug(slug) {
    return request(`/products/${encodeURIComponent(slug)}`);
  },

  /**
   * Fetches category list.
   */
  async fetchCategories() {
    return request("/categories");
  },

  /**
   * Fetches current shopping cart.
   */
  async fetchCart() {
    return request("/cart");
  },

  /**
   * Adds an item to the shopping cart.
   */
  async addCartItem(productId, quantity = 1) {
    return request("/cart/items", {
      method: "POST",
      body: { product_id: productId, quantity },
    });
  },

  /**
   * Updates quantity of an existing item in the cart.
   */
  async updateCartItemQuantity(productId, quantity) {
    return request(`/cart/items/${productId}`, {
      method: "PATCH",
      body: { quantity },
    });
  },

  /**
   * Removes an item completely from the cart.
   */
  async removeCartItem(productId) {
    return request(`/cart/items/${productId}`, {
      method: "DELETE",
    });
  },

  /**
   * Empties the entire cart.
   */
  async clearCart() {
    return request("/cart", {
      method: "DELETE",
    });
  },

  /**
   * Applies a promo code to the cart.
   */
  async applyPromoCode(promoCode) {
    return request("/cart/promo", {
      method: "POST",
      body: { promo_code: promoCode },
    });
  },

  /**
   * Removes currently active promo code.
   */
  async removePromoCode() {
    return request("/cart/promo", {
      method: "DELETE",
    });
  },

  /**
   * Creates an order from current cart.
   */
  async createOrder({ customer_email, customer_name, shipping_address }) {
    const token = getStoredCartToken();
    return request("/checkout/create-order", {
      method: "POST",
      body: {
        cart_token: token,
        customer_email,
        customer_name,
        shipping_address,
      },
    });
  },

  /**
   * Simulates payment gateway processing.
   */
  async simulatePayment({ payment_intent_id, scenario = "success" }) {
    return request("/checkout/simulate-payment", {
      method: "POST",
      body: {
        payment_intent_id,
        scenario,
      },
    });
  },

  /**
   * Fetches order details by order number.
   */
  async fetchOrder(orderNumber) {
    return request(`/orders/${encodeURIComponent(orderNumber)}`);
  },

  /**
   * Fetches order invoice by order number.
   */
  async fetchInvoice(orderNumber) {
    return request(`/orders/${encodeURIComponent(orderNumber)}/invoice`);
  },
};
