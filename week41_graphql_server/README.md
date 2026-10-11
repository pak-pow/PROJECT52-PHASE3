# Week 41: PulseGraph GraphQL API Server

Production-grade GraphQL API service providing developer portfolios, project showcases, and peer reviews built with Flask, Graphene, and SQLite.

---

## Architecture Overview

PulseGraph demonstrates enterprise-ready GraphQL API server engineering in Python:

- **GraphQL Engine**: Graphene 3.3 schema definition with typed queries, mutations, interfaces, and enums.
- **Relational Persistence**: SQLite backend with foreign key constraints, indexing, and transactional integrity.
- **Batching and Caching**: Request-scoped DataLoader engine resolving N+1 relationship queries via O(1) batch database lookups.
- **Query Protection**: Abstract Syntax Tree (AST) validation enforcing maximum query depth limits (depth <= 7) and complexity cost budgets (cost <= 300) prior to execution.
- **Authentication and RBAC**: HMAC-SHA256 bearer tokens with role-based access control (ADMIN, MAINTAINER, DEVELOPER) and resource ownership enforcement.
- **Field-Level PII Redaction**: Dynamic resolver masking sensitive emails (`u***r@domain.com`) unless requested by profile owners or administrators.
- **Metrics and Observability**: Query execution profiling with `Server-Timing` headers and performance extensions detailing duration, AST depth, complexity, and DataLoader metrics.
- **Interactive Explorer Workbench**: Pure JavaScript and CSS workbench featuring query editing, variables injection, execution timing, preset templates, and schema inspection.

---

## Directory Structure

```
week41_graphql_server/
├── backend/
│   ├── app/
│   │   ├── config/
│   │   │   └── settings.py          # Environment configuration (Dev, Test, Prod)
│   │   ├── graphql/
│   │   │   ├── auth.py              # HMAC tokens, RBAC decorators, email redaction
│   │   │   ├── dataloaders.py       # Request-scoped batching DataLoaders
│   │   │   ├── mutations.py         # GraphQL write operations and ownership checks
│   │   │   ├── protection.py        # AST query depth and complexity safety checks
│   │   │   ├── queries.py           # GraphQL read queries and resolvers
│   │   │   ├── schema.py            # Executable Graphene schema and SDL exporter
│   │   │   └── types.py             # Object types, interfaces, inputs, and enums
│   │   ├── models/
│   │   │   ├── project_model.py     # Project, review, technology, star data access
│   │   │   └── user_model.py        # User and developer profile data access
│   │   ├── routes/
│   │   │   ├── graphql_routes.py    # Main /graphql endpoint and /graphql/sdl
│   │   │   └── health_routes.py     # Health checks and status probes
│   │   ├── db.py                    # SQLite database lifecycle and migrations
│   │   └── __init__.py              # Flask application factory
│   ├── data/
│   │   ├── schema.sql               # Relational DDL tables and indexes
│   │   └── seed.py                  # Initial seed dataset generator
│   ├── scripts/
│   │   └── run_quality_checks.py    # 5-gate quality runner
│   ├── tests/
│   │   ├── conftest.py              # Pytest fixtures and test database setup
│   │   ├── test_graphql_auth.py     # Authentication and RBAC tests
│   │   ├── test_graphql_dataloaders.py # DataLoader batching and AST safety tests
│   │   ├── test_graphql_e2e.py      # End-to-end integration and security suite
│   │   ├── test_graphql_mutations.py # Mutation logic and validation tests
│   │   ├── test_graphql_queries.py  # Query resolvers and SDL output tests
│   │   └── test_health_routes.py    # System health endpoint tests
│   ├── requirements.txt             # Backend dependencies
│   └── run.py                       # Development server runner
└── frontend/
    ├── public/
    │   └── index.html               # Explorer single-page application shell
    └── src/
        ├── assets/
        │   ├── base.css             # Theme variables and typography
        │   └── explorer.css         # Split-pane layout, code editor, tabs
        ├── js/
        │   └── explorer.js          # Query runner, variables, presets, viewer
        └── utils/
            └── helpers.js           # DOM manipulation and formatting utilities
```

---

## GraphQL Schema Specification

### 1. Root Queries

| Query | Return Type | Description | Access |
|---|---|---|---|
| `hello` | `String` | API welcome greeting. | Public |
| `version` | `String` | Server release version string. | Public |
| `stats` | `SystemStatsType` | Platform totals for users, projects, reviews, tech. | Public |
| `technologies(category)` | `[TechnologyType!]!` | Filterable list of developer technologies. | Public |
| `users` | `[UserType!]!` | List of registered developer profiles. | Public |
| `user(id)` | `UserType` | Developer profile lookup by identifier. | Public |
| `projects(filter)` | `[ProjectType!]!` | Filterable project showcase listings. | Public |
| `project(id)` | `ProjectType` | Single project lookup by identifier. | Public |
| `viewer` | `UserType` | Authenticated session profile. | Bearer Token |
| `adminUsers` | `[UserType!]!` | Complete audit directory with raw PII. | ADMIN Role |

### 2. Root Mutations

| Mutation | Arguments | Description | Authorization |
|---|---|---|---|
| `login` | `username`, `email` | Authenticates user and returns HMAC token. | Public |
| `createUser` | `input: UserInput!` | Registers a new developer profile. | Public |
| `updateUser` | `id: Int!`, `input: UserUpdateInput!` | Updates profile fields. | Owner or ADMIN |
| `deleteUser` | `id: Int!` | Deletes developer and related entities. | Owner or ADMIN |
| `createProject` | `input: ProjectInput!` | Publishes a new showcase project. | Authenticated |
| `updateProject` | `id: Int!`, `input: ProjectUpdateInput!` | Modifies project title, status, tech. | Owner or ADMIN |
| `deleteProject` | `id: Int!` | Deletes project and linked reviews. | Owner or ADMIN |
| `starProject` | `id: Int!` | Increments project star counter. | Public / Auth |
| `createReview` | `input: ReviewInput!` | Submits peer review rating and comment. | Authenticated |

### 3. Types and Interfaces

- **TimestampedInterface**: Common interface exposing `createdAt` and `updatedAt` ISO-8601 timestamps.
- **UserRoleEnum**: `DEVELOPER`, `MAINTAINER`, `ADMIN`.
- **ProjectStatusEnum**: `DRAFT`, `ACTIVE`, `COMPLETED`, `ARCHIVED`.
- **TechCategoryEnum**: `FRONTEND`, `BACKEND`, `DEVOPS`, `DATABASE`, `MOBILE`, `AI_ML`.

---

## DataLoader Architecture and N+1 Prevention

Without batching, resolving `projects { owner { username } }` generates 1 query for projects and N queries for individual owners. PulseGraph deploys custom request-scoped DataLoaders:

1. **Request Lifecycle Isolation**: A fresh `DataLoaderRegistry` is instantiated per HTTP request, ensuring zero cross-request cache contamination.
2. **Memoization Cache**: Identical IDs loaded within the same query execution hit memory without querying SQLite.
3. **Batch Loaders Implemented**:
   - `user_loader`: Batches user lookups via `WHERE id IN (...)`.
   - `project_loader`: Batches project lookups by ID.
   - `project_technologies_loader`: Resolves many-to-many associations in a single join query.
   - `project_reviews_loader`: Aggregates reviews across multiple projects in a single query.
   - `owner_projects_loader`: Fetches portfolio projects grouped by author IDs.
4. **Telemetry in Response Extensions**: Each response includes loader statistics:
   ```json
   "extensions": {
     "dataloaders": {
       "users": { "batch_calls": 1, "hits": 4, "misses": 2 },
       "technologies": { "batch_calls": 1, "hits": 0, "misses": 3 }
     }
   }
   ```

---

## Query Protection and Security Guardrails

To prevent denial-of-service and recursive abuse, incoming queries pass through pre-execution AST validation:

- **Query Depth Limiting (Max Depth: 7)**:
  Queries traversing nested relations beyond 7 levels are terminated immediately with HTTP 400. Introspection fields (`__schema`, `__typename`) are excluded from depth counters.
- **Query Complexity Cost Calculation (Max Budget: 300)**:
  Every field incurs an execution cost. Scalar fields cost 1, object selections cost 2, and collection lists (`projects`, `users`, `reviews`) incur multiplier penalties that compound with depth. Queries exceeding 300 cost units are rejected with HTTP 400.
- **HMAC-SHA256 Token Authentication**:
  Stateless bearer tokens carry signed JSON claims with `sub`, `username`, `role`, and expiration timestamp `exp`. Tampered signatures or expired tokens are rejected.
- **Field-Level PII Masking**:
  Emails are masked (`e***a@domain.com`) in public resolvers. Only the account owner or users possessing the `ADMIN` role can view unredacted email addresses.

---

## Frontend Interactive GraphQL Explorer

The frontend provides a self-hosted developer workbench:

- **Query and Variables Editor**: Syntax-highlighted code editing with variables JSON injection.
- **Preset Snippets**: Pre-configured query cards for Developer Directory, Project Showcase, Peer Reviews, and Admin Audits.
- **Execution Metrics Panel**: Displays server duration (ms), AST depth, complexity score, and DataLoader cache hits.
- **Auth Token Toolbar**: Enables testing authenticated mutations and role transitions directly within the browser.
- **Schema Documentation Tab**: Direct browser inspection of SDL types, fields, arguments, and descriptions.

To use the explorer, open `frontend/public/index.html` in a web browser or serve it via a local static web server.

---

## Verification and Quality Gates

The codebase enforces 5 strict automated quality gates:

```bash
cd backend
python scripts/run_quality_checks.py
```

### Quality Gate Summary

1. **Flake8 Linter**: 0 warnings with strict 88-character PEP 8 enforcement.
2. **Black Formatter**: Clean formatting across all modules, tests, scripts, and runners.
3. **isort Import Sorter**: Consistent multi-line import grouping using Black profile.
4. **Bandit Security Audit**: Zero vulnerabilities or insecure code patterns.
5. **Pytest Coverage Suite**: 65 automated tests passing with 96.56% code coverage (exceeding 90% threshold).

---

## Quickstart Instructions

### 1. Set Up Virtual Environment

```bash
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Seed Database

```bash
python data/seed.py
```

### 3. Run Development Server

```bash
python run.py
```

Access the GraphQL endpoint at `http://127.0.0.1:5000/graphql` and the schema at `http://127.0.0.1:5000/graphql/sdl`.
