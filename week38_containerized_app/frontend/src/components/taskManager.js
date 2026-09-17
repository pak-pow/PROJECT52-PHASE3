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
              <span>📋</span> Containerized Task & Operations Hub
            </div>
            <p class="benchmark-subtitle">Real-time CRUD verifying PostgreSQL persistence and automated Redis cache invalidation.</p>
          </div>
          <div class="cache-badge" id="cache-indicator">
            <span class="status-dot dot-cyan"></span> <span id="cache-text">Checking Cache...</span>
          </div>
        </div>

        <!-- Task Creation Form -->
        <form id="form-create-task" class="task-form">
          <div class="form-row">
            <input type="text" id="task-title" class="form-input" placeholder="Enter task title (e.g., Verify Docker Volume Persistence)..." required>
            <select id="task-priority" class="form-select">
              <option value="low">Low Priority</option>
              <option value="medium" selected>Medium Priority</option>
              <option value="high">High Priority</option>
              <option value="urgent">Urgent Priority</option>
            </select>
          </div>
          <div class="form-row">
            <input type="text" id="task-desc" class="form-input" placeholder="Optional description or operational note...">
            <button type="submit" class="btn btn-primary" id="btn-submit-task"><span>+</span> Create Task</button>
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
          <div class="task-loading">Loading tasks from containerized database...</div>
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
        cacheIndicator.textContent = data.xCache === 'HIT' ? 'Redis Cache: HIT' : 'PostgreSQL: MISS';
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
          <p>No tasks found for this filter. Create a new task above!</p>
        </div>
      `;
      return;
    }

    let rowsHtml = this.tasks.map(task => {
      const priorityClass = `priority-${task.priority || 'medium'}`;
      const statusClass = `status-${task.status || 'pending'}`;
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
            <select class="status-select ${statusClass}" data-action="change-status" data-id="${task.id}">
              <option value="pending" ${task.status === 'pending' ? 'selected' : ''}>Pending</option>
              <option value="in_progress" ${task.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
              <option value="completed" ${task.status === 'completed' ? 'selected' : ''}>Completed</option>
            </select>
            <button class="btn-delete" data-action="delete" data-id="${task.id}" title="Delete Task">✕</button>
          </div>
        </div>
      `;
    }).join('');

    tableContainer.innerHTML = `<div class="task-list">${rowsHtml}</div>`;
    this.attachTableEvents(tableContainer);
  }

  attachTableEvents(container) {
    container.addEventListener('change', async (e) => {
      if (e.target.getAttribute('data-action') === 'change-status') {
        const taskId = e.target.getAttribute('data-id');
        const newStatus = e.target.value;
        try {
          await opsApi.updateTaskStatus(taskId, newStatus);
          Toast.success(`Task status updated to ${newStatus}`);
          this.loadTasks(true);
        } catch (err) {
          Toast.error(err.message);
        }
      }
    });

    container.addEventListener('click', async (e) => {
      if (e.target.getAttribute('data-action') === 'delete') {
        const taskId = e.target.getAttribute('data-id');
        if (confirm('Delete this task from PostgreSQL?')) {
          try {
            await opsApi.deleteTask(taskId);
            Toast.success('Task deleted successfully');
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
      Toast.success(`Created task: ${title}`);
      titleInput.value = '';
      descInput.value = '';
      this.loadTasks(true);
    } catch (err) {
      Toast.error(err.message);
    }
  }
}