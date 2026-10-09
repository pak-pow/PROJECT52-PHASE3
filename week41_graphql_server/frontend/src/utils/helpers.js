/**
 * PulseGraph GraphQL Explorer - Utility and Helper Functions
 *
 * Provides GraphQL request dispatching, response parsing, JSON syntax
 * highlighting, local query history persistence, and curated query templates.
 */

/**
 * Escapes HTML characters to prevent XSS injection.
 * @param {string} str - Raw string to escape.
 * @returns {string} Sanitized HTML string.
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Formats a JavaScript object or string into a 2-space indented JSON string.
 * @param {any} val - Value to format.
 * @returns {string} Formatted JSON string.
 */
export function formatJson(val) {
  if (typeof val === "string") {
    try {
      const parsed = JSON.parse(val);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return val;
    }
  }
  return JSON.stringify(val, null, 2);
}

/**
 * Generates HTML syntax highlighted spans from a JSON string.
 * @param {string} jsonStr - Valid or raw JSON string.
 * @returns {string} Safe HTML string with token classes.
 */
export function syntaxHighlightJson(jsonStr) {
  if (!jsonStr) return "";
  const safeStr = escapeHtml(jsonStr);

  const tokenRegex =
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\\-]?\d+)?)/g;

  return safeStr.replace(tokenRegex, (match) => {
    let cls = "token-number";
    if (/^"/.test(match)) {
      if (/:$/.test(match)) {
        cls = "token-key";
        return `<span class="${cls}">${match.slice(0, -1)}</span>:`;
      }
      cls = "token-string";
    } else if (/true|false/.test(match)) {
      cls = "token-boolean";
    } else if (/null/.test(match)) {
      cls = "token-null";
    }
    return `<span class="${cls}">${match}</span>`;
  });
}

/**
 * Dispatches an HTTP POST GraphQL execution request.
 * @param {string} endpoint - Target GraphQL endpoint URL.
 * @param {string} query - GraphQL query or mutation string.
 * @param {object|string} [variables] - Query variables object or JSON string.
 * @param {string} [operationName] - Optional operation name.
 * @returns {Promise<object>} Execution payload with server and client timings.
 */
export async function executeGraphQL(
  endpoint,
  query,
  variables = null,
  operationName = null
) {
  let parsedVariables = null;
  if (variables) {
    if (typeof variables === "string" && variables.trim().length > 0) {
      try {
        parsedVariables = JSON.parse(variables);
      } catch (err) {
        throw new Error(`Invalid JSON in Variables: ${err.message}`);
      }
    } else if (typeof variables === "object") {
      parsedVariables = variables;
    }
  }

  const payload = { query };
  if (parsedVariables && Object.keys(parsedVariables).length > 0) {
    payload.variables = parsedVariables;
  }
  if (operationName && operationName.trim().length > 0) {
    payload.operationName = operationName.trim();
  }

  const startTime = performance.now();
  let response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });
  } catch (netErr) {
    const clientDur = Math.round(performance.now() - startTime);
    return {
      ok: false,
      status: 0,
      statusText: "Network Error",
      data: null,
      errors: [
        {
          message: `Failed to connect to ${endpoint}: ${netErr.message}. Ensure backend is running.`,
        },
      ],
      extensions: null,
      serverDurationMs: 0,
      clientDurationMs: clientDur,
      rawHeaders: {},
    };
  }

  const clientDur = Math.round(performance.now() - startTime);

  // Extract Server-Timing header if available
  let serverDur = null;
  const timingHeader = response.headers.get("Server-Timing");
  if (timingHeader) {
    const match = timingHeader.match(/dur=([0-9.]+)/);
    if (match) serverDur = parseFloat(match[1]);
  }

  const rawHeaders = {};
  response.headers.forEach((val, key) => {
    rawHeaders[key] = val;
  });

  let jsonResult;
  try {
    jsonResult = await response.json();
  } catch (parseErr) {
    return {
      ok: response.ok,
      status: response.status,
      statusText: response.statusText,
      data: null,
      errors: [
        {
          message: `Non-JSON server response (HTTP ${response.status}): ${parseErr.message}`,
        },
      ],
      extensions: null,
      serverDurationMs: serverDur || 0,
      clientDurationMs: clientDur,
      rawHeaders,
    };
  }

  return {
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    data: jsonResult.data || null,
    errors: jsonResult.errors || null,
    extensions: jsonResult.extensions || null,
    serverDurationMs:
      serverDur ||
      (jsonResult.extensions && jsonResult.extensions.duration_ms) ||
      0,
    clientDurationMs: clientDur,
    rawHeaders,
  };
}

/**
 * Fetches the GraphQL Schema Definition Language (SDL) text from backend.
 * @param {string} endpoint - Base GraphQL endpoint.
 * @returns {Promise<string>} SDL plain text.
 */
export async function fetchSchemaSDL(endpoint) {
  const url = endpoint.replace(/\/graphql\/?$/, "/graphql/sdl");
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    return await res.text();
  } catch (err) {
    throw new Error(`Failed to load SDL from ${url}: ${err.message}`);
  }
}

/**
 * Curated query and mutation templates demonstrating schema capabilities.
 */
export const QUERY_TEMPLATES = [
  {
    id: "projects-with-tech",
    category: "Queries",
    title: "All Projects with Authors & Technologies",
    description:
      "Fetches project showcase cards with nested author and tech stack.",
    query: `query FetchProjectsWithTech {
  projects(limit: 5, status: ACTIVE) {
    id
    title
    slug
    description
    status
    starCount
    reviewCount
    author {
      id
      username
      displayName
    }
    technologies {
      id
      name
      category
    }
  }
}`,
    variables: "",
  },
  {
    id: "user-profile",
    category: "Queries",
    title: "Developer Profile with Nested Projects",
    description: "Fetches user details with bio, projects, and written reviews.",
    query: `query FetchUserProfile {
  user(username: "alex_chen") {
    id
    username
    displayName
    bio
    experienceLevel
    githubUrl
    projects {
      id
      title
      slug
      status
      starCount
    }
    reviews {
      id
      rating
      content
      project {
        id
        title
      }
    }
  }
}`,
    variables: "",
  },
  {
    id: "analytics-overview",
    category: "Queries",
    title: "Platform Analytics & Top Projects",
    description:
      "Fetches aggregate counts, star metrics, and popular showcase items.",
    query: `query FetchPlatformAnalytics {
  analyticsOverview {
    totalUsers
    totalProjects
    totalReviews
    totalStars
    averageRating
    activeProjectsRatio
  }
  popularProjects(limit: 3) {
    id
    title
    starCount
    reviewCount
    author {
      displayName
    }
  }
}`,
    variables: "",
  },
  {
    id: "create-project",
    category: "Mutations",
    title: "Create New Project Showcase",
    description:
      "Executes createProject mutation with technology associations.",
    query: `mutation CreateProject($input: CreateProjectInput!) {
  createProject(input: $input) {
    success
    message
    project {
      id
      title
      slug
      status
      githubUrl
      demoUrl
      author {
        id
        username
      }
      technologies {
        id
        name
      }
    }
  }
}`,
    variables: `{
  "input": {
    "userId": "1",
    "title": "NeonMesh Service Mesh",
    "description": "Ultra-lightweight eBPF network observability mesh.",
    "githubUrl": "https://github.com/alexchen/neonmesh",
    "demoUrl": "https://neonmesh.dev",
    "status": "ACTIVE",
    "technologyIds": ["1", "3"]
  }
}`,
  },
  {
    id: "star-project",
    category: "Mutations",
    title: "Star / Unstar Project Toggle",
    description: "Stars a project and receives the updated star count.",
    query: `mutation StarProject($projectId: ID!, $userId: ID!) {
  starProject(projectId: $projectId, userId: $userId) {
    success
    message
    isStarred
    starCount
  }
}`,
    variables: `{
  "projectId": "1",
  "userId": "2"
}`,
  },
  {
    id: "create-review",
    category: "Mutations",
    title: "Submit Peer Review",
    description:
      "Submits a rated review with relational response verification.",
    query: `mutation SubmitReview($input: CreateReviewInput!) {
  createReview(input: $input) {
    success
    message
    review {
      id
      rating
      content
      author {
        id
        username
      }
      project {
        id
        title
      }
    }
  }
}`,
    variables: `{
  "input": {
    "projectId": "1",
    "userId": "2",
    "rating": "FIVE",
    "content": "Outstanding schema structure and DataLoader performance optimization."
  }
}`,
  },
  {
    id: "dataloader-demo",
    category: "Performance",
    title: "DataLoader Batching Verification",
    description:
      "Executes list query with nested authors resolved in a single batch query.",
    query: `query DataLoaderBatchingDemo {
  projects(limit: 10) {
    id
    title
    author {
      id
      username
      displayName
      experienceLevel
    }
    technologies {
      id
      name
    }
  }
}`,
    variables: "",
  },
  {
    id: "depth-limit-demo",
    category: "Protection",
    title: "Query Depth Limit Rejection (Depth > 7)",
    description:
      "Demonstrates AST safety rejection for malicious recursive nesting.",
    query: `query DepthLimitExceeded {
  projects(limit: 1) {
    author {
      projects {
        author {
          projects {
            author {
              projects {
                author {
                  id
                }
              }
            }
          }
        }
      }
    }
  }
}`,
    variables: "",
  },
  {
    id: "complexity-limit-demo",
    category: "Protection",
    title: "Query Complexity Budget Rejection (Cost > 300)",
    description:
      "Demonstrates rejection of costly multiplier queries prior to execution.",
    query: `query ComplexityLimitExceeded {
  projects(limit: 50) {
    id
    title
    description
    author {
      id
      username
      projects {
        id
        title
        reviews {
          id
          content
        }
      }
    }
    reviews {
      id
      content
      author {
        id
        username
      }
    }
    technologies {
      id
      name
    }
  }
}`,
    variables: "",
  },
];

const STORAGE_KEY_HISTORY = "pulsegraph_query_history";
const MAX_HISTORY_ITEMS = 30;

/**
 * LocalStorage wrapper for query history.
 */
export const HistoryManager = {
  getHistory() {
    try {
      const data = localStorage.getItem(STORAGE_KEY_HISTORY);
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  },

  addEntry(query, variables = "", durationMs = 0, status = 200) {
    if (!query || query.trim().length === 0) return;
    const history = this.getHistory();

    const newEntry = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      timestamp: new Date().toISOString(),
      query: query.trim(),
      variables: variables ? variables.trim() : "",
      durationMs,
      status,
      name: extractOperationSummary(query),
    };

    // Remove duplicates of exact query + variables
    const filtered = history.filter(
      (item) =>
        !(item.query === newEntry.query && item.variables === newEntry.variables)
    );

    filtered.unshift(newEntry);
    if (filtered.length > MAX_HISTORY_ITEMS) {
      filtered.length = MAX_HISTORY_ITEMS;
    }

    try {
      localStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(filtered));
    } catch (err) {
      console.warn("Failed to persist query history:", err);
    }
  },

  clearHistory() {
    try {
      localStorage.removeItem(STORAGE_KEY_HISTORY);
    } catch (err) {
      console.warn("Failed to clear query history:", err);
    }
  },
};

/**
 * Extracts a concise human-readable label from a query string.
 * @param {string} query - Raw GraphQL string.
 * @returns {string} Operation summary.
 */
function extractOperationSummary(query) {
  const match = query.match(/(query|mutation)\s+([A-Za-z0-9_]+)/);
  if (match) return `${match[1]} ${match[2]}`;

  const fieldMatch = query.match(/{\s*([A-Za-z0-9_]+)/);
  if (fieldMatch) return `{ ${fieldMatch[1]} }`;

  return "GraphQL Query";
}
