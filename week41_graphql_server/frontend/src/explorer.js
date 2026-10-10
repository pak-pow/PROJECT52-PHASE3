/**
 * PulseGraph GraphQL Explorer - Core Client Controller
 *
 * Orchestrates query execution, template loading, SDL schema documentation,
 * performance profiling dashboards, and localStorage history.
 */

import {
  escapeHtml,
  executeGraphQL,
  fetchSchemaSDL,
  formatJson,
  HistoryManager,
  QUERY_TEMPLATES,
  syntaxHighlightJson,
} from "./utils/helpers.js";

// Application State
const state = {
  endpoint:
    localStorage.getItem("pulsegraph_endpoint") ||
    "http://127.0.0.1:5000/graphql",
  authToken: localStorage.getItem("pulsegraph_auth_token") || "",
  sidebarTab: "templates",
  resultsTab: "response",
  lastResult: null,
  schemaSDL: null,
  isExecuting: false,
};

// DOM References
const dom = {
  endpointInput: document.getElementById("endpoint-input"),
  authTokenInput: document.getElementById("auth-token-input"),
  btnToggleSidebar: document.getElementById("btn-toggle-sidebar"),
  btnPrettify: document.getElementById("btn-prettify"),
  btnRun: document.getElementById("btn-run"),
  workbench: document.getElementById("workbench"),
  sidebar: document.getElementById("sidebar"),
  sidebarContent: document.getElementById("sidebar-content"),
  sidebarTabBtns: document.querySelectorAll(".sidebar-tab-btn"),
  queryEditor: document.getElementById("query-editor"),
  lineNumbers: document.getElementById("line-numbers"),
  editorStatus: document.getElementById("editor-status"),
  variablesDrawer: document.getElementById("variables-drawer"),
  drawerHeader: document.getElementById("drawer-header"),
  variablesEditor: document.getElementById("variables-editor"),
  resultsTabBtns: document.querySelectorAll(".results-tab-btn"),
  resultsViewer: document.getElementById("results-viewer"),
  emptyResults: document.getElementById("empty-results"),
  codeOutput: document.getElementById("code-output"),
  performanceView: document.getElementById("performance-view"),
  sdlOutput: document.getElementById("sdl-output"),
  headersView: document.getElementById("headers-view"),
  pillDuration: document.getElementById("pill-duration"),
  pillStatus: document.getElementById("pill-status"),
  statusBeacon: document.getElementById("status-beacon"),
  statusMessage: document.getElementById("status-message"),
  statusMetricsDetail: document.getElementById("status-metrics-detail"),
};

/**
 * Initializes the GraphQL Explorer application on DOM ready.
 */
function init() {
  // Sync endpoint and auth input
  dom.endpointInput.value = state.endpoint;
  if (dom.authTokenInput) {
    dom.authTokenInput.value = state.authToken;
  }

  // Setup initial template
  if (QUERY_TEMPLATES.length > 0) {
    loadTemplate(QUERY_TEMPLATES[0]);
  }

  setupEventListeners();
  updateLineNumbers();
  renderSidebar();
}

/**
 * Attaches UI event listeners and keyboard shortcuts.
 */
function setupEventListeners() {
  // Endpoint input change
  dom.endpointInput.addEventListener("change", (e) => {
    state.endpoint = e.target.value.trim();
    localStorage.setItem("pulsegraph_endpoint", state.endpoint);
    state.schemaSDL = null; // Invalidate cached SDL
  });

  // Auth token input change
  if (dom.authTokenInput) {
    dom.authTokenInput.addEventListener("change", (e) => {
      state.authToken = e.target.value.trim();
      localStorage.setItem("pulsegraph_auth_token", state.authToken);
    });
  }

  // Run query button
  dom.btnRun.addEventListener("click", () => {
    handleRunQuery();
  });

  // Prettify query and variables
  dom.btnPrettify.addEventListener("click", () => {
    handlePrettify();
  });

  // Toggle Sidebar
  dom.btnToggleSidebar.addEventListener("click", () => {
    dom.sidebar.classList.toggle("collapsed");
  });

  // Variables drawer toggle
  dom.drawerHeader.addEventListener("click", () => {
    dom.variablesDrawer.classList.toggle("collapsed");
  });

  // Sidebar Tab buttons
  dom.sidebarTabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      dom.sidebarTabBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.sidebarTab = btn.dataset.tab;
      renderSidebar();
    });
  });

  // Results Tab buttons
  dom.resultsTabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      dom.resultsTabBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.resultsTab = btn.dataset.tab;
      renderResultsView();
    });
  });

  // Synchronized line numbering and tab key handling for query textarea
  dom.queryEditor.addEventListener("input", () => {
    updateLineNumbers();
  });

  dom.queryEditor.addEventListener("scroll", () => {
    dom.lineNumbers.scrollTop = dom.queryEditor.scrollTop;
  });

  dom.queryEditor.addEventListener("keydown", handleTextareaKeydown);
  dom.variablesEditor.addEventListener("keydown", handleTextareaKeydown);

  // Global keyboard shortcuts (Ctrl+Enter / Cmd+Enter to execute)
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleRunQuery();
    }
  });
}

/**
 * Handles Tab indentation and Enter execution within code textareas.
 * @param {KeyboardEvent} e - Keydown event.
 */
function handleTextareaKeydown(e) {
  if (e.key === "Tab") {
    e.preventDefault();
    const target = e.target;
    const start = target.selectionStart;
    const end = target.selectionEnd;

    target.value =
      target.value.substring(0, start) + "  " + target.value.substring(end);
    target.selectionStart = target.selectionEnd = start + 2;

    if (target === dom.queryEditor) {
      updateLineNumbers();
    }
  }
}

/**
 * Updates line numbers gutter based on current editor line count.
 */
function updateLineNumbers() {
  const lines = dom.queryEditor.value.split("\n").length;
  dom.lineNumbers.textContent = Array.from(
    { length: Math.max(lines, 1) },
    (_, i) => i + 1
  ).join("\n");
  dom.editorStatus.textContent = `Lines: ${lines}`;
}

/**
 * Loads a query template into the editor panes.
 * @param {object} template - Query template definition.
 */
function loadTemplate(template) {
  dom.queryEditor.value = template.query;
  dom.variablesEditor.value = template.variables || "";
  updateLineNumbers();

  // If variables are populated, expand the drawer
  if (template.variables && template.variables.trim().length > 0) {
    dom.variablesDrawer.classList.remove("collapsed");
  }

  dom.statusMessage.textContent = `Loaded template: ${template.title}`;
}

/**
 * Prettifies query and variables content.
 */
function handlePrettify() {
  const varsVal = dom.variablesEditor.value.trim();
  if (varsVal.length > 0) {
    try {
      dom.variablesEditor.value = formatJson(varsVal);
    } catch {
      dom.statusMessage.textContent = "Warning: Variables contains invalid JSON";
    }
  }
  dom.statusMessage.textContent = "Editor content formatted";
}

/**
 * Dispatches query execution against the target GraphQL endpoint.
 */
async function handleRunQuery() {
  const queryStr = dom.queryEditor.value.trim();
  if (!queryStr) {
    dom.statusMessage.textContent = "Cannot execute empty query.";
    return;
  }

  state.isExecuting = true;
  dom.btnRun.disabled = true;
  dom.btnRun.textContent = "Running...";
  dom.statusBeacon.className = "status-indicator";
  dom.statusMessage.textContent = "Executing GraphQL request...";

  try {
    const result = await executeGraphQL(
      state.endpoint,
      queryStr,
      dom.variablesEditor.value.trim(),
      null,
      state.authToken
    );

    // Auto-capture token from login mutation
    if (result.data && result.data.login && result.data.login.token) {
      state.authToken = result.data.login.token;
      if (dom.authTokenInput) {
        dom.authTokenInput.value = state.authToken;
      }
      localStorage.setItem("pulsegraph_auth_token", state.authToken);
    }

    state.lastResult = result;
    HistoryManager.addEntry(
      queryStr,
      dom.variablesEditor.value.trim(),
      result.serverDurationMs || result.clientDurationMs,
      result.status
    );

    // Update Pills
    dom.pillDuration.textContent = `${result.serverDurationMs || result.clientDurationMs} ms`;
    if (result.ok && (!result.errors || result.errors.length === 0)) {
      dom.pillStatus.textContent = `HTTP ${result.status} OK`;
      dom.pillStatus.className = "metric-pill success";
      dom.statusBeacon.className = "status-indicator";
      dom.statusMessage.textContent = "Query executed successfully";
    } else {
      dom.pillStatus.textContent = `HTTP ${result.status || 400} ERROR`;
      dom.pillStatus.className = "metric-pill danger";
      dom.statusBeacon.className = "status-indicator offline";
      dom.statusMessage.textContent =
        result.errors && result.errors[0]
          ? result.errors[0].message
          : "Execution returned errors";
    }

    // Update status footer metrics
    if (result.extensions) {
      const ext = result.extensions;
      const loaderHits = ext.dataloaders ? ext.dataloaders.cache_hits : 0;
      const loaderMisses = ext.dataloaders ? ext.dataloaders.cache_misses : 0;
      dom.statusMetricsDetail.textContent = `Depth: ${ext.depth || 1} | Complexity: ${ext.complexity || 1} | Loader Hits: ${loaderHits} | Misses: ${loaderMisses}`;
    }

    renderResultsView();

    // If history tab is open, re-render it
    if (state.sidebarTab === "history") {
      renderSidebar();
    }
  } catch (err) {
    dom.pillStatus.textContent = "ERROR";
    dom.pillStatus.className = "metric-pill danger";
    dom.statusBeacon.className = "status-indicator offline";
    dom.statusMessage.textContent = `Client Error: ${err.message}`;
  } finally {
    state.isExecuting = false;
    dom.btnRun.disabled = false;
    dom.btnRun.textContent = "Run Query";
  }
}

/**
 * Renders the results view depending on the active tab.
 */
function renderResultsView() {
  const { resultsTab, lastResult } = state;

  dom.emptyResults.style.display = "none";
  dom.codeOutput.style.display = "none";
  dom.performanceView.style.display = "none";
  dom.sdlOutput.style.display = "none";
  dom.headersView.style.display = "none";

  if (!lastResult && resultsTab !== "sdl") {
    dom.emptyResults.style.display = "flex";
    return;
  }

  if (resultsTab === "response") {
    dom.codeOutput.style.display = "block";
    const payload = {};
    if (lastResult.data !== null && lastResult.data !== undefined) {
      payload.data = lastResult.data;
    }
    if (lastResult.errors) {
      payload.errors = lastResult.errors;
    }
    if (lastResult.extensions) {
      payload.extensions = lastResult.extensions;
    }

    const formatted = formatJson(payload);
    dom.codeOutput.innerHTML = syntaxHighlightJson(formatted);
  } else if (resultsTab === "performance") {
    dom.performanceView.style.display = "block";
    renderPerformanceDashboard(lastResult);
  } else if (resultsTab === "sdl") {
    dom.sdlOutput.style.display = "block";
    renderSdlView();
  } else if (resultsTab === "headers") {
    dom.headersView.style.display = "block";
    renderHeadersView(lastResult);
  }
}

/**
 * Renders the Performance Profiling Dashboard tab.
 * @param {object} res - Execution result.
 */
function renderPerformanceDashboard(res) {
  const ext = res.extensions || {};
  const depth = ext.depth !== undefined ? ext.depth : "-";
  const complexity = ext.complexity !== undefined ? ext.complexity : "-";
  const serverDur = res.serverDurationMs || "-";
  const clientDur = res.clientDurationMs || "-";
  const loaders = ext.dataloaders || {
    cache_hits: 0,
    cache_misses: 0,
    batch_loads: 0,
  };

  const totalOps = (loaders.cache_hits || 0) + (loaders.cache_misses || 0);
  const hitRatio =
    totalOps > 0 ? Math.round((loaders.cache_hits / totalOps) * 100) : 0;

  dom.performanceView.innerHTML = `
    <div class="performance-grid">
      <div class="perf-card">
        <div class="perf-card-title">Server Execution Duration</div>
        <div class="perf-card-value">${serverDur} ms</div>
        <div class="perf-card-detail">Client roundtrip: ${clientDur} ms</div>
      </div>

      <div class="perf-card">
        <div class="perf-card-title">DataLoader Cache Hit Ratio</div>
        <div class="perf-card-value">${hitRatio}%</div>
        <div class="perf-card-detail">${loaders.cache_hits || 0} hits / ${totalOps} entity requests</div>
      </div>

      <div class="perf-card">
        <div class="perf-card-title">AST Query Depth</div>
        <div class="perf-card-value">${depth}</div>
        <div class="perf-card-detail">Max Allowed Budget: 7 levels</div>
      </div>

      <div class="perf-card">
        <div class="perf-card-title">AST Query Complexity</div>
        <div class="perf-card-value">${complexity}</div>
        <div class="perf-card-detail">Max Allowed Budget: 300 points</div>
      </div>
    </div>

    <div class="perf-card">
      <div class="perf-card-title">DataLoader Batch Metrics</div>
      <table class="table-stats">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Count</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Batch Loads Executed</td>
            <td>${loaders.batch_loads || 0}</td>
            <td>Database queries resolved via batching</td>
          </tr>
          <tr>
            <td>In-Memory Cache Hits</td>
            <td>${loaders.cache_hits || 0}</td>
            <td>Entities resolved instantly from request cache</td>
          </tr>
          <tr>
            <td>Cache Misses</td>
            <td>${loaders.cache_misses || 0}</td>
            <td>Entities loaded from persistence layer</td>
          </tr>
        </tbody>
      </table>
    </div>
  `;
}

/**
 * Renders the Schema Definition Language (SDL) view.
 */
async function renderSdlView() {
  if (!state.schemaSDL) {
    dom.sdlOutput.textContent = "Fetching schema SDL from server...";
    try {
      state.schemaSDL = await fetchSchemaSDL(state.endpoint);
    } catch (err) {
      dom.sdlOutput.textContent = `Error loading SDL: ${err.message}`;
      return;
    }
  }
  dom.sdlOutput.textContent = state.schemaSDL;
}

/**
 * Renders the raw response headers table.
 * @param {object} res - Execution result.
 */
function renderHeadersView(res) {
  if (!res.rawHeaders || Object.keys(res.rawHeaders).length === 0) {
    dom.headersView.innerHTML = "<p>No headers available.</p>";
    return;
  }

  const rows = Object.entries(res.rawHeaders)
    .map(
      ([key, val]) =>
        `<tr><td><strong>${escapeHtml(key)}</strong></td><td>${escapeHtml(val)}</td></tr>`
    )
    .join("");

  dom.headersView.innerHTML = `
    <table class="table-stats">
      <thead>
        <tr><th>Header</th><th>Value</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

/**
 * Renders the left sidebar drawer based on current active tab.
 */
function renderSidebar() {
  const { sidebarTab } = state;
  dom.sidebarContent.innerHTML = "";

  if (sidebarTab === "templates") {
    renderTemplatesSidebar();
  } else if (sidebarTab === "docs") {
    renderDocsSidebar();
  } else if (sidebarTab === "history") {
    renderHistorySidebar();
  }
}

/**
 * Renders the templates selection list in the sidebar.
 */
function renderTemplatesSidebar() {
  const categories = ["Auth", "Queries", "Mutations", "Performance", "Protection"];

  categories.forEach((cat) => {
    const items = QUERY_TEMPLATES.filter((t) => t.category === cat);
    if (items.length === 0) return;

    const groupTitle = document.createElement("div");
    groupTitle.className = "template-group-title";
    groupTitle.textContent = cat;
    dom.sidebarContent.appendChild(groupTitle);

    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "template-card";
      card.innerHTML = `
        <div class="template-card-title">${escapeHtml(item.title)}</div>
        <div class="template-card-desc">${escapeHtml(item.description)}</div>
      `;
      card.addEventListener("click", () => {
        loadTemplate(item);
      });
      dom.sidebarContent.appendChild(card);
    });
  });
}

/**
 * Renders the schema documentation viewer in the sidebar.
 */
async function renderDocsSidebar() {
  dom.sidebarContent.innerHTML = "<p>Loading schema types...</p>";

  if (!state.schemaSDL) {
    try {
      state.schemaSDL = await fetchSchemaSDL(state.endpoint);
    } catch (err) {
      dom.sidebarContent.innerHTML = `<p class="badge badge-danger">Failed to load schema: ${escapeHtml(err.message)}</p>`;
      return;
    }
  }

  // Parse SDL types and queries
  const types = extractTypesFromSDL(state.schemaSDL);

  dom.sidebarContent.innerHTML = `
    <div class="docs-section">
      <div class="docs-section-title">Query Operations</div>
      ${types.queries
        .map(
          (q) => `
        <div class="docs-item">
          <span class="docs-item-name">${escapeHtml(q.name)}</span>: 
          <span class="docs-item-type">${escapeHtml(q.type)}</span>
          ${q.desc ? `<div class="docs-item-desc">${escapeHtml(q.desc)}</div>` : ""}
        </div>
      `
        )
        .join("")}
    </div>

    <div class="docs-section">
      <div class="docs-section-title">Mutation Operations</div>
      ${types.mutations
        .map(
          (m) => `
        <div class="docs-item">
          <span class="docs-item-name">${escapeHtml(m.name)}</span>: 
          <span class="docs-item-type">${escapeHtml(m.type)}</span>
        </div>
      `
        )
        .join("")}
    </div>

    <div class="docs-section">
      <div class="docs-section-title">Object Types</div>
      ${types.objects
        .map(
          (obj) => `
        <div class="docs-item">
          <span class="docs-item-name">${escapeHtml(obj.name)}</span>
        </div>
      `
        )
        .join("")}
    </div>
  `;
}

/**
 * Extracts types, queries, and mutations from raw SDL string.
 * @param {string} sdl - Raw SDL.
 * @returns {object} Categorized types object.
 */
function extractTypesFromSDL(sdl) {
  const queries = [];
  const mutations = [];
  const objects = [];

  // Parse type Query
  const queryMatch = sdl.match(/type Query\s*{([^}]+)}/s);
  if (queryMatch) {
    const lines = queryMatch[1].split("\n");
    lines.forEach((line) => {
      const match = line.trim().match(/^([A-Za-z0-9_]+)(\([^)]+\))?:\s*(.+)$/);
      if (match) {
        queries.push({ name: match[1], type: match[3] });
      }
    });
  }

  // Parse type Mutation
  const mutMatch = sdl.match(/type Mutation\s*{([^}]+)}/s);
  if (mutMatch) {
    const lines = mutMatch[1].split("\n");
    lines.forEach((line) => {
      const match = line.trim().match(/^([A-Za-z0-9_]+)(\([^)]+\))?:\s*(.+)$/);
      if (match) {
        mutations.push({ name: match[1], type: match[3] });
      }
    });
  }

  // Parse object types
  const typeMatches = sdl.matchAll(/type\s+([A-Za-z0-9_]+)/g);
  for (const m of typeMatches) {
    if (m[1] !== "Query" && m[1] !== "Mutation") {
      objects.push({ name: m[1] });
    }
  }

  return { queries, mutations, objects };
}

/**
 * Renders the query history list in the sidebar.
 */
function renderHistorySidebar() {
  const history = HistoryManager.getHistory();

  if (history.length === 0) {
    dom.sidebarContent.innerHTML = `
      <p class="empty-results-title">No History</p>
      <p style="font-size: 11px; color: var(--text-muted);">Executed queries will automatically appear here.</p>
    `;
    return;
  }

  const clearBtn = document.createElement("button");
  clearBtn.className = "btn btn-secondary";
  clearBtn.style.width = "100%";
  clearBtn.style.marginBottom = "10px";
  clearBtn.textContent = "Clear History";
  clearBtn.addEventListener("click", () => {
    HistoryManager.clearHistory();
    renderHistorySidebar();
  });
  dom.sidebarContent.appendChild(clearBtn);

  history.forEach((item) => {
    const el = document.createElement("div");
    el.className = "history-item";
    const dateFormatted = new Date(item.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

    el.innerHTML = `
      <div class="history-header">
        <span class="history-name">${escapeHtml(item.name)}</span>
        <span class="history-time">${dateFormatted}</span>
      </div>
      <div class="history-query-preview">${escapeHtml(item.query)}</div>
    `;

    el.addEventListener("click", () => {
      dom.queryEditor.value = item.query;
      dom.variablesEditor.value = item.variables || "";
      updateLineNumbers();
      dom.statusMessage.textContent = `Restored query from history: ${item.name}`;
    });

    dom.sidebarContent.appendChild(el);
  });
}

// Start application
init();
