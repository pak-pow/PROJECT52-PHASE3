import { escapeHtml, formatDate, getIcon } from "../utils/helpers.js";

/**
 * Task Grid Component for rendering local IndexedDB tasks.
 */
export function initTaskGrid({ onToggleTask, onDeleteTask } = {}) {
  const mount = document.getElementById("tasks-mount");

  function render(tasks = []) {
    if (!mount) return;

    if (tasks.length === 0) {
      mount.innerHTML = `
        <div class="empty-state">
          ${getIcon("check", 40)}
          <h3 class="empty-state-title">No tasks found</h3>
          <p>Get started by clicking New Task above. All tasks are saved locally to IndexedDB!</p>
        </div>
      `;
      return;
    }

    mount.innerHTML = tasks.map((task) => createTaskItemHtml(task)).join("");

    // Bind Toggle Checkbox Handlers
    mount.querySelectorAll(".task-checkbox").forEach((box) => {
      box.addEventListener("change", () => {
        const taskId = box.getAttribute("data-id");
        if (typeof onToggleTask === "function") {
          onToggleTask(taskId);
        }
      });
    });

    // Bind Delete Button Handlers
    mount.querySelectorAll(".btn-delete-task").forEach((btn) => {
      btn.addEventListener("click", () => {
        const taskId = btn.getAttribute("data-id");
        if (typeof onDeleteTask === "function") {
          onDeleteTask(taskId);
        }
      });
    });
  }

  return {
    render,
  };
}

/**
 * Generates HTML string for an individual task card.
 */
function createTaskItemHtml(task) {
  const isCompleted = Boolean(task.completed);
  const priorityClass = `priority-${(task.priority || "medium").toLowerCase()}`;

  return `
    <article class="task-item ${isCompleted ? "completed" : ""}" data-id="${escapeHtml(task.id)}">
      <input 
        type="checkbox" 
        class="task-checkbox" 
        data-id="${escapeHtml(task.id)}" 
        ${isCompleted ? "checked" : ""} 
        aria-label="Mark task as ${isCompleted ? "pending" : "completed"}"
      >
      <div class="task-content">
        <h4 class="task-title">${escapeHtml(task.title)}</h4>
        ${
          task.description
            ? `<p class="task-desc">${escapeHtml(task.description)}</p>`
            : ""
        }
        <div class="task-meta">
          <span class="task-category-tag">${escapeHtml(task.category || "work")}</span>
          <span class="task-priority-tag ${priorityClass}">${escapeHtml(task.priority || "medium")}</span>
          <span class="task-timestamp">${formatDate(task.updated_at || task.created_at)}</span>
        </div>
      </div>
      <div class="task-actions">
        <button 
          type="button" 
          class="btn-icon-action btn-delete-task" 
          data-id="${escapeHtml(task.id)}" 
          aria-label="Delete task"
        >
          ${getIcon("trash", 16)}
        </button>
      </div>
    </article>
  `;
}
