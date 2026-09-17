/**
 * Component managing operational tasks with real-time CRUD and cache telemetry.
 * 
 * The manager enables task creation, status filtering, status toggling, and deletion.
 */

import { opsApi } from '../api/opsApi.js';
import { escapeHtml, formatTimestamp } from '../utils/helpers.js';
import { Toast } from './toast.js';

export class TaskManager {
  constructor(container) {
    this.container = container;
    this.currentStatusFilter = 'all';
    this.tasks = [];
    this.loading = false;
  }

  render() {
    this.container.innerHTML = `
      <div class="section-box">
        <div class="task-manager-header">
          <div>
            <div class="section-title">
              <span>📋</span> Live Task Board
            </div>
            <p class="benchmark-subtitle">Add, start, and complete tasks to see your database and memory update in real time.</p>
          </div>
          <div class="cache-badge" id="cache-indicator">
            <span class="status-dot dot-cyan"></span> <span id="cache-text">Checking memory...</span>
          </div>
        </div>

        <!-- Task Creation Form -->
        <form id="form-create-task" class="task-form">
          <div class="form-row">
            <input type="text" id="task-title" class="form-input" placeholder="What needs to be done? (e.g., Deploy new update)..." required>
            <select id="task-priority" class="form-select">
              <option value="low">Low Priority</option>
              <option value="medium" selected>Medium Priority</option>
              <option value="high">High Priority</option>
              <option value="urgent">Urgent Priority</option>
            </select>
          </div>
          <div class="form-row">
            <input type="text" id="task-desc" class="form-input" placeholder="Add extra details or notes (optional)...">
            <button type="submit" class="btn btn-primary" id="btn-submit-task"><span>+</span> Add Task</button>
          </div>
        </form>

        <!-- Filters & Actions Toolbar -->
        <div class="toolbar">
          <div class="filter-group" id="filter-buttons">
            <button class="filter-btn active" data-filter="all">All Tasks</button>
            <button class="filter-btn" data-filter="pending">Pending</button>
            <button class="filter-btn" data-filter="in_progress">In Progress</button>
            <button class="filter-btn" data-filter="completed">Completed</button>
          </div>
          <button class="btn btn-secondary btn-sm" id="btn-refresh-tasks"><span>⟳</span> Refresh</button>
        </div>

        <!-- Task Table / List -->
        <div id="task-table-container">
          <div class="task-loading">Loading tasks...</div>
        </div>
      </div>
    `;

    this.attachEvents();
    this.loadTasks();
  }

  attachEvents() {
    // Form submit
    const form = this.container.querySelector('#form-create-task');
    if (form) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        this.handleCreateTask();
      });
    }

    // Refresh button
    const btnRefresh = this.container.querySelector('#btn-refresh-tasks');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => this.loadTasks(true));
    }

    // Filter buttons
    const filterGroup = this.container.querySelector('#filter-buttons');
    if (filterGroup) {
      filterGroup.addEventListener('click', (e) => {
        if (e.target.classList.contains('filter-btn')) {
          filterGroup.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
          e.target.classList.add('active');
          this.currentStatusFilter = e.target.getAttribute('data-filter');
          this.loadTasks();
        }
      });
    }
  }

  async loadTasks(forceRefresh = false) {
    if (this.loading) return;
    this.loading = true;

    const tableContainer = this.container.querySelector('#task-table-container');
    const cacheIndicator = this.container.querySelector('#cache-text');

    try {
      const data = await opsApi.getTasks({
        status: this.currentStatusFilter,
        noCache: forceRefresh,
      });

      this.tasks = data.tasks || [];
      if (cacheIndicator) {
        cacheIndicator.textContent = data.xCache === 'HIT' ? '⚡ Loaded from Fast Memory (Redis)' : '💾 Loaded from Hard Drive (PostgreSQL)';
        const parent = cacheIndicator.parentElement;
        parent.className = data.xCache === 'HIT' ? 'cache-badge badge-hit' : 'cache-badge badge-miss';
      }

      this.renderTable();
    } catch (err) {
      tableContainer.innerHTML = `<div class="task-error">Error loading tasks: ${escapeHtml(err.message)}</div>`;
    } finally {
      this.loading = false;
    }
  }

  renderTable() {
    const tableContainer = this.container.querySelector('#task-table-container');

    if (this.tasks.length === 0) {
      tableContainer.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">📂</span>
          <p>No tasks found in this view. Add a new task above!</p>
        </div>
      `;
      return;
    }

    let rowsHtml = this.tasks.map(task => {
      const priorityClass = `priority-${task.priority || 'medium'}`;
      const status = task.status || 'pending';

      let statusBadge = '';
      let quickActionBtn = '';

      if (status === 'pending') {
        statusBadge = '<span class="badge-status badge-status-pending">⏳ Pending</span>';
        quickActionBtn = `<button class="btn-quick-action btn-action-start" data-action="quick-status" data-id="${task.id}" data-next-status="in_progress" title="Start Task">▶ Start</button>`;
      } else if (status === 'in_progress') {
        statusBadge = '<span class="badge-status badge-status-progress">⚙️ In Progress</span>';
        quickActionBtn = `<button class="btn-quick-action btn-action-complete" data-action="quick-status" data-id="${task.id}" data-next-status="completed" title="Mark as Completed">✓ Done</button>`;
      } else {
        statusBadge = '<span class="badge-status badge-status-completed">✓ Completed</span>';
        quickActionBtn = `<button class="btn-quick-action btn-action-reopen" data-action="quick-status" data-id="${task.id}" data-next-status="pending" title="Reset to Pending">↺ Reset</button>`;
      }

      return `
        <div class="task-row" data-id="${task.id}">
          <div class="task-main">
            <div class="task-title-line">
              <span class="task-title">${escapeHtml(task.title)}</span>
              <span class="badge ${priorityClass}">${escapeHtml(task.priority)}</span>
            </div>
            ${task.description ? `<p class="task-desc-text">${escapeHtml(task.description)}</p>` : ''}
            <span class="task-timestamp">Created: ${formatTimestamp(task.created_at)}</span>
          </div>

          <div class="task-actions">
            ${statusBadge}
            ${quickActionBtn}
            <button class="btn-delete" data-action="delete" data-id="${task.id}" title="Delete Task">✕</button>
          </div>
        </div>
      `;
    }).join('');

    tableContainer.innerHTML = `<div class="task-list">${rowsHtml}</div>`;
    this.attachTableEvents(tableContainer);
  }

  attachTableEvents(container) {
    container.addEventListener('click', async (e) => {
      // 1-click status stepper progression
      const actionBtn = e.target.closest('[data-action="quick-status"]');
      if (actionBtn) {
        const taskId = actionBtn.getAttribute('data-id');
        const nextStatus = actionBtn.getAttribute('data-next-status');
        try {
          actionBtn.disabled = true;
          actionBtn.textContent = '...';
          await opsApi.updateTaskStatus(taskId, nextStatus);
          const labels = { in_progress: 'In Progress', completed: 'Completed', pending: 'Pending' };
          Toast.success(`Task moved to ${labels[nextStatus] || nextStatus}`);
          this.loadTasks(true);
        } catch (err) {
          Toast.error(err.message);
        }
        return;
      }

      // Delete task confirmation
      if (e.target.getAttribute('data-action') === 'delete') {
        const taskId = e.target.getAttribute('data-id');
        if (confirm('Are you sure you want to delete this task?')) {
          try {
            await opsApi.deleteTask(taskId);
            Toast.success('Task deleted');
            this.loadTasks(true);
          } catch (err) {
            Toast.error(err.message);
          }
        }
      }
    });
  }

  async handleCreateTask() {
    const titleInput = this.container.querySelector('#task-title');
    const prioritySelect = this.container.querySelector('#task-priority');
    const descInput = this.container.querySelector('#task-desc');

    const title = titleInput.value.trim();
    const priority = prioritySelect.value;
    const description = descInput.value.trim();

    if (!title) return;

    try {
      await opsApi.createTask({ title, priority, description, status: 'pending' });
      Toast.success(`Task added: ${title}`);
      titleInput.value = '';
      descInput.value = '';
      this.loadTasks(true);
    } catch (err) {
      Toast.error(err.message);
    }
  }
}