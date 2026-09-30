import { getIcon } from "../utils/helpers.js";

/**
 * Task Creation & Editing Modal Component
 */
export function initTaskModal({ onSaveTask } = {}) {
  const mount = document.getElementById("modal-mount");
  let isOpen = false;

  function render() {
    if (!mount) return;

    mount.innerHTML = `
      <div id="task-modal-overlay" class="modal-overlay" aria-hidden="true">
        <div class="modal-card" role="dialog" aria-labelledby="modal-task-title" aria-modal="true">
          <div class="modal-header">
            <h3 id="modal-task-title" class="modal-title">Create New Task</h3>
            <button type="button" id="btn-close-modal" class="modal-close-btn" aria-label="Close modal">
              ${getIcon("close", 18)}
            </button>
          </div>
          <form id="task-form">
            <div class="modal-body">
              <div class="form-group">
                <label for="task-title-input" class="form-label">Task Title *</label>
                <input 
                  type="text" 
                  id="task-title-input" 
                  name="title" 
                  placeholder="e.g., Audit IndexedDB storage limits" 
                  required 
                  maxlength="120"
                >
              </div>

              <div class="form-group">
                <label for="task-desc-input" class="form-label">Description (Optional)</label>
                <textarea 
                  id="task-desc-input" 
                  name="description" 
                  rows="3" 
                  placeholder="Add any specific steps or context..."
                  maxlength="500"
                ></textarea>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label for="task-category-select" class="form-label">Category</label>
                  <select id="task-category-select" name="category">
                    <option value="work" selected>Work</option>
                    <option value="personal">Personal</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>

                <div class="form-group">
                  <label for="task-priority-select" class="form-label">Priority</label>
                  <select id="task-priority-select" name="priority">
                    <option value="low">Low</option>
                    <option value="medium" selected>Medium</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
              </div>
            </div>

            <div class="modal-footer">
              <button type="button" id="btn-cancel-modal" class="btn filter-btn">Cancel</button>
              <button type="submit" class="btn btn-add-task">
                ${getIcon("plus", 14)}
                <span>Save to IndexedDB</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    `;

    const overlay = mount.querySelector("#task-modal-overlay");
    const closeBtn = mount.querySelector("#btn-close-modal");
    const cancelBtn = mount.querySelector("#btn-cancel-modal");
    const form = mount.querySelector("#task-form");

    function closeModal() {
      if (!overlay) return;
      overlay.classList.remove("open");
      overlay.setAttribute("aria-hidden", "true");
      if (form) form.reset();
      isOpen = false;
    }

    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

    if (overlay) {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeModal();
      });
    }

    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const formData = new FormData(form);
        const title = (formData.get("title") || "").trim();
        if (!title) return;

        const taskData = {
          title,
          description: (formData.get("description") || "").trim(),
          category: formData.get("category") || "work",
          priority: formData.get("priority") || "medium",
          completed: false,
        };

        if (typeof onSaveTask === "function") {
          await onSaveTask(taskData);
        }

        closeModal();
      });
    }
  }

  function open() {
    const overlay = document.getElementById("task-modal-overlay");
    if (overlay) {
      overlay.classList.add("open");
      overlay.setAttribute("aria-hidden", "false");
      const titleInput = document.getElementById("task-title-input");
      if (titleInput) titleInput.focus();
      isOpen = true;
    }
  }

  return {
    render,
    open,
  };
}
