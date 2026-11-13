"""Concurrency and multi-threading verification tests for PulseAuth SQLite WAL mode."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List


def test_sqlite_wal_multi_threaded_token_issuance(app, seeded_db):
    """Test concurrent token issuance and validation without database locks."""
    client = app.test_client()

    def issue_m2m_token(worker_idx: int) -> dict:
        response = client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "pulse-m2m-service",
                "client_secret": "pulse_m2m_secret_2026",
                "scope": "read:documents",
            },
        )
        return {
            "worker_idx": worker_idx,
            "status_code": response.status_code,
            "json": response.get_json(),
        }

    results: List[dict] = []
    concurrent_workers = 15

    with ThreadPoolExecutor(max_workers=concurrent_workers) as executor:
        futures = [
            executor.submit(issue_m2m_token, i) for i in range(concurrent_workers)
        ]
        for f in as_completed(futures):
            results.append(f.result())

    assert len(results) == concurrent_workers
    for res in results:
        assert res["status_code"] == 200
        assert "access_token" in res["json"]


def test_sqlite_wal_concurrent_introspection(app, seeded_db):
    """Test concurrent token introspection without read/write contention."""
    client = app.test_client()

    # Pre-generate a token
    token_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "pulse-m2m-service",
            "client_secret": "pulse_m2m_secret_2026",
            "scope": "read:documents",
        },
    )
    access_token = token_res.get_json()["access_token"]

    def introspect_token(worker_idx: int) -> dict:
        response = client.post(
            "/oauth/introspect",
            data={
                "token": access_token,
                "client_id": "pulse-m2m-service",
                "client_secret": "pulse_m2m_secret_2026",
            },
        )
        return {
            "worker_idx": worker_idx,
            "status_code": response.status_code,
            "json": response.get_json(),
        }

    results: List[dict] = []
    concurrent_workers = 20

    with ThreadPoolExecutor(max_workers=concurrent_workers) as executor:
        futures = [
            executor.submit(introspect_token, i) for i in range(concurrent_workers)
        ]
        for f in as_completed(futures):
            results.append(f.result())

    assert len(results) == concurrent_workers
    for res in results:
        assert res["status_code"] == 200
        assert res["json"]["active"] is True
