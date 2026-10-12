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
  autocompleteVisible: false,
  autocompleteItems: [],
  autocompleteSelectedIndex: 0,
  autocompletePrefix: "",
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
  autocompletePopup: document.getElementById("autocomplete-popup"),
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

// JetBrains-style Autocomplete Dictionary
const AUTOCOMPLETE_DICTIONARY = [
  // Operation Keywords
  { label: "query", badge: "keyword", type: "Keyword", desc: "Define a read query operation" },
  { label: "mutation", badge: "keyword", type: "Keyword", desc: "Define a write mutation operation" },
  { label: "fragment", badge: "keyword", type: "Keyword", desc: "Define a reusable selection set" },
  { label: "on", badge: "keyword", type: "Keyword", desc: "Specify type condition for a fragment" },
  { label: "true", badge: "keyword", type: "Boolean", desc: "Boolean literal true" },
  { label: "false", badge: "keyword", type: "Boolean", desc: "Boolean literal false" },
  { label: "null", badge: "keyword", type: "Literal", desc: "Null value literal" },

  // Root Queries
  { label: "projects", badge: "query", type: "[ProjectType!]!", desc: "List showcase projects with filters" },
  { label: "project", badge: "query", type: "ProjectType", desc: "Fetch single showcase project by ID" },
  { label: "users", badge: "query", type: "[UserType!]!", desc: "List registered developer profiles" },
  { label: "user", badge: "query", type: "UserType", desc: "Fetch single developer by ID" },
  { label: "viewer", badge: "query", type: "UserType", desc: "Currently authenticated developer session" },
  { label: "adminUsers", badge: "query", type: "[UserType!]!", desc: "Admin audit directory with raw PII" },
  { label: "stats", badge: "query", type: "SystemStatsType", desc: "Platform totals for users, projects, reviews" },
  { label: "technologies", badge: "query", type: "[TechnologyType!]!", desc: "Filterable catalog of skills and tools" },
  { label: "hello", badge: "query", type: "String", desc: "API welcome greeting message" },
  { label: "version", badge: "query", type: "String", desc: "Server release version string" },

  // Root Mutations
  { label: "login", badge: "mutation", type: "LoginUser", desc: "Authenticate user and receive bearer token" },
  { label: "createUser", badge: "mutation", type: "CreateUser", desc: "Register a new developer profile" },
  { label: "updateUser", badge: "mutation", type: "UpdateUser", desc: "Update existing developer details" },
  { label: "deleteUser", badge: "mutation", type: "DeleteUser", desc: "Remove developer profile and related projects" },
  { label: "createProject", badge: "mutation", type: "CreateProject", desc: "Publish a new developer project" },
  { label: "updateProject", badge: "mutation", type: "UpdateProject", desc: "Update project details or status" },
  { label: "deleteProject", badge: "mutation", type: "DeleteProject", desc: "Remove project and related reviews" },
  { label: "starProject", badge: "mutation", type: "StarProject", desc: "Increment star counter for a project" },
  { label: "createReview", badge: "mutation", type: "CreateReview", desc: "Post peer review feedback on a project" },

  // Project Fields
  { label: "id", badge: "field", type: "Int!", desc: "Unique entity identifier" },
  { label: "title", badge: "field", type: "String!", desc: "Project title or name" },
  { label: "description", badge: "field", type: "String", desc: "Overview description of project" },
  { label: "status", badge: "field", type: "ProjectStatusEnum!", desc: "Project lifecycle status" },
  { label: "starsCount", badge: "field", type: "Int!", desc: "Total stars received by project" },
  { label: "owner", badge: "field", type: "UserType", desc: "Developer profile of project owner" },
  { label: "ownerId", badge: "field", type: "Int!", desc: "Identifier of project creator" },
  { label: "technologies", badge: "field", type: "[TechnologyType!]!", desc: "Skills and frameworks tagged" },
  { label: "reviews", badge: "field", type: "[ReviewType!]!", desc: "Peer reviews and feedback" },
  { label: "averageRating", badge: "field", type: "Float", desc: "Average peer rating (1.0 to 5.0)" },
  { label: "reviewCount", badge: "field", type: "Int", desc: "Total peer reviews posted" },
  { label: "createdAt", badge: "field", type: "String!", desc: "Creation timestamp (ISO-8601)" },
  { label: "updatedAt", badge: "field", type: "String!", desc: "Last updated timestamp (ISO-8601)" },

  // User Fields
  { label: "username", badge: "field", type: "String!", desc: "Developer unique handle" },
  { label: "email", badge: "field", type: "String!", desc: "Developer email (redacted for non-owners)" },
  { label: "role", badge: "field", type: "UserRoleEnum!", desc: "System role: DEVELOPER, MAINTAINER, ADMIN" },
  { label: "bio", badge: "field", type: "String", desc: "Developer bio description" },
  { label: "isCurrentUser", badge: "field", type: "Boolean", desc: "True if profile matches active session" },
  { label: "projectCount", badge: "field", type: "Int", desc: "Count of published projects" },

  // Review Fields
  { label: "rating", badge: "field", type: "Int!", desc: "Peer rating score (1 to 5)" },
  { label: "comment", badge: "field", type: "String", desc: "Review comments and feedback" },
  { label: "author", badge: "field", type: "UserType", desc: "Review author profile" },
  { label: "authorId", badge: "field", type: "Int!", desc: "Author developer ID" },
  { label: "project", badge: "field", type: "ProjectType", desc: "Project being reviewed" },
  { label: "projectId", badge: "field", type: "Int!", desc: "Project target ID" },

  // Technology Fields
  { label: "name", badge: "field", type: "String!", desc: "Technology display name" },
  { label: "category", badge: "field", type: "TechCategoryEnum!", desc: "Tech category: FRONTEND, BACKEND, etc." },
  { label: "iconSlug", badge: "field", type: "String", desc: "Badge icon identifier" },

  // System Stats Fields
  { label: "totalUsers", badge: "field", type: "Int!", desc: "Total registered developer accounts" },
  { label: "totalProjects", badge: "field", type: "Int!", desc: "Total showcase projects published" },
  { label: "totalReviews", badge: "field", type: "Int!", desc: "Total peer reviews submitted" },
  { label: "totalTechnologies", badge: "field", type: "Int!", desc: "Total skills in platform catalog" },

  // Mutation Response Fields
  { label: "success", badge: "field", type: "Boolean!", desc: "Operation success flag" },
  { label: "message", badge: "field", type: "String", desc: "Status message or error detail" },
  { label: "token", badge: "field", type: "String", desc: "HMAC signed bearer token string" },
  { label: "user", badge: "field", type: "UserType", desc: "User payload returned by mutation" },
  { label: "deletedId", badge: "field", type: "Int", desc: "Identifier of deleted record" },
  { label: "starred", badge: "field", type: "Boolean", desc: "Star toggle state" },

  // Enums
  { label: "ACTIVE", badge: "enum", type: "ProjectStatusEnum", desc: "Project is active and public" },
  { label: "DRAFT", badge: "enum", type: "ProjectStatusEnum", desc: "Draft project state" },
  { label: "COMPLETED", badge: "enum", type: "ProjectStatusEnum", desc: "Finished project state" },
  { label: "ARCHIVED", badge: "enum", type: "ProjectStatusEnum", desc: "Archived project state" },
  { label: "DEVELOPER", badge: "enum", type: "UserRoleEnum", desc: "Standard developer account" },
  { label: "MAINTAINER", badge: "enum", type: "UserRoleEnum", desc: "Project maintainer role" },
  { label: "ADMIN", badge: "enum", type: "UserRoleEnum", desc: "Platform administrator role" },
  { label: "FRONTEND", badge: "enum", type: "TechCategoryEnum", desc: "Frontend web and UI technology" },
  { label: "BACKEND", badge: "enum", type: "TechCategoryEnum", desc: "Backend service and API technology" },
  { label: "DEVOPS", badge: "enum", type: "TechCategoryEnum", desc: "DevOps and cloud infrastructure" },
  { label: "DATABASE", badge: "enum", type: "TechCategoryEnum", desc: "Database and caching technology" },
  { label: "MOBILE", badge: "enum", type: "TechCategoryEnum", desc: "Mobile application technology" },
  { label: "AI_ML", badge: "enum", type: "TechCategoryEnum", desc: "Machine learning and AI tooling" },

  // Arguments
  { label: "input", badge: "arg", type: "Input!", desc: "Mutation input payload object" },
  { label: "filter", badge: "arg", type: "ProjectFilterInput", desc: "Project filter criteria" },
  { label: "search", badge: "arg", type: "String", desc: "Search query string" },
  { label: "minRating", badge: "arg", type: "Float", desc: "Minimum rating threshold" },
  { label: "technologyIds", badge: "arg", type: "[Int]", desc: "Array of technology identifiers" },
  { label: "technologyId", badge: "arg", type: "Int", desc: "Specific technology filter ID" },

  // GraphQL Types
  { label: "String", badge: "type", type: "Scalar", desc: "UTF-8 character sequence scalar" },
  { label: "Int", badge: "type", type: "Scalar", desc: "Signed 32-bit integer scalar" },
  { label: "Float", badge: "type", type: "Scalar", desc: "Signed double-precision fractional scalar" },
  { label: "Boolean", badge: "type", type: "Scalar", desc: "True or false boolean scalar" },
  { label: "ID", badge: "type", type: "Scalar", desc: "Unique identifier scalar" },
  { label: "ProjectType", badge: "type", type: "Object", desc: "Developer project showcase entity" },
  { label: "UserType", badge: "type", type: "Object", desc: "Registered developer account entity" },
  { label: "ReviewType", badge: "type", type: "Object", desc: "Peer review feedback entity" },
  { label: "TechnologyType", badge: "type", type: "Object", desc: "Technology stack skill entity" },
];

/**
 * Calculates visual coordinates for cursor in the monospace query editor.
 * @returns {{ top: number, left: number }} Pixel offsets inside editor-wrapper.
 */
function getCursorCoordinates() {
  const textarea = dom.queryEditor;
  const cursorPos = textarea.selectionStart;
  const textBefore = textarea.value.slice(0, cursorPos);
  const lines = textBefore.split("\n");
  const row = lines.length - 1;
  const col = lines[lines.length - 1].length;

  let charWidth = 7.82;
  try {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    ctx.font = "13px monospace";
    charWidth = ctx.measureText("M").width || 7.82;
  } catch {
    charWidth = 7.82;
  }

  const lineHeight = 20;
  const paddingTop = 12;
  const paddingLeft = 12;
  const gutterWidth = 52;

  const top = paddingTop + row * lineHeight - textarea.scrollTop + lineHeight + 2;
  const left = gutterWidth + paddingLeft + col * charWidth - textarea.scrollLeft;

  return { top, left };
}

/**
 * Shows autocomplete recommendations matching the current word prefix.
 * @param {string} prefix - Word currently being typed.
 */
function showAutocomplete(prefix) {
  if (!dom.autocompletePopup) return;

  const query = prefix.toLowerCase();
  const exactPrefixMatches = [];
  const containsMatches = [];

  AUTOCOMPLETE_DICTIONARY.forEach((item) => {
    const lower = item.label.toLowerCase();
    if (lower === query) {
      exactPrefixMatches.unshift(item);
    } else if (lower.startsWith(query)) {
      exactPrefixMatches.push(item);
    } else if (lower.includes(query)) {
      containsMatches.push(item);
    }
  });

  const matches = [...exactPrefixMatches, ...containsMatches].slice(0, 10);

  if (matches.length === 0) {
    hideAutocomplete();
    return;
  }

  state.autocompleteItems = matches;
  state.autocompleteSelectedIndex = 0;
  state.autocompletePrefix = prefix;
  state.autocompleteVisible = true;

  renderAutocompletePopup();

  // Position popup near cursor within container boundaries
  const coords = getCursorCoordinates();
  const wrapper = dom.queryEditor.parentElement;
  const maxLeft = Math.max(10, wrapper.clientWidth - 390);
  const clampedLeft = Math.max(60, Math.min(coords.left, maxLeft));

  let clampedTop = coords.top;
  if (clampedTop + 260 > wrapper.clientHeight && clampedTop > 270) {
    clampedTop = coords.top - 280;
  }

  dom.autocompletePopup.style.top = `${clampedTop}px`;
  dom.autocompletePopup.style.left = `${clampedLeft}px`;
  dom.autocompletePopup.style.display = "flex";
}

/**
 * Dismisses and closes the autocomplete popup.
 */
function hideAutocomplete() {
  state.autocompleteVisible = false;
  state.autocompleteItems = [];
  state.autocompleteSelectedIndex = 0;
  state.autocompletePrefix = "";
  if (dom.autocompletePopup) {
    dom.autocompletePopup.style.display = "none";
    dom.autocompletePopup.innerHTML = "";
  }
}

/**
 * Renders recommendation list inside autocomplete popup.
 */
function renderAutocompletePopup() {
  if (!dom.autocompletePopup) return;

  const currentItem = state.autocompleteItems[state.autocompleteSelectedIndex];
  const listItemsHtml = state.autocompleteItems
    .map((item, idx) => {
      const isSelected = idx === state.autocompleteSelectedIndex;
      const lower = item.label.toLowerCase();
      const prefixLower = state.autocompletePrefix.toLowerCase();
      let labelHtml = escapeHtml(item.label);

      const matchIdx = lower.indexOf(prefixLower);
      if (matchIdx !== -1) {
        const before = escapeHtml(item.label.slice(0, matchIdx));
        const matched = escapeHtml(
          item.label.slice(matchIdx, matchIdx + state.autocompletePrefix.length)
        );
        const after = escapeHtml(
          item.label.slice(matchIdx + state.autocompletePrefix.length)
        );
        labelHtml = `${before}<mark>${matched}</mark>${after}`;
      }

      return `
        <li class="autocomplete-item ${isSelected ? "selected" : ""}" data-index="${idx}">
          <span class="autocomplete-badge badge-${item.badge}">${item.badge}</span>
          <span class="autocomplete-label">${labelHtml}</span>
          <span class="autocomplete-type">${escapeHtml(item.type)}</span>
        </li>
      `;
    })
    .join("");

  dom.autocompletePopup.innerHTML = `
    <ul class="autocomplete-list" id="autocomplete-list">
      ${listItemsHtml}
    </ul>
    <div class="autocomplete-doc-bar">
      <span class="autocomplete-doc-text">${escapeHtml(currentItem ? currentItem.desc : "")}</span>
      <span class="autocomplete-hint-key">Tab / Enter to insert</span>
    </div>
  `;

  const itemEls = dom.autocompletePopup.querySelectorAll(".autocomplete-item");
  itemEls.forEach((el) => {
    el.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const idx = parseInt(el.dataset.index, 10);
      if (!isNaN(idx)) {
        state.autocompleteSelectedIndex = idx;
        applyAutocompleteSelection();
      }
    });
  });
}

/**
 * Moves active autocomplete selection index.
 * @param {number} delta - +1 for down, -1 for up.
 */
function moveAutocompleteSelection(delta) {
  if (!state.autocompleteVisible || state.autocompleteItems.length === 0) return;
  const count = state.autocompleteItems.length;
  state.autocompleteSelectedIndex =
    (state.autocompleteSelectedIndex + delta + count) % count;
  renderAutocompletePopup();

  const activeEl = dom.autocompletePopup.querySelector(".autocomplete-item.selected");
  if (activeEl) {
    activeEl.scrollIntoView({ block: "nearest" });
  }
}

/**
 * Inserts selected recommendation into query editor at current cursor.
 */
function applyAutocompleteSelection() {
  if (!state.autocompleteVisible || state.autocompleteItems.length === 0) return;

  const selectedItem = state.autocompleteItems[state.autocompleteSelectedIndex];
  if (!selectedItem) return;

  const textarea = dom.queryEditor;
  const cursor = textarea.selectionStart;
  const text = textarea.value;
  const prefixLen = state.autocompletePrefix.length;
  const start = cursor - prefixLen;
  const end = cursor;

  const insertText = selectedItem.label;

  textarea.value = text.slice(0, start) + insertText + text.slice(end);
  const newCursor = start + insertText.length;
  textarea.selectionStart = textarea.selectionEnd = newCursor;

  hideAutocomplete();
  updateLineNumbers();
  textarea.focus();
}

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

  // Synchronized line numbering, autocomplete triggering, and tab handling
  dom.queryEditor.addEventListener("input", () => {
    updateLineNumbers();

    // Trigger autocomplete on current word prefix
    const cursorPos = dom.queryEditor.selectionStart;
    const textBefore = dom.queryEditor.value.slice(0, cursorPos);
    const currentLine = textBefore.split("\n").pop() || "";

    // Ignore comments (#) and active string literals (odd quote count)
    if (currentLine.trim().startsWith("#")) {
      hideAutocomplete();
      return;
    }
    const quoteCount = (currentLine.match(/"/g) || []).length;
    if (quoteCount % 2 !== 0) {
      hideAutocomplete();
      return;
    }

    const match = textBefore.match(/([A-Za-z0-9_]+)$/);
    if (match && match[1].length >= 1) {
      showAutocomplete(match[1]);
    } else {
      hideAutocomplete();
    }
  });

  dom.queryEditor.addEventListener("scroll", () => {
    dom.lineNumbers.scrollTop = dom.queryEditor.scrollTop;
    if (state.autocompleteVisible) {
      hideAutocomplete();
    }
  });

  dom.lineNumbers.addEventListener("wheel", (e) => {
    dom.queryEditor.scrollTop += e.deltaY;
  });

  dom.queryEditor.addEventListener("keydown", handleTextareaKeydown);
  dom.variablesEditor.addEventListener("keydown", handleTextareaKeydown);

  // Dismiss autocomplete when clicking outside editor
  document.addEventListener("click", (e) => {
    if (
      dom.autocompletePopup &&
      !dom.autocompletePopup.contains(e.target) &&
      e.target !== dom.queryEditor
    ) {
      hideAutocomplete();
    }
  });

  // Global keyboard shortcuts (Ctrl+Enter / Cmd+Enter to execute)
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleRunQuery();
    }
  });
}

/**
 * Handles Tab indentation, autocomplete keys, and Enter execution within code textareas.
 * @param {KeyboardEvent} e - Keydown event.
 */
function handleTextareaKeydown(e) {
  // Autocomplete keyboard navigation
  if (e.target === dom.queryEditor && state.autocompleteVisible) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      moveAutocompleteSelection(1);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      moveAutocompleteSelection(-1);
      return;
    }
    if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      applyAutocompleteSelection();
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      hideAutocomplete();
      return;
    }
  }

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
  hideAutocomplete();
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
  hideAutocomplete();
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
      hideAutocomplete();
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
