/**
 * PulsePress Post List Component
 * Renders blog home feed with featured post hero, responsive card grid,
 * tag pills, pagination controls, and Load More / infinite scroll support.
 */

export class PostList {
  /**
   * @param {Object} options
   * @param {HTMLElement} options.container - Container for post feed
   * @param {HTMLElement} [options.filterBanner] - Active tag filter banner element
   * @param {Function} [options.onSelectPost] - Callback(slug) when opening a post
   * @param {Function} [options.onSelectTag] - Callback(tagSlug, tagName) when clicking a tag
   */
  constructor(options = {}) {
    this.container = options.container;
    this.filterBanner = options.filterBanner || null;
    this.onSelectPost = options.onSelectPost || (() => {});
    this.onSelectTag = options.onSelectTag || (() => {});
    this.state = {
      page: 1,
      pageSize: 6,
      totalPages: 1,
      total: 0,
      tag: null,
      tagName: null,
      posts: [],
      loading: false,
    };
    this._observer = null;
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
   * Format ISO date string.
   * @param {string} isoString
   * @returns {string}
   */
  static formatDate(isoString) {
    if (!isoString) return "";
    const parsed = new Date(isoString);
    if (Number.isNaN(parsed.getTime())) return String(isoString);
    return parsed.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  /**
   * Load posts for a given page and optional tag slug.
   * @param {Object} [params]
   * @param {number} [params.page=1]
   * @param {string|null} [params.tag=null]
   * @param {string|null} [params.tagName=null]
   * @param {boolean} [params.append=false]
   */
  async loadPosts({
    page = 1,
    tag = this.state.tag,
    tagName = this.state.tagName,
    append = false,
  } = {}) {
    if (!this.container || this.state.loading) return;
    this.state.loading = true;
    this.state.tag = tag || null;
    this.state.tagName = tagName || tag || null;

    if (!append) {
      this.container.innerHTML =
        '<div class="loading-spinner">Loading publications...</div>';
    }

    try {
      let url = "";
      if (this.state.tag) {
        url = `/api/tags/${encodeURIComponent(
          this.state.tag
        )}/posts?page=${page}&page_size=${this.state.pageSize}`;
      } else {
        url = `/api/posts?page=${page}&page_size=${this.state.pageSize}`;
      }

      const response = await fetch(url);
      const payload = await response.json();

      if (!response.ok || payload.status !== "success") {
        this.renderError(payload.message || "Failed to load articles.");
        return;
      }

      const data = payload.data || {};
      const incoming = Array.isArray(data.posts) ? data.posts : [];

      this.state.page = Number(data.page) || page;
      this.state.total = Number(data.total) || incoming.length;
      this.state.totalPages =
        Number(data.total_pages) ||
        Math.max(1, Math.ceil(this.state.total / this.state.pageSize));
      this.state.posts = append
        ? [...this.state.posts, ...incoming]
        : incoming;

      this.renderFilterBanner();
      this.render();
    } catch (err) {
      this.renderError("Network error while loading articles.");
    } finally {
      this.state.loading = false;
    }
  }

  /**
   * Render active tag filter pill banner when a tag filter is applied.
   */
  renderFilterBanner() {
    if (!this.filterBanner) return;
    if (!this.state.tag) {
      this.filterBanner.classList.add("hidden");
      this.filterBanner.innerHTML = "";
      return;
    }

    const esc = PostList.escapeHtml;
    this.filterBanner.classList.remove("hidden");
    this.filterBanner.innerHTML = `
      <span>Filtered by tag: <strong>${esc(
        this.state.tagName || this.state.tag
      )}</strong></span>
      <button type="button" class="btn-clear-filter" id="clearTagFilterBtn">Clear</button>
    `;
    const clearBtn = document.getElementById("clearTagFilterBtn");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        this.loadPosts({ page: 1, tag: null, tagName: null, append: false });
      });
    }
  }

  /**
   * Render error state.
   * @param {string} message
   */
  renderError(message) {
    this.container.innerHTML = `
      <div class="empty-state-card">
        <p>${PostList.escapeHtml(message)}</p>
      </div>
    `;
  }

  /**
   * Render featured hero, post card grid, pagination controls, and Load More sentinel.
   */
  render() {
    this.destroyObserver();
    const esc = PostList.escapeHtml;
    const posts = this.state.posts;

    if (posts.length === 0) {
      this.container.innerHTML = `
        <div class="empty-state-card">
          <h3>No articles found</h3>
          <p>Try clearing active filters or publishing your first article in the Workbench.</p>
        </div>
      `;
      return;
    }

    const showFeatured = !this.state.tag && this.state.page === 1 && posts.length > 0;
    const featured = showFeatured ? posts[0] : null;
    const gridPosts = showFeatured ? posts.slice(1) : posts;

    const featuredHtml = featured
      ? `<article class="featured-post-card" data-post-slug="${esc(featured.slug)}">
           <div class="featured-badge">FEATURED ARTICLE</div>
           <h2 class="featured-title">
             <a href="#post/${esc(featured.slug)}">${esc(featured.title)}</a>
           </h2>
           <p class="featured-excerpt">${esc(featured.excerpt || "")}</p>
           <div class="post-card-meta">
             <span>By ${esc(featured.author_name || "Editorial Team")}</span>
             <span>${esc(
               PostList.formatDate(featured.published_at || featured.created_at)
             )}</span>
             <span>${Number(featured.reading_time_minutes) || 1} min read</span>
             <div class="post-tags-list">
               ${(featured.tags || [])
                 .map(
                   (t) =>
                     `<button type="button" class="tag-badge tag-btn" data-tag-slug="${esc(
                       t.slug
                     )}" data-tag-name="${esc(t.name)}">${esc(t.name)}</button>`
                 )
                 .join("")}
             </div>
           </div>
         </article>`
      : "";

    const gridHtml =
      gridPosts.length > 0
        ? `<div class="posts-grid">
             ${gridPosts
               .map(
                 (post) => `
               <article class="post-card" data-post-slug="${esc(post.slug)}">
                 <h3 class="post-card-title">
                   <a href="#post/${esc(post.slug)}">${esc(post.title)}</a>
                 </h3>
                 <p class="post-card-excerpt">${esc(post.excerpt || "")}</p>
                 <div class="post-card-meta">
                   <span>By ${esc(post.author_name || "Editorial Team")}</span>
                   <span>${esc(
                     PostList.formatDate(post.published_at || post.created_at)
                   )}</span>
                   <span>${Number(post.reading_time_minutes) || 1} min read</span>
                 </div>
                 <div class="post-tags-list">
                   ${(post.tags || [])
                     .map(
                       (t) =>
                         `<button type="button" class="tag-badge tag-btn" data-tag-slug="${esc(
                           t.slug
                         )}" data-tag-name="${esc(t.name)}">${esc(
                           t.name
                         )}</button>`
                     )
                     .join("")}
                 </div>
               </article>`
               )
               .join("")}
           </div>`
        : "";

    const hasMore = this.state.page < this.state.totalPages;
    const paginationHtml = `
      <div class="pagination-bar">
        <div class="pagination-controls">
          <button type="button" class="btn-secondary btn-sm" id="prevPageBtn"
            ${this.state.page <= 1 ? "disabled" : ""}>Previous</button>
          <span class="pagination-info">
            Page ${this.state.page} of ${this.state.totalPages} (${this.state.total} articles)
          </span>
          <button type="button" class="btn-secondary btn-sm" id="nextPageBtn"
            ${!hasMore ? "disabled" : ""}>Next</button>
        </div>
        ${
          hasMore
            ? `<button type="button" class="btn-primary btn-sm" id="loadMoreBtn">
                 Load More Articles
               </button>`
            : ""
        }
      </div>
      <div id="infiniteScrollSentinel" class="infinite-sentinel"></div>
    `;

    this.container.innerHTML = `${featuredHtml}${gridHtml}${paginationHtml}`;
    this.bindEvents(hasMore);
  }

  /**
   * Bind click and infinite-scroll handlers.
   * @param {boolean} hasMore
   */
  bindEvents(hasMore) {
    this.container.querySelectorAll("[data-post-slug] a").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const card = link.closest("[data-post-slug]");
        if (card) {
          this.onSelectPost(card.getAttribute("data-post-slug"));
        }
      });
    });

    this.container.querySelectorAll("[data-tag-slug]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const slug = btn.getAttribute("data-tag-slug");
        const name = btn.getAttribute("data-tag-name");
        this.onSelectTag(slug, name);
      });
    });

    const prevBtn = document.getElementById("prevPageBtn");
    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (this.state.page > 1) {
          this.loadPosts({ page: this.state.page - 1, append: false });
        }
      });
    }

    const nextBtn = document.getElementById("nextPageBtn");
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (this.state.page < this.state.totalPages) {
          this.loadPosts({ page: this.state.page + 1, append: false });
        }
      });
    }

    const loadMoreBtn = document.getElementById("loadMoreBtn");
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", () => {
        this.loadPosts({ page: this.state.page + 1, append: true });
      });
    }

    const sentinel = document.getElementById("infiniteScrollSentinel");
    if (hasMore && sentinel && "IntersectionObserver" in window) {
      this._observer = new IntersectionObserver(
        (entries) => {
          if (entries[0] && entries[0].isIntersecting && !this.state.loading) {
            this.loadPosts({ page: this.state.page + 1, append: true });
          }
        },
        { rootMargin: "200px" }
      );
      this._observer.observe(sentinel);
    }
  }

  /**
   * Disconnect IntersectionObserver if active.
   */
  destroyObserver() {
    if (this._observer) {
      this._observer.disconnect();
      this._observer = null;
    }
  }
}
