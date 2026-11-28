/**
 * PulsePress Threaded Comment Widget
 * Renders multi-level comment trees with Gravatar avatars, relative timestamps,
 * inline reply forms, and rate-limit / moderation feedback.
 */

export class CommentWidget {
  /**
   * @param {Object} options
   * @param {HTMLElement} options.container - Target container for comments
   * @param {string} options.slug - Post slug
   */
  constructor(options = {}) {
    this.container = options.container;
    this.slug = options.slug;
    this.comments = [];
    this.activeReplyId = null;
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
   * Convert an ISO timestamp to a human-readable relative string.
   * @param {string} isoString
   * @returns {string}
   */
  static formatRelativeTime(isoString) {
    if (!isoString) return "just now";
    const parsed = new Date(isoString);
    if (Number.isNaN(parsed.getTime())) return String(isoString);
    const diffSec = Math.max(
      0,
      Math.floor((Date.now() - parsed.getTime()) / 1000)
    );
    if (diffSec < 60) return "just now";
    const mins = Math.floor(diffSec / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return parsed.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  /**
   * Fetch and render approved comments for the post.
   */
  async load() {
    if (!this.container || !this.slug) return;
    this.container.innerHTML =
      '<div class="loading-spinner">Loading discussion...</div>';

    try {
      const response = await fetch(
        `/api/posts/${encodeURIComponent(this.slug)}/comments`
      );
      const payload = await response.json();
      if (!response.ok || payload.status !== "success") {
        this.comments = [];
      } else {
        this.comments = Array.isArray(payload.data?.comments)
          ? payload.data.comments
          : [];
      }
    } catch (err) {
      this.comments = [];
    }

    this.render();
  }

  /**
   * Count total comments recursively across nested replies.
   * @param {Array} nodes
   * @returns {number}
   */
  countTree(nodes) {
    return (nodes || []).reduce(
      (sum, node) => sum + 1 + this.countTree(node.replies || []),
      0
    );
  }

  /**
   * Render comment thread recursively with bounded visual indentation.
   * @param {Array} nodes
   * @param {number} depth
   * @returns {string}
   */
  renderTree(nodes, depth = 0) {
    if (!Array.isArray(nodes) || nodes.length === 0) return "";
    const esc = CommentWidget.escapeHtml;
    const indentLevel = Math.min(depth, 4);

    return nodes
      .map((comment) => {
        const avatar =
          comment.gravatar_url ||
          "https://www.gravatar.com/avatar/00000000000000000000000000000000?s=80&d=identicon";
        const repliesHtml = this.renderTree(comment.replies || [], depth + 1);
        const replyFormHtml =
          this.activeReplyId === comment.id
            ? this.renderFormMarkup(comment.id)
            : "";

        return `
          <div class="comment-node depth-${indentLevel}" data-comment-id="${Number(
          comment.id
        )}">
            <div class="comment-card">
              <img class="comment-avatar" src="${esc(avatar)}" alt="${esc(
          comment.author_name
        )}" width="40" height="40" loading="lazy" />
              <div class="comment-content">
                <div class="comment-header">
                  <strong class="comment-author">${esc(
                    comment.author_name
                  )}</strong>
                  <span class="comment-time">${esc(
                    CommentWidget.formatRelativeTime(comment.created_at)
                  )}</span>
                </div>
                <div class="comment-body">${esc(comment.body)}</div>
                <div class="comment-actions">
                  <button type="button" class="btn-link reply-trigger-btn" data-reply-to="${Number(
                    comment.id
                  )}">
                    Reply
                  </button>
                </div>
              </div>
            </div>
            ${replyFormHtml}
            ${repliesHtml}
          </div>`;
      })
      .join("");
  }

  /**
   * Render comment submission form HTML for root or reply target.
   * @param {number|null} parentId
   * @returns {string}
   */
  renderFormMarkup(parentId = null) {
    const suffix = parentId ? `reply-${parentId}` : "root";
    return `
      <form class="comment-form ${
        parentId ? "comment-reply-form" : ""
      }" data-parent-id="${parentId || ""}" id="commentForm-${suffix}">
        <div class="comment-form-row">
          <div class="form-field">
            <label for="commentAuthor-${suffix}">Name</label>
            <input type="text" id="commentAuthor-${suffix}" name="author_name" required maxlength="100" placeholder="Your name" />
          </div>
          <div class="form-field">
            <label for="commentEmail-${suffix}">Email (private, used for Gravatar)</label>
            <input type="email" id="commentEmail-${suffix}" name="author_email" required placeholder="you@example.com" />
          </div>
        </div>
        <div class="form-field">
          <label for="commentBody-${suffix}">${
      parentId ? "Reply" : "Comment"
    }</label>
          <textarea id="commentBody-${suffix}" name="body" rows="3" required maxlength="5000" placeholder="Share a thoughtful engineering perspective..."></textarea>
        </div>
        <div class="comment-form-footer">
          <button type="submit" class="btn-primary btn-sm">
            ${parentId ? "Post Reply" : "Submit Comment"}
          </button>
          ${
            parentId
              ? '<button type="button" class="btn-secondary btn-sm cancel-reply-btn">Cancel</button>'
              : ""
          }
          <span class="comment-form-feedback" aria-live="polite"></span>
        </div>
      </form>`;
  }

  /**
   * Render full discussion section.
   */
  render() {
    if (!this.container) return;
    const totalCount = this.countTree(this.comments);
    const treeHtml =
      this.comments.length > 0
        ? `<div class="comments-thread">${this.renderTree(
            this.comments,
            0
          )}</div>`
        : '<p class="muted-text">No approved comments yet. Start the discussion below.</p>';

    this.container.innerHTML = `
      <div class="comments-header">
        <h3 class="section-subtitle">Discussion (${totalCount})</h3>
      </div>
      ${treeHtml}
      <div class="comment-composer-box">
        <h4>Leave a Comment</h4>
        ${this.renderFormMarkup(null)}
      </div>
    `;

    this.bindEvents();
  }

  /**
   * Bind reply buttons and form submissions.
   */
  bindEvents() {
    this.container.querySelectorAll(".reply-trigger-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetId = Number(btn.getAttribute("data-reply-to"));
        this.activeReplyId = this.activeReplyId === targetId ? null : targetId;
        this.render();
      });
    });

    this.container.querySelectorAll(".cancel-reply-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.activeReplyId = null;
        this.render();
      });
    });

    this.container.querySelectorAll(".comment-form").forEach((form) => {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.handleSubmit(form);
      });
    });
  }

  /**
   * Submit a comment or reply to the REST API.
   * @param {HTMLFormElement} form
   */
  async handleSubmit(form) {
    const feedback = form.querySelector(".comment-form-feedback");
    const submitBtn = form.querySelector("button[type='submit']");
    const rawParent = form.getAttribute("data-parent-id");
    const parentId = rawParent ? Number(rawParent) : null;

    const formData = new FormData(form);
    const payload = {
      author_name: String(formData.get("author_name") || "").trim(),
      author_email: String(formData.get("author_email") || "").trim(),
      body: String(formData.get("body") || "").trim(),
    };
    if (parentId) payload.parent_id = parentId;

    if (submitBtn) submitBtn.disabled = true;
    if (feedback) {
      feedback.className = "comment-form-feedback";
      feedback.textContent = "Submitting...";
    }

    try {
      const response = await fetch(
        `/api/posts/${encodeURIComponent(this.slug)}/comments`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
      const data = await response.json();

      if (!response.ok || data.status !== "success") {
        if (feedback) {
          feedback.classList.add("error");
          feedback.textContent = data.message || "Could not submit comment.";
        }
        return;
      }

      form.reset();
      if (feedback) {
        feedback.classList.add("success");
        feedback.textContent =
          "Comment submitted and queued for moderation approval.";
      }
      if (parentId) {
        this.activeReplyId = null;
      }
    } catch (err) {
      if (feedback) {
        feedback.classList.add("error");
        feedback.textContent = "Network error while submitting comment.";
      }
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }
}
