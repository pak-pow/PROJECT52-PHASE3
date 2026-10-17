/**
 * Remote cursor positioning, OT cursor shifting, and visual caret overlay.
 */

import { OpKind } from "./client_ot.js";

export function transformCursorPosition(cursorPos, operation) {
  if (cursorPos <= 0) {
    let newPos = 0;
    for (const comp of operation.components) {
      if (comp.kind === OpKind.INSERT) {
        newPos += String(comp.value).length;
      } else {
        break;
      }
    }
    return newPos;
  }

  let newPos = 0;
  let origPos = 0;

  for (const comp of operation.components) {
    if (comp.kind === OpKind.RETAIN) {
      const count = Number(comp.value);
      if (cursorPos < origPos + count) {
        return newPos + (cursorPos - origPos);
      }
      newPos += count;
      origPos += count;
    } else if (comp.kind === OpKind.INSERT) {
      newPos += String(comp.value).length;
    } else if (comp.kind === OpKind.DELETE) {
      const count = Number(comp.value);
      const delEnd = origPos + count;
      if (cursorPos < delEnd) {
        return newPos;
      }
      origPos = delEnd;
    }
  }

  return Math.min(newPos, operation.targetLength);
}

export function transformSelection(start, end, operation) {
  const newStart = transformCursorPosition(start, operation);
  if (end === null || end === undefined) {
    return [newStart, null];
  }
  const newEnd = transformCursorPosition(end, operation);
  return [newStart, newEnd];
}

export class CursorTracker {
  constructor(overlayContainer, textarea) {
    this.overlay = overlayContainer;
    this.textarea = textarea;
    this.remoteCursors = new Map(); // sid -> { user_name, color, cursor_pos, selection_end, is_typing }
    this.lineHeight = 22.4; // 14px * 1.6 line-height
    this.charWidth = 8.42; // Fallback mono char width
    this.paddingTop = 16;
    this.paddingLeft = 16;
    this._measureFont();
  }

  _measureFont() {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.font = "14px JetBrains Mono, Fira Code, monospace";
      const metrics = ctx.measureText("M");
      if (metrics.width > 0) {
        this.charWidth = metrics.width;
      }
    }
  }

  updateRemoteCursor(sid, data) {
    const existing = this.remoteCursors.get(sid) || {};
    this.remoteCursors.set(sid, {
      ...existing,
      ...data,
      cursor_pos: data.cursor_pos !== undefined ? data.cursor_pos : existing.cursor_pos || 0,
      selection_end: data.selection_end !== undefined ? data.selection_end : existing.selection_end || null,
    });
    this.render();
  }

  removeRemoteCursor(sid) {
    this.remoteCursors.delete(sid);
    this.render();
  }

  transformAll(operation) {
    for (const [sid, cursor] of this.remoteCursors.entries()) {
      const [newStart, newEnd] = transformSelection(cursor.cursor_pos, cursor.selection_end, operation);
      cursor.cursor_pos = newStart;
      cursor.selection_end = newEnd;
    }
    this.render();
  }

  _getCoordinates(index, text) {
    const clampedIndex = Math.max(0, Math.min(index, text.length));
    const linesBefore = text.slice(0, clampedIndex).split("\n");
    const row = linesBefore.length - 1;
    const col = linesBefore[linesBefore.length - 1].length;

    const scrollTop = this.textarea ? this.textarea.scrollTop : 0;
    const scrollLeft = this.textarea ? this.textarea.scrollLeft : 0;

    const top = this.paddingTop + row * this.lineHeight - scrollTop;
    const left = this.paddingLeft + col * this.charWidth - scrollLeft;
    return { top, left };
  }

  render() {
    if (!this.overlay) return;
    this.overlay.innerHTML = "";

    const text = this.textarea ? this.textarea.value : "";

    for (const [sid, cursor] of this.remoteCursors.entries()) {
      const coords = this._getCoordinates(cursor.cursor_pos, text);

      // Render vertical caret bar
      const caretEl = document.createElement("div");
      caretEl.className = "remote-caret";
      caretEl.style.backgroundColor = cursor.color || "#3b82f6";
      caretEl.style.top = `${coords.top}px`;
      caretEl.style.left = `${coords.left}px`;

      // Render floating name tag
      const tagEl = document.createElement("div");
      tagEl.className = "remote-tag";
      tagEl.style.backgroundColor = cursor.color || "#3b82f6";
      tagEl.textContent = cursor.user_name || "Anonymous";
      if (cursor.is_typing) {
        tagEl.textContent += " (typing...)";
      }

      caretEl.appendChild(tagEl);
      this.overlay.appendChild(caretEl);
    }
  }
}
