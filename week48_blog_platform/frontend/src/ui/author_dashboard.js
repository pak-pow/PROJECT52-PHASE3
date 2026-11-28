/**
 * PulsePress Author Dashboard & Editorial Workbench
 * Provides JWT authentication, split-pane Markdown editor with live preview,
 * draft/publish workflow, tag selection, SEO meta editor, post management table,
 * and admin comment moderation + analytics overview.
 */

export class AuthorDashboard {
  /**
   * @param {Object} options
   * @param {HTMLElement} options.container - Mount container for workbench
   * @param {Function} [options.onViewPost] - Callback(slug) to open reader view
   * @param {Function} [options.onBackHome] - Callback() to return to home feed
   */
  constructor(options = {}) {
    this.container = options.container;
    this.onViewPost = options.onViewPost || (() => {});
    this.onBackHome = options.onBackHome || (() => {});

    this.token = localStorage.getItem("pulsepress_token") || null;
    this.user = null;
    this.posts = [];
    this.availableTags = [];
    this.moderationQueue = [];
    this.topPosts = [];
    this.editingSlug = null;
    this.authMode = "login";
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
   * Lightweight client-side Markdown-to-HTML preview renderer.
   * @param {string} markdown
   * @returns {string}
   */
  static renderPreviewMarkdown(markdown) {
    const esc = AuthorDashboard.escapeHtml;
    const lines = String(markdown || "").split(/\r?\n/);
    const out = [];
    let inCodeBlock = false;
    let inList = false;

    for (const rawLine of lines) {
      if (rawLine.trim().startsWith("```")) {
        if (inList) {
          out.push("</ul>");
          inList = false;
        }
        out.push(inCodeBlock ? "</code></pre>" : "<pre><code>");
        inCodeBlock = !inCodeBlock;
        continue;
      }

      if (inCodeBlock) {
        out.push(esc(rawLine));
        continue;
      }

      const trimmed = rawLine.trim();
      if (!trimmed) {
        if (inList) {
          out.push("</ul>");
          inList = false;
        }
        continue;
      }

      if (trimmed.startsWith("### ")) {
        out.push(`<h3>${AuthorDashboard.inlineFormat(trimmed.slice(4))}</h3>`);
      } else if (trimmed.startsWith("## ")) {
        out.push(`<h2>${AuthorDashboard.inlineFormat(trimmed.slice(3))}</h2>`);
      } else if (trimmed.startsWith("# ")) {
        out.push(`<h1>${AuthorDashboard.inlineFormat(trimmed.slice(2))}</h1>`);
      } else if (trimmed.startsWith("> ")) {
        out.push(
          `<blockquote>${AuthorDashboard.inlineFormat(
            trimmed.slice(2)
          )}</blockquote>`
        );
      } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        if (!inList) {
          out.push("<ul>");
          inList = true;
        }
        out.push(
          `<li>${AuthorDashboard.inlineFormat(trimmed.slice(2))}</li>`
        );
      } else {
        if (inList) {
          out.push("</ul>");
          inList = false;
        }
        out.push(`<p>${AuthorDashboard.inlineFormat(trimmed)}</p>`);
      }
    }

    if (inList) out.push("</ul>");
    if (inCodeBlock) out.push("</code></pre>");
    return out.join("\n");
  }

  /**
   * Apply inline bold, italic, and code formatting safely.
   * @param {string} text
   * @returns {string}
   */
  static inlineFormat(text) {
    let safe = AuthorDashboard.escapeHtml(text);
    safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");
    safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    return safe;
  }

  /**
   * Build authenticated request headers.
   * @returns {Object}
   */
  authHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }
    return headers;
  }

  /**
   * Open dashboard: verify existing JWT or display auth form.
   */
  async open() {
    if (!this.container) return;
    this.token = localStorage.getItem("pulsepress_token") || null;

    if (!this.token) {
      this.user = null;
      this.renderAuthView();
      return;
    }

    this.container.innerHTML =
      '<div class="loading-spinner">Verifying author session...</div>';

    try {
      const res = await fetch("/api/auth/me", { headers: this.authHeaders() });
      const payload = await res.json();
      if (!res.ok || payload.status !== "success") {
        this.signOut(false);
        this.renderAuthView("Session expired. Please sign in again.");
        return;
      }
      this.user = payload.data.user;
      await this.loadDashboardData();
      this.renderDashboard();
    } catch (err) {
      this.renderAuthView("Unable to reach authentication server.");
    }
  }

  /**
   * Clear JWT and optionally re-render login form.
   * @param {boolean} [rerender=true]
   */
  signOut(rerender = true) {
    this.token = null;
    this.user = null;
    this.editingSlug = null;
    localStorage.removeItem("pulsepress_token");
    if (rerender) this.renderAuthView();
  }

  /**
   * Load posts, tags, moderation queue, and analytics in parallel.
   */
  async loadDashboardData() {
    const requests = [
      fetch("/api/posts?status=all&page=1&page_size=50", {
        headers: this.authHeaders(),
      }),
      fetch("/api/tags?include_empty=true"),
      fetch("/api/analytics/top?limit=5"),
    ];
    if (this.user && this.user.role === "admin") {
      requests.push(
        fetch("/api/comments/queue?status=pending", {
          headers: this.authHeaders(),
        })
      );
    }

    const responses = await Promise.all(requests);
    const payloads = await Promise.all(responses.map((r) => r.json()));

    this.posts = Array.isArray(payloads[0]?.data?.posts)
      ? payloads[0].data.posts
      : [];
    this.availableTags = Array.isArray(payloads[1]?.data?.tags)
      ? payloads[1].data.tags
      : [];
    this.topPosts = Array.isArray(payloads[2]?.data?.posts)
      ? payloads[2].data.posts
      : [];
    this.moderationQueue =
      this.user?.role === "admin" && Array.isArray(payloads[3]?.data?.comments)
        ? payloads[3].data.comments
        : [];
  }

  /**
   * Render Sign In / Register panel.
   * @param {string} [notice=""]
   */
  renderAuthView(notice = "") {
    const esc = AuthorDashboard.escapeHtml;
    const isRegister = this.authMode === "register";

    this.container.innerHTML = `
      <div class="auth-panel-wrapper">
        <div class="auth-card">
          <div class="auth-card-header">
            <h2>${isRegister ? "Create Author Account" : "Author Workbench Sign In"}</h2>
            <button type="button" class="btn-secondary btn-sm" id="authBackHomeBtn">
              &larr; Feed
            </button>
          </div>
          ${
            notice
              ? `<div class="auth-notice">${esc(notice)}</div>`
              : ""
          }
          <form id="dashboardAuthForm" class="auth-form">
            ${
              isRegister
                ? `<div class="form-field">
                     <label for="authDisplayName">Display Name</label>
                     <input type="text" id="authDisplayName" name="display_name" required placeholder="Jane Doe" />
                   </div>
                   <div class="form-field">
                     <label for="authEmail">Email</label>
                     <input type="email" id="authEmail" name="email" required placeholder="jane@example.com" />
                   </div>`
                : ""
            }
            <div class="form-field">
              <label for="authUsername">${
                isRegister ? "Username" : "Username or Email"
              }</label>
              <input type="text" id="authUsername" name="username" required placeholder="author" />
            </div>
            <div class="form-field">
              <label for="authPassword">Password</label>
              <input type="password" id="authPassword" name="password" required minlength="6" placeholder="********" />
            </div>
            <div id="authFeedback" class="form-feedback" aria-live="polite"></div>
            <div class="auth-actions">
              <button type="submit" class="btn-primary">
                ${isRegister ? "Register" : "Sign In"}
              </button>
              <button type="button" class="btn-link" id="toggleAuthModeBtn">
                ${
                  isRegister
                    ? "Already have an account? Sign In"
                    : "Need an author account? Register"
                }
              </button>
            </div>
          </form>
        </div>
      </div>
    `;

    document
      .getElementById("authBackHomeBtn")
      ?.addEventListener("click", () => this.onBackHome());

    document
      .getElementById("toggleAuthModeBtn")
      ?.addEventListener("click", () => {
        this.authMode = isRegister ? "login" : "register";
        this.renderAuthView();
      });

    document
      .getElementById("dashboardAuthForm")
      ?.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.handleAuthSubmit(e.target);
      });
  }

  /**
   * Handle login or registration submission.
   * @param {HTMLFormElement} form
   */
  async handleAuthSubmit(form) {
    const feedback = document.getElementById("authFeedback");
    const fd = new FormData(form);
    const isRegister = this.authMode === "register";
    const endpoint = isRegister ? "/api/auth/register" : "/api/auth/login";

    const body = isRegister
      ? {
          username: String(fd.get("username") || "").trim(),
          email: String(fd.get("email") || "").trim(),
          display_name: String(fd.get("display_name") || "").trim(),
          password: String(fd.get("password") || ""),
        }
      : {
          username: String(fd.get("username") || "").trim(),
          password: String(fd.get("password") || ""),
        };

    if (feedback) feedback.textContent = "Authenticating...";

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await res.json();
      if (!res.ok || payload.status !== "success") {
        if (feedback) {
          feedback.className = "form-feedback error";
          feedback.textContent = payload.message || "Authentication failed.";
        }
        return;
      }

      this.token = payload.data.token;
      this.user = payload.data.user;
      localStorage.setItem("pulsepress_token", this.token);
      await this.loadDashboardData();
      this.renderDashboard();
    } catch (err) {
      if (feedback) {
        feedback.className = "form-feedback error";
        feedback.textContent = "Network error during authentication.";
      }
    }
  }

  /**
   * Render full Author Dashboard with split-pane editor, management table,
   * analytics summary, and admin moderation queue.
   */
  renderDashboard() {
    const esc = AuthorDashboard.escapeHtml;
    const editingPost = this.editingSlug
      ? this.posts.find((p) => p.slug === this.editingSlug)
      : null;

    const tagCheckboxes = this.availableTags
      .map((t) => {
        const isChecked = editingPost?.tags?.some((pt) => pt.slug === t.slug)
          ? "checked"
          : "";
        return `
          <label class="tag-select-chip">
            <input type="checkbox" name="tag_select" value="${esc(t.name)}" ${isChecked} />
            <span>${esc(t.name)}</span>
          </label>`;
      })
      .join("");

    const postsRows =
      this.posts.length > 0
        ? this.posts
            .map(
              (p) => `
            <tr>
              <td>
                <strong>${esc(p.title)}</strong>
                <div class="table-slug">/${esc(p.slug)}</div>
              </td>
              <td>
                <span class="status-pill status-${esc(p.status)}">${esc(
                p.status
              )}</span>
              </td>
              <td>${Number(p.reading_time_minutes) || 1} min</td>
              <td class="table-actions">
                <button type="button" class="btn-secondary btn-xs edit-post-btn" data-slug="${esc(
                  p.slug
                )}">Edit</button>
                ${
                  p.status !== "published"
                    ? `<button type="button" class="btn-primary btn-xs publish-post-btn" data-slug="${esc(
                        p.slug
                      )}">Publish</button>`
                    : `<button type="button" class="btn-secondary btn-xs view-post-btn" data-slug="${esc(
                        p.slug
                      )}">View</button>`
                }
                <button type="button" class="btn-danger btn-xs delete-post-btn" data-slug="${esc(
                  p.slug
                )}">Delete</button>
              </td>
            </tr>`
            )
            .join("")
        : '<tr><td colspan="4" class="muted-text">No posts yet. Create your first article above.</td></tr>';

    const moderationSection =
      this.user?.role === "admin"
        ? `<section class="dashboard-card">
             <h3>Comment Moderation Queue (${this.moderationQueue.length})</h3>
             ${
               this.moderationQueue.length > 0
                 ? `<div class="moderation-list">
                      ${this.moderationQueue
                        .map(
                          (c) => `
                        <div class="moderation-item">
                          <div>
                            <strong>${esc(c.author_name)}</strong>
                            <span class="muted-text">on ${esc(
                              c.post_title || ""
                            )}</span>
                            <p>${esc(c.body)}</p>
                          </div>
                          <div class="moderation-actions">
                            <button type="button" class="btn-primary btn-xs mod-btn" data-cid="${Number(
                              c.id
                            )}" data-status="approved">Approve</button>
                            <button type="button" class="btn-danger btn-xs mod-btn" data-cid="${Number(
                              c.id
                            )}" data-status="rejected">Reject</button>
                          </div>
                        </div>`
                        )
                        .join("")}
                    </div>`
                 : '<p class="muted-text">No pending comments in queue.</p>'
             }
           </section>`
        : "";

    this.container.innerHTML = `
      <div class="dashboard-topbar">
        <div>
          <h2>Editorial Workbench</h2>
          <p class="muted-text">Signed in as <strong>${esc(
            this.user?.display_name || this.user?.username || "Author"
          )}</strong> (${esc(this.user?.role || "author")})</p>
        </div>
        <div class="dashboard-topbar-actions">
          <button type="button" class="btn-secondary btn-sm" id="dashNewPostBtn">New Article</button>
          <button type="button" class="btn-secondary btn-sm" id="dashBackHomeBtn">&larr; Public Feed</button>
          <button type="button" class="btn-danger btn-sm" id="dashSignOutBtn">Sign Out</button>
        </div>
      </div>

      <section class="dashboard-card">
        <h3>${
          editingPost
            ? `Editing: ${esc(editingPost.title)}`
            : "Compose New Article"
        }</h3>
        <form id="postEditorForm" class="editor-form">
          <div class="editor-meta-grid">
            <div class="form-field">
              <label for="editorTitle">Article Title</label>
              <input type="text" id="editorTitle" name="title" required value="${esc(
                editingPost?.title || ""
              )}" placeholder="Designing Resilient SQLite Engines" />
            </div>
            <div class="form-field">
              <label for="editorStatus">Publication Status</label>
              <select id="editorStatus" name="status">
                <option value="draft" ${
                  editingPost?.status !== "published" ? "selected" : ""
                }>Draft</option>
                <option value="published" ${
                  editingPost?.status === "published" ? "selected" : ""
                }>Published</option>
              </select>
            </div>
          </div>

          <div class="editor-split-pane">
            <div class="editor-pane">
              <label for="editorMarkdown">Markdown Source</label>
              <textarea id="editorMarkdown" name="body_markdown" rows="14" required placeholder="# Heading&#10;&#10;Write technical markdown...">${esc(
                editingPost?.body_markdown || ""
              )}</textarea>
            </div>
            <div class="preview-pane">
              <label>Live Preview</label>
              <div id="editorLivePreview" class="article-content preview-surface"></div>
            </div>
          </div>

          <div class="editor-meta-grid">
            <div class="form-field">
              <label for="editorFeaturedImage">Featured Image URL</label>
              <input type="url" id="editorFeaturedImage" name="featured_image_url" value="${esc(
                editingPost?.featured_image_url || ""
              )}" placeholder="https://example.com/cover.png" />
            </div>
            <div class="form-field">
              <label for="editorCustomTags">Tags (comma-separated)</label>
              <input type="text" id="editorCustomTags" name="custom_tags" placeholder="Python, Architecture, SEO" />
            </div>
          </div>

          ${
            this.availableTags.length > 0
              ? `<div class="form-field">
                   <label>Existing Taxonomy Tags</label>
                   <div class="tag-select-grid">${tagCheckboxes}</div>
                 </div>`
              : ""
          }

          <div class="editor-meta-grid">
            <div class="form-field">
              <label for="editorSeoTitle">SEO Meta Title</label>
              <input type="text" id="editorSeoTitle" name="seo_title" maxlength="70" value="${esc(
                editingPost?.seo_title || ""
              )}" placeholder="Optional SEO title (max 70 chars)" />
            </div>
            <div class="form-field">
              <label for="editorSeoDesc">SEO Meta Description</label>
              <input type="text" id="editorSeoDesc" name="seo_description" maxlength="160" value="${esc(
                editingPost?.seo_description || ""
              )}" placeholder="Concise summary for search engines (max 160 chars)" />
            </div>
          </div>

          <div class="editor-submit-row">
            <button type="submit" class="btn-primary">
              ${editingPost ? "Save Changes" : "Create Article"}
            </button>
            ${
              editingPost
                ? '<button type="button" class="btn-secondary" id="cancelEditBtn">Cancel Edit</button>'
                : ""
            }
            <span id="editorFeedback" class="form-feedback" aria-live="polite"></span>
          </div>
        </form>
      </section>

      <section class="dashboard-card">
        <h3>Post Management (${this.posts.length})</h3>
        <div class="table-responsive">
          <table class="dashboard-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Status</th>
                <th>Read Time</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>${postsRows}</tbody>
          </table>
        </div>
      </section>

      <section class="dashboard-card">
        <h3>Top Performing Articles</h3>
        ${
          this.topPosts.length > 0
            ? `<ul class="analytics-top-list">
                 ${this.topPosts
                   .map(
                     (item) => `
                   <li>
                     <span>${esc(item.title)}</span>
                     <span class="views-badge">${Number(item.views) || 0} views</span>
                   </li>`
                   )
                   .join("")}
               </ul>`
            : '<p class="muted-text">No view telemetry recorded yet.</p>'
        }
      </section>

      ${moderationSection}
    `;

    this.bindDashboardEvents();
  }

  /**
   * Wire live Markdown preview, CRUD actions, and moderation handlers.
   */
  bindDashboardEvents() {
    const mdInput = document.getElementById("editorMarkdown");
    const previewEl = document.getElementById("editorLivePreview");
    const updatePreview = () => {
      if (mdInput && previewEl) {
        previewEl.innerHTML = AuthorDashboard.renderPreviewMarkdown(
          mdInput.value
        );
      }
    };
    if (mdInput) {
      mdInput.addEventListener("input", updatePreview);
      updatePreview();
    }

    document
      .getElementById("dashBackHomeBtn")
      ?.addEventListener("click", () => this.onBackHome());

    document
      .getElementById("dashSignOutBtn")
      ?.addEventListener("click", () => this.signOut(true));

    document
      .getElementById("dashNewPostBtn")
      ?.addEventListener("click", () => {
        this.editingSlug = null;
        this.renderDashboard();
      });

    document
      .getElementById("cancelEditBtn")
      ?.addEventListener("click", () => {
        this.editingSlug = null;
        this.renderDashboard();
      });

    document
      .getElementById("postEditorForm")
      ?.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.handleSavePost(e.target);
      });

    this.container.querySelectorAll(".edit-post-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.editingSlug = btn.getAttribute("data-slug");
        this.renderDashboard();
      });
    });

    this.container.querySelectorAll(".view-post-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.onViewPost(btn.getAttribute("data-slug"));
      });
    });

    this.container.querySelectorAll(".publish-post-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const slug = btn.getAttribute("data-slug");
        await fetch(`/api/posts/${encodeURIComponent(slug)}/publish`, {
          method: "POST",
          headers: this.authHeaders(),
        });
        await this.loadDashboardData();
        this.renderDashboard();
      });
    });

    this.container.querySelectorAll(".delete-post-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const slug = btn.getAttribute("data-slug");
        await fetch(`/api/posts/${encodeURIComponent(slug)}`, {
          method: "DELETE",
          headers: this.authHeaders(),
        });
        if (this.editingSlug === slug) this.editingSlug = null;
        await this.loadDashboardData();
        this.renderDashboard();
      });
    });

    this.container.querySelectorAll(".mod-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const cid = btn.getAttribute("data-cid");
        const status = btn.getAttribute("data-status");
        await fetch(`/api/comments/${encodeURIComponent(cid)}/moderate`, {
          method: "PUT",
          headers: this.authHeaders(),
          body: JSON.stringify({ status }),
        });
        await this.loadDashboardData();
        this.renderDashboard();
      });
    });
  }

  /**
   * Create or update a post via the REST API.
   * @param {HTMLFormElement} form
   */
  async handleSavePost(form) {
    const feedback = document.getElementById("editorFeedback");
    const fd = new FormData(form);
    const selectedTags = Array.from(
      form.querySelectorAll("input[name='tag_select']:checked")
    ).map((el) => el.value);
    const customTags = String(fd.get("custom_tags") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const mergedTags = Array.from(new Set([...selectedTags, ...customTags]));

    const payload = {
      title: String(fd.get("title") || "").trim(),
      body_markdown: String(fd.get("body_markdown") || ""),
      status: String(fd.get("status") || "draft"),
      featured_image_url:
        String(fd.get("featured_image_url") || "").trim() || null,
      seo_title: String(fd.get("seo_title") || "").trim() || null,
      seo_description: String(fd.get("seo_description") || "").trim() || null,
      tags: mergedTags,
    };

    if (feedback) {
      feedback.className = "form-feedback";
      feedback.textContent = "Saving article...";
    }

    try {
      const isEditing = Boolean(this.editingSlug);
      const url = isEditing
        ? `/api/posts/${encodeURIComponent(this.editingSlug)}`
        : "/api/posts";
      const method = isEditing ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: this.authHeaders(),
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok || data.status !== "success") {
        if (feedback) {
          feedback.classList.add("error");
          feedback.textContent = data.message || "Failed to save article.";
        }
        return;
      }

      this.editingSlug = null;
      await this.loadDashboardData();
      this.renderDashboard();
    } catch (err) {
      if (feedback) {
        feedback.classList.add("error");
        feedback.textContent = "Network error while saving article.";
      }
    }
  }
}
