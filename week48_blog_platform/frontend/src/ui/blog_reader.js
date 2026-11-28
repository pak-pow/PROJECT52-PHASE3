/**
 * PulsePress Blog Reader Component
 * Renders typography-focused articles with sticky TOC sidebar,
 * reading time badge, social share actions, related posts, and theme toggle.
 */

export class BlogReader {
  /**
   * @param {Object} options
   * @param {HTMLElement} options.container - Target container for reader view
   * @param {Function} [options.onNavigatePost] - Callback(slug) when clicking a related post
   * @param {Function} [options.onSelectTag] - Callback(tagSlug) when clicking a tag pill
   * @param {Function} [options.onMountComments] - Callback(slug, mountEl) to mount CommentWidget
   * @param {Function} [options.onBackHome] - Callback() to return to home list
   */
  constructor(options = {}) {
    this.container = options.container;
    this.onNavigatePost = options.onNavigatePost || (() => {});
    this.onSelectTag = options.onSelectTag || (() => {});
    this.onMountComments = options.onMountComments || (() => {});
    this.onBackHome = options.onBackHome || (() => {});
    this._scrollHandler = null;
  }

  /**
   * Escape HTML special characters for safe text rendering.
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
   * Format ISO timestamp into readable date string.
   * @param {string} isoString
   * @returns {string}
   */
  static formatDate(isoString) {
    if (!isoString) return "Unpublished";
    const parsed = new Date(isoString);
    if (Number.isNaN(parsed.getTime())) return String(isoString);
    return parsed.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  /**
   * Fetch and render a single post by slug.
   * @param {string} slug
   */
  async loadPost(slug) {
    if (!this.container) return;
    this.destroy();
    this.container.innerHTML =
      '<div class="loading-spinner">Loading article...</div>';

    try {
      const token = localStorage.getItem("pulsepress_token");
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await fetch(`/api/posts/${encodeURIComponent(slug)}`, {
        headers,
      });
      const payload = await response.json();

      if (!response.ok || payload.status !== "success") {
        this.renderError(payload.message || "Article could not be loaded.");
        return;
      }

      const post = payload.data.post;
      this.updateDocumentMeta(post);
      this.render(post);
    } catch (err) {
      this.renderError("Network error while loading article.");
    }
  }

  /**
   * Update page title and meta description for reader context.
   * @param {Object} post
   */
  updateDocumentMeta(post) {
    const title = post.seo_title || post.title || "PulsePress Article";
    document.title = `${title} | PulsePress`;
    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc && (post.seo_description || post.excerpt)) {
      metaDesc.setAttribute(
        "content",
        post.seo_description || post.excerpt || ""
      );
    }
  }

  /**
   * Render error state with back navigation.
   * @param {string} message
   */
  renderError(message) {
    this.container.innerHTML = `
      <div class="reader-error-card">
        <h2>Article Unavailable</h2>
        <p>${BlogReader.escapeHtml(message)}</p>
        <button type="button" class="btn-primary" id="readerBackBtn">Back to Articles</button>
      </div>
    `;
    const backBtn = document.getElementById("readerBackBtn");
    if (backBtn) {
      backBtn.addEventListener("click", () => this.onBackHome());
    }
  }

  /**
   * Render full post reader layout with sticky TOC, share buttons, and comments slot.
   * @param {Object} post
   */
  render(post) {
    const esc = BlogReader.escapeHtml;
    const tocItems = Array.isArray(post.toc) ? post.toc : [];
    const tags = Array.isArray(post.tags) ? post.tags : [];
    const related = Array.isArray(post.related_posts) ? post.related_posts : [];
    const shareUrl = `${window.location.origin}/#post/${encodeURIComponent(
      post.slug
    )}`;
    const shareTitle = encodeURIComponent(post.title || "");
    const encodedUrl = encodeURIComponent(shareUrl);

    const coverHtml = post.featured_image_url
      ? `<figure class="reader-cover">
           <img src="${esc(post.featured_image_url)}" alt="${esc(post.title)}" loading="lazy" />
         </figure>`
      : "";

    const tocHtml =
      tocItems.length > 0
        ? `<aside class="reader-toc-sidebar" aria-label="Table of contents">
             <div class="toc-card">
               <h3 class="toc-title">On This Page</h3>
               <nav class="toc-nav" id="readerTocNav">
                 ${tocItems
                   .map(
                     (item) => `
                   <a href="#${esc(item.id)}"
                      class="toc-link toc-level-${Number(item.level) || 2}"
                      data-toc-id="${esc(item.id)}">
                     ${esc(item.text)}
                   </a>`
                   )
                   .join("")}
               </nav>
             </div>
           </aside>`
        : "";

    const relatedHtml =
      related.length > 0
        ? `<section class="related-posts-section">
             <h3 class="section-subtitle">Related Engineering Articles</h3>
             <div class="related-posts-grid">
               ${related
                 .map(
                   (item) => `
                 <article class="related-card" data-related-slug="${esc(item.slug)}">
                   <h4><a href="#post/${esc(item.slug)}">${esc(item.title)}</a></h4>
                   <p>${esc(item.excerpt || "")}</p>
                   <span class="related-meta">${Number(item.reading_time_minutes) || 1} min read</span>
                 </article>`
                 )
                 .join("")}
             </div>
           </section>`
        : "";

    this.container.innerHTML = `
      <div class="reader-topbar">
        <button type="button" class="btn-secondary btn-sm" id="readerBackHomeBtn">
          &larr; All Articles
        </button>
        <div class="reader-topbar-actions">
          <span class="reading-time-badge">${Number(post.reading_time_minutes) || 1} min read</span>
          <span class="views-badge">${Number(post.view_count) || 0} views</span>
          <button type="button" class="btn-secondary btn-sm" id="readerThemeToggleBtn">
            Toggle Theme
          </button>
        </div>
      </div>

      <div class="reader-layout ${tocItems.length > 0 ? "has-toc" : ""}">
        <article class="reader-article">
          <header class="reader-header">
            <div class="reader-tags">
              ${tags
                .map(
                  (t) =>
                    `<button type="button" class="tag-badge tag-btn" data-tag-slug="${esc(
                      t.slug
                    )}">${esc(t.name)}</button>`
                )
                .join("")}
            </div>
            <h1 class="reader-title">${esc(post.title)}</h1>
            <div class="reader-byline">
              <span>By <strong>${esc(post.author_name || "Editorial Team")}</strong></span>
              <span class="meta-dot">&bull;</span>
              <time datetime="${esc(post.published_at || post.created_at || "")}">
                ${esc(BlogReader.formatDate(post.published_at || post.created_at))}
              </time>
            </div>
          </header>

          ${coverHtml}

          <div class="article-content" id="readerArticleBody">
            ${post.body_html || ""}
          </div>

          <section class="share-bar" aria-label="Share article">
            <span class="share-label">Share this article:</span>
            <div class="share-buttons">
              <button type="button" class="btn-secondary btn-sm" id="copyShareLinkBtn">Copy Link</button>
              <a class="btn-secondary btn-sm" target="_blank" rel="noopener noreferrer"
                 href="https://twitter.com/intent/tweet?text=${shareTitle}&url=${encodedUrl}">
                Share on X
              </a>
              <a class="btn-secondary btn-sm" target="_blank" rel="noopener noreferrer"
                 href="https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}">
                LinkedIn
              </a>
            </div>
            <span id="shareCopyStatus" class="share-copy-status" aria-live="polite"></span>
          </section>

          ${relatedHtml}

          <section id="readerCommentsMount" class="comments-section"></section>
        </article>

        ${tocHtml}
      </div>
    `;

    this.bindReaderEvents(post, shareUrl);

    const commentsMount = document.getElementById("readerCommentsMount");
    if (commentsMount) {
      this.onMountComments(post.slug, commentsMount);
    }
  }

  /**
   * Attach interactive handlers for back button, tags, TOC scroll spy, share, and theme toggle.
   * @param {Object} post
   * @param {string} shareUrl
   */
  bindReaderEvents(post, shareUrl) {
    const backBtn = document.getElementById("readerBackHomeBtn");
    if (backBtn) {
      backBtn.addEventListener("click", () => this.onBackHome());
    }

    const themeBtn = document.getElementById("readerThemeToggleBtn");
    if (themeBtn) {
      themeBtn.addEventListener("click", () => {
        const headerThemeBtn = document.getElementById("themeToggleBtn");
        if (headerThemeBtn) headerThemeBtn.click();
      });
    }

    const copyBtn = document.getElementById("copyShareLinkBtn");
    const copyStatus = document.getElementById("shareCopyStatus");
    if (copyBtn) {
      copyBtn.addEventListener("click", async () => {
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(shareUrl);
          }
          if (copyStatus) copyStatus.textContent = "Link copied.";
        } catch (err) {
          if (copyStatus) copyStatus.textContent = "Copy unavailable.";
        }
      });
    }

    this.container.querySelectorAll("[data-tag-slug]").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.onSelectTag(btn.getAttribute("data-tag-slug"));
      });
    });

    this.container.querySelectorAll("[data-related-slug]").forEach((card) => {
      card.addEventListener("click", (e) => {
        e.preventDefault();
        this.onNavigatePost(card.getAttribute("data-related-slug"));
      });
    });

    this.container.querySelectorAll(".toc-link").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const targetId = link.getAttribute("data-toc-id");
        const heading = targetId ? document.getElementById(targetId) : null;
        if (heading) {
          heading.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });

    this.setupScrollSpy();
  }

  /**
   * Highlight the active TOC link based on viewport scroll position.
   */
  setupScrollSpy() {
    const links = Array.from(this.container.querySelectorAll(".toc-link"));
    if (links.length === 0) return;

    const headings = links
      .map((l) => document.getElementById(l.getAttribute("data-toc-id")))
      .filter(Boolean);

    if (headings.length === 0) return;

    this._scrollHandler = () => {
      let activeId = headings[0].id;
      for (const heading of headings) {
        if (heading.getBoundingClientRect().top <= 140) {
          activeId = heading.id;
        }
      }
      links.forEach((link) => {
        link.classList.toggle(
          "active",
          link.getAttribute("data-toc-id") === activeId
        );
      });
    };

    window.addEventListener("scroll", this._scrollHandler, { passive: true });
    this._scrollHandler();
  }

  /**
   * Clean up scroll listeners when leaving reader view.
   */
  destroy() {
    if (this._scrollHandler) {
      window.removeEventListener("scroll", this._scrollHandler);
      this._scrollHandler = null;
    }
  }
}
