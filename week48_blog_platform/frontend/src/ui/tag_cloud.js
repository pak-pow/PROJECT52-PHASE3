/**
 * PulsePress Tag Cloud Component
 * Renders an interactive weighted tag cloud with normalized font sizing
 * and click-to-filter navigation.
 */

export class TagCloud {
  /**
   * @param {Object} options
   * @param {HTMLElement} options.container - Target element for tag cloud
   * @param {Function} [options.onSelectTag] - Callback(slug, name) on tag click
   */
  constructor(options = {}) {
    this.container = options.container;
    this.onSelectTag = options.onSelectTag || (() => {});
    this.activeSlug = null;
    this.tags = [];
  }

  /**
   * Escape HTML special characters.
   * @param {string} value
   * @returns {string}
   */
  static escapeHtml(value) {
    const str = String(value ?? "");
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * Fetch tag cloud metrics from /api/tags and render.
   * @param {string|null} [activeSlug=null]
   */
  async load(activeSlug = this.activeSlug) {
    if (!this.container) return;
    this.activeSlug = activeSlug || null;

    try {
      const response = await fetch("/api/tags");
      const payload = await response.json();
      if (!response.ok || payload.status !== "success") {
        this.tags = [];
      } else {
        this.tags = Array.isArray(payload.data?.tags) ? payload.data.tags : [];
      }
    } catch (err) {
      this.tags = [];
    }

    this.render();
  }

  /**
   * Update highlighted active tag without refetching.
   * @param {string|null} slug
   */
  setActive(slug) {
    this.activeSlug = slug || null;
    this.render();
  }

  /**
   * Render weighted tag cloud buttons.
   */
  render() {
    if (!this.container) return;
    const esc = TagCloud.escapeHtml;

    if (this.tags.length === 0) {
      this.container.innerHTML =
        '<span class="muted-text">No published tags yet.</span>';
      return;
    }

    this.container.innerHTML = this.tags
      .map((tag) => {
        const isActive = this.activeSlug === tag.slug;
        const size = Number(tag.font_size) || 0.95;
        const count = Number(tag.post_count) || 0;
        return `
          <button type="button"
            class="tag-cloud-item ${isActive ? "active" : ""}"
            style="font-size: ${size.toFixed(2)}rem"
            data-cloud-slug="${esc(tag.slug)}"
            data-cloud-name="${esc(tag.name)}"
            title="${esc(tag.name)} (${count} posts)">
            ${esc(tag.name)} <span class="tag-cloud-count">(${count})</span>
          </button>`;
      })
      .join("");

    this.container.querySelectorAll("[data-cloud-slug]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const slug = btn.getAttribute("data-cloud-slug");
        const name = btn.getAttribute("data-cloud-name");
        const nextSlug = this.activeSlug === slug ? null : slug;
        this.setActive(nextSlug);
        this.onSelectTag(nextSlug, nextSlug ? name : null);
      });
    });
  }
}
