/**
 * Revision timeline drawer controller for PulsePad.
 * Manages fetching, rendering, restoring point-in-time document revisions,
 * and exporting content.
 */

export class TimelineView {
  constructor({
    drawerElement,
    listElement,
    docId,
    serverUrl,
    onRollback,
  }) {
    this.drawer = drawerElement;
    this.list = listElement;
    this.docId = docId;
    this.serverUrl = serverUrl;
    this.onRollback = onRollback;
    this.revisions = [];
  }

  isOpen() {
    return this.drawer && !this.drawer.classList.contains("hidden");
  }

  open() {
    if (!this.drawer) return;
    this.drawer.classList.remove("hidden");
    this.fetchRevisions();
  }

  close() {
    if (!this.drawer) return;
    this.drawer.classList.add("hidden");
  }

  toggle() {
    if (this.isOpen()) {
      this.close();
      return false;
    } else {
      this.open();
      return true;
    }
  }

  async fetchRevisions() {
    if (!this.list) return;
    this.list.innerHTML = '<div class="timeline-empty">Loading history...</div>';

    try {
      const response = await fetch(
        `${this.serverUrl}/api/documents/${this.docId}/revisions`
      );
      if (!response.ok) {
        throw new Error(`Failed to fetch revisions: ${response.status}`);
      }
      const data = await response.json();
      this.revisions = data.revisions || [];
      this.render();
    } catch (err) {
      this.list.innerHTML = `<div class="timeline-empty">Error loading history: ${err.message}</div>`;
    }
  }

  summarizeOperation(operationJson) {
    if (!operationJson) return "Text modified";
    try {
      const op = JSON.parse(operationJson);
      const components = op.components || [];
      const parts = [];

      let inserts = 0;
      let deletes = 0;

      for (const comp of components) {
        if (comp.kind === "insert") {
          inserts += String(comp.value).length;
        } else if (comp.kind === "delete") {
          deletes += Number(comp.value);
        }
      }

      if (inserts > 0) parts.push(`Inserted ${inserts} chars`);
      if (deletes > 0) parts.push(`Deleted ${deletes} chars`);
      return parts.length > 0 ? parts.join(", ") : "Maintained structure";
    } catch {
      return "Edit recorded";
    }
  }

  formatTime(isoString) {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return isoString;
    }
  }

  render() {
    if (!this.list) return;

    if (this.revisions.length === 0) {
      this.list.innerHTML = '<div class="timeline-empty">No past revisions recorded yet.</div>';
      return;
    }

    this.list.innerHTML = "";

    // Render revisions in descending order (newest first)
    const sortedRevs = [...this.revisions].reverse();

    sortedRevs.forEach((rev) => {
      const card = document.createElement("div");
      card.className = "timeline-card";

      const header = document.createElement("div");
      header.className = "timeline-card-header";

      const badge = document.createElement("span");
      badge.className = "rev-badge";
      badge.textContent = `Rev #${rev.revision_num}`;

      const author = document.createElement("span");
      author.className = "rev-author";
      author.textContent = rev.author;

      header.appendChild(badge);
      header.appendChild(author);

      const time = document.createElement("div");
      time.className = "timeline-card-time";
      time.textContent = this.formatTime(rev.created_at);

      const summary = document.createElement("div");
      summary.className = "timeline-card-summary";
      summary.textContent = this.summarizeOperation(rev.operation_json);

      const actions = document.createElement("div");
      actions.className = "timeline-card-actions";

      const restoreBtn = document.createElement("button");
      restoreBtn.className = "btn-restore";
      restoreBtn.textContent = "Restore";
      restoreBtn.addEventListener("click", () => {
        this.confirmAndRollback(rev.revision_num);
      });

      actions.appendChild(restoreBtn);

      card.appendChild(header);
      card.appendChild(time);
      card.appendChild(summary);
      card.appendChild(actions);

      this.list.appendChild(card);
    });
  }

  async confirmAndRollback(targetRevision) {
    const confirmed = window.confirm(
      `Revert document to revision #${targetRevision}? This will create a new append-only revision.`
    );
    if (!confirmed) return;

    try {
      const response = await fetch(
        `${this.serverUrl}/api/documents/${this.docId}/rollback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_revision: targetRevision,
            author: "User Rollback",
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Rollback failed");
      }

      const result = await response.json();
      if (this.onRollback) {
        this.onRollback(result);
      }
      this.fetchRevisions();
    } catch (err) {
      window.alert(`Rollback failed: ${err.message}`);
    }
  }

  exportDocument(format) {
    const url = `${this.serverUrl}/api/documents/${this.docId}/export?format=${format}`;
    window.open(url, "_blank");
  }
}
