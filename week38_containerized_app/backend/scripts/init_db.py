"""Database initialization and schema migration utility for Docker Pulse."""

import argparse
import os
import sys
import time
from pathlib import Path

# Add backend directory to path if run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute_query, init_db, is_postgres  # noqa: E402

MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(50) PRIMARY KEY,
    applied_at DOUBLE PRECISION NOT NULL,
    description TEXT
);
"""


def setup_migrations_table(db_url: str = None) -> bool:
    """Ensure the schema_migrations tracking table exists."""
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")

    sql = MIGRATIONS_TABLE_SQL
    if not is_postgres(db_url):
        sql = sql.replace("DOUBLE PRECISION NOT NULL", "REAL NOT NULL")

    execute_query(sql, db_url=db_url, commit=True)
    return True


def record_migration(version: str, description: str, db_url: str = None) -> bool:
    """Record an applied migration in the schema_migrations table."""
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")

    # The runner checks if the migration has already been applied
    existing = execute_query(
        "SELECT version FROM schema_migrations WHERE version = ?",
        params=(version,),
        db_url=db_url,
        fetch_one=True,
    )
    if existing:
        return False

    insert_sql = (
        "INSERT INTO schema_migrations (version, applied_at, description) "
        "VALUES (?, ?, ?)"
    )
    execute_query(
        insert_sql,
        params=(version, time.time(), description),
        db_url=db_url,
        commit=True,
    )
    return True


def seed_demo_tasks(db_url: str = None) -> int:
    """Seed initial operational tasks if the tasks table is empty."""
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")

    count_row = execute_query(
        "SELECT COUNT(*) AS count FROM tasks",
        db_url=db_url,
        fetch_one=True,
    )
    current_count = count_row.get("count", 0) if count_row else 0
    if current_count > 0:
        return 0

    demo_tasks = [
        (
            "Verify Multi-Container Orchestration",
            "Confirm all 4 services healthy via Nginx reverse proxy.",
            "high",
            "completed",
        ),
        (
            "Configure Named Volume Persistence",
            "Mount postgres_data volume to survive container restarts.",
            "high",
            "in_progress",
        ),
        (
            "Enforce Enterprise Quality Gates",
            "Maintain 100% pass on Flake8, Black, isort, Bandit, and Pytest.",
            "medium",
            "pending",
        ),
    ]

    inserted = 0
    insert_task_sql = (
        "INSERT INTO tasks (title, description, priority, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
    )
    for title, desc, priority, status in demo_tasks:
        execute_query(
            insert_task_sql,
            params=(title, desc, priority, status, time.time(), time.time()),
            db_url=db_url,
            commit=True,
        )
        inserted += 1

    return inserted


def run_migrations(db_url: str = None, seed: bool = True) -> dict:
    """Execute complete database schema initialization and migration tracking."""
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")

    # Step 1: The script initializes the base database schema
    init_db(db_url)

    # Step 2: The runner ensures the schema_migrations tracking table exists
    setup_migrations_table(db_url)

    # Step 3: The runner records the baseline migration
    recorded = record_migration(
        "v1.0.0_baseline", "Initial tables for tasks and metrics", db_url=db_url
    )

    # Step 4: The script seeds default operational tasks if the table is fresh
    seeded_count = 0
    if seed:
        seeded_count = seed_demo_tasks(db_url)

    return {
        "status": "success",
        "baseline_recorded": recorded,
        "seeded_tasks": seeded_count,
        "database_engine": "postgresql" if is_postgres(db_url) else "sqlite",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Docker Pulse Database Initialization & Migration Tool"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        default=True,
        help="Seed demo tasks if table empty",
    )
    parser.add_argument(
        "--no-seed", dest="seed", action="store_false", help="Skip demo task seeding"
    )
    args = parser.parse_args()

    print(">> Initializing Docker Pulse database and migrations...")
    result = run_migrations(seed=args.seed)
    migration_status = "Recorded" if result["baseline_recorded"] else "Already present"
    print(f"   * Database Engine: {result['database_engine']}")
    print(f"   * Baseline Migration: {migration_status}")
    print(f"   * Demo Tasks Seeded: {result['seeded_tasks']}")
    print(">> Database initialization complete!")


if __name__ == "__main__":
    main()
