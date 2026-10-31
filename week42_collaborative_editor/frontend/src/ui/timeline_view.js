/**
 * Revision timeline drawer controller for PulsePad.
 * Manages fetching, rendering, restoring point-in-time document revisions,
 * and exporting content. Groups granular character keystrokes into clean
 * word-level checkpoints at space/punctuation boundaries.
 */

export function groupRevisionsByWord(revisions) {
  if (!revisions || revisions.length === 0) return [];

  const grouped = [];
  let currentGroup = null;

  for (const rev of revisions) {
    let op = null;
    try {
      op =
        typeof rev.operation_json === "string"
          ? JSON.parse(rev.operation_json)
          : rev.operation_json;
    } catch {
      op = null;
    }

    const components = op ? op.components || [] : [];
    const insertedChars = components
      .filter((c) => c.kind === "insert")
      .map((c) => String(c.value))
      .join("");
    const deletedCount = components
      .filter((c) => c.kind === "delete")
      .reduce((sum, c) => sum + Number(c.value), 0);

    const isWordBoundary =
      insertedChars.includes(" ") ||
      insertedChars.includes("\n") ||
      insertedChars.includes("\t") ||
      /[.,!?;:]/.test(insertedChars);

    if (!currentGroup) {
      currentGroup = {
        revision_num: rev.revision_num,
        author: rev.author,
        created_at: rev.created_at,
        insertedText: insertedChars,
        deletedCount: deletedCount,
        count: 1,
      };
    } else {
      const sameAuthor = currentGroup.author === rev.author;
      const bothTyping = currentGroup.deletedCount === 0 && deletedCount === 0;
      const bothDeleting =
        currentGroup.insertedText.length === 0 && insertedChars.length === 0;

      if (sameAuthor && (bothTyping || bothDeleting) && currentGroup.count < 60) {
        currentGroup.revision_num = rev.revision_num;
        currentGroup.created_at = rev.created_at;
        currentGroup.insertedText += insertedChars;
        currentGroup.deletedCount += deletedCount;
        currentGroup.count++;
      } else {
        grouped.push(currentGroup);
        currentGroup = {
          revision_num: rev.revision_num,
          author: rev.author,
          created_at: rev.created_at,
          insertedText: insertedChars,
          deletedCount: deletedCount,
          count: 1,
        };
      }
    }

    if (isWordBoundary && currentGroup) {
      grouped.push(currentGroup);
      currentGroup = null;
    }
  }

  if (currentGroup) {
    grouped.push(currentGroup);
  }

  return grouped;
}

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

  summarizeGroup(group) {
    if (group.insertedText && group.deletedCount > 0) {
      const ins =
        group.insertedText.length > 25
          ? `${group.insertedText.slice(0, 25)}...`
          : group.insertedText;
      return `Replaced ${group.deletedCount} chars with "${ins}"`;
    }
    if (group.insertedText) {
      const clean = group.insertedText.replace(/\n/g, "\\n");
      const display =
        clean.length > 32 ? `${clean.slice(0, 32)}...` : clean;
      return `Inserted "${display}"`;
    }
    if (group.deletedCount > 0) {
      return `Deleted ${group.deletedCount} chars`;
    }
    return "Structure modified";
  }

  formatTime(isoString) {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return isoString;
    }
  }

  render() {
    if (!this.list) return;

    if (this.revisions.length === 0) {
      this.list.innerHTML =
        '<div class="timeline-empty">No past revisions recorded yet.</div>';
      return;
    }

    // Group single-character edits into word-level checkpoints
    const groupedRevs = groupRevisionsByWord(this.revisions);

    this.list.innerHTML = "";

    // Render revisions in descending order (newest first)
    const sortedRevs = [...groupedRevs].reverse();

    sortedRevs.forEach((group) => {
      const card = document.createElement("div");
      card.className = "timeline-card";

      const header = document.createElement("div");
      header.className = "timeline-card-header";

      const badge = document.createElement("span");
      badge.className = "rev-badge";
      badge.textContent = `Rev #${group.revision_num}`;

      const author = document.createElement("span");
      author.className = "rev-author";
      author.textContent = group.author;

      header.appendChild(badge);
      header.appendChild(author);

      const time = document.createElement("div");
      time.className = "timeline-card-time";
      time.textContent = this.formatTime(group.created_at);

      const summary = document.createElement("div");
      summary.className = "timeline-card-summary";
      summary.textContent = this.summarizeGroup(group);

      const actions = document.createElement("div");
      actions.className = "timeline-card-actions";

      const restoreBtn = document.createElement("button");
      restoreBtn.className = "btn-restore";
      restoreBtn.textContent = "Restore";
      restoreBtn.addEventListener("click", () => {
        this.confirmAndRollback(group.revision_num);
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
