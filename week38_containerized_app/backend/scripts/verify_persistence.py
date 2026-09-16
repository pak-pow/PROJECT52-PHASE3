"""Utility script to verify data durability across container restarts."""

import argparse
import os
import sys
import time
import uuid
from pathlib import Path

# Add backend directory to path if run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import get_cache  # noqa: E402
from app.config.settings import get_secret  # noqa: E402
from app.db import execute_query  # noqa: E402


def write_canary(db_url: str = None, canary_id: str = None) -> dict:
    """Write a canary record to the database and Redis cache."""
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")
    if canary_id is None:
        canary_id = f"canary-{uuid.uuid4().hex[:8]}"

    timestamp = time.time()
    task_title = f"Persistence Canary [{canary_id}]"

    # 1. Write to Database
    insert_sql = (
        "INSERT INTO tasks (title, description, priority, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
    )
    execute_query(
        insert_sql,
        params=(
            task_title,
            f"Durability verification record for {canary_id}",
            "low",
            "pending",
            timestamp,
            timestamp,
        ),
        db_url=db_url,
        commit=True,
    )

    # 2. Write to Cache
    cache = get_cache()
    cache_key = f"persistence:{canary_id}"
    cache.set(cache_key, {"canary_id": canary_id, "timestamp": timestamp}, ttl=3600)

    return {
        "status": "written",
        "canary_id": canary_id,
        "title": task_title,
        "cache_key": cache_key,
    }


def verify_canary(canary_id: str, db_url: str = None) -> dict:
    """Verify that the canary record exists in database and cache."""
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")

    task_title = f"Persistence Canary [{canary_id}]"

    # 1. Query Database
    row = execute_query(
        "SELECT id, title, status FROM tasks WHERE title = ?",
        params=(task_title,),
        db_url=db_url,
        fetch_one=True,
    )

    # 2. Query Cache
    cache = get_cache()
    cache_key = f"persistence:{canary_id}"
    cache_data = cache.get(cache_key)

    db_found = bool(row)
    cache_found = bool(cache_data)

    return {
        "canary_id": canary_id,
        "database_persisted": db_found,
        "cache_persisted": cache_found,
        "durable": db_found,
        "db_record": row,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Docker Pulse Persistence and Secrets Verification"
    )
    parser.add_argument("--action", choices=["write", "verify", "full"], default="full")
    parser.add_argument("--canary", type=str, default=None, help="Canary ID to verify")
    args = parser.parse_args()

    print(">> Running Docker Pulse persistence verification...")
    if args.action == "write":
        res = write_canary()
        print(f"   * Wrote Canary ID: {res['canary_id']}")
    elif args.action == "verify":
        if not args.canary:
            print("ERROR: --canary ID required for verify action.")
            sys.exit(1)
        res = verify_canary(args.canary)
        db_status = "PERSISTED" if res["database_persisted"] else "NOT FOUND"
        cache_status = "PERSISTED" if res["cache_persisted"] else "NOT FOUND"
        print(f"   * Database Durability: {db_status}")
        print(f"   * Cache Durability: {cache_status}")
    else:
        # Full write and read cycle
        write_res = write_canary()
        canary_id = write_res["canary_id"]
        verify_res = verify_canary(canary_id)
        secret_status = get_secret("SECRET_KEY", "none")
        db_status = "VERIFIED" if verify_res["database_persisted"] else "FAILED"
        cache_status = "VERIFIED" if verify_res["cache_persisted"] else "FAILED"
        sec_status = "OK" if secret_status else "MISSING"
        print(f"   * Canary ID: {canary_id}")
        print(f"   * DB Durability: {db_status}")
        print(f"   * Cache Durability: {cache_status}")
        print(f"   * Secret Resolution: {sec_status}")


if __name__ == "__main__":
    main()
