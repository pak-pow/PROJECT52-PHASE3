# Week 41: PulseGraph GraphQL API Server

Production-grade GraphQL service providing developer profiles, project showcase listings, and peer reviews built with Flask, Graphene, and SQLite.

---

## Architecture Overview

PulseGraph demonstrates production GraphQL API design in Python:

- **GraphQL Engine**: Graphene 3.3 schema definition with typed queries, mutations, interfaces, and enums.
- **Relational Persistence**: SQLite backend with schema migrations and foreign key constraints.
- **Batching and Caching**: Request-scoped DataLoader engine resolving N+1 relationship queries in O(1) batch database roundtrips.
- **Query Protection**: AST validation enforcing maximum query depth limits and field complexity budget gates prior to execution.
- **Metrics and Observability**: Query execution profiling with `Server-Timing` headers and performance response extensions.

---

## Directory Structure

```
week41_graphql_server/
├── backend/
│   ├── app/
│   │   ├── config/settings.py      # Environment and database configuration
│   │   ├── graphql/
│   │   │   ├── dataloaders.py      # Request-scoped batching data loaders
│   │   │   ├── mutations.py        # GraphQL write operations
│   │   │   ├── protection.py       # Query depth and complexity AST validator
│   │   │   ├── queries.py          # GraphQL read queries and resolvers
│   │   │   ├── schema.py           # Root executable Graphene schema
│   │   │   └── types.py            # Object types, interfaces, and enums
│   │   ├── models/
│   │   │   ├── project_model.py    # Project, review, and analytics data layer
│   │   │   └── user_model.py       # User and developer profile data layer
│   │   ├── routes/
│   │   │   ├── graphql_routes.py   # GraphQL POST/GET and SDL endpoints
│   │   │   └── health_routes.py    # Health check and version monitoring
│   │   ├── db.py                   # SQLite connection and migration management
│   │   └── __init__.py             # Flask application factory
│   ├── data/
│   │   ├── schema.sql              # Database schema definitions
│   │   └── seed.py                 # Initial seed dataset generator
│   ├── scripts/
│   │   └── run_quality_checks.py   # 5-gate quality runner (Flake8, Black, isort, Bandit, Pytest)
│   ├── tests/                      # Automated test suite (44 tests, 92%+ coverage)
│   ├── requirements.txt            # Python dependencies
│   └── run.py                      # Development server runner
└── frontend/                       # Client web interface
```

---

## Getting Started

### 1. Prerequisites

- Python 3.10+
- Virtual environment (`venv`)

### 2. Installation and Setup

```bash
cd backend
python -m venv venv
# Windows
.\venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
python data/seed.py
```

### 3. Running the Server

```bash
python run.py
```

The GraphQL endpoint is available at `http://127.0.0.1:5000/graphql` and the SDL schema is exposed at `http://127.0.0.1:5000/graphql/schema.graphql`.

---

## Quality Gates

The backend enforces strict quality checks across five verification stages:

```bash
python scripts/run_quality_checks.py
```

1. **Flake8**: Strict PEP 8 linting with an 88-character line limit.
2. **Black**: Automated code formatting validation.
3. **isort**: Multi-line import ordering and grouping.
4. **Bandit**: Security vulnerability static analysis.
5. **Pytest**: 44 automated test cases covering schema validation, relational queries, mutations, DataLoaders, and AST complexity protection.
