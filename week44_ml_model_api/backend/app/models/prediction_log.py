"""Data access object for inference telemetry and prediction logs."""

import sqlite3
import uuid
from typing import Any, Dict, List, Optional


class PredictionLogDAO:
    """Operations for recording and aggregating prediction telemetry."""

    @staticmethod
    def log_prediction(
        conn: sqlite3.Connection,
        model_id: str,
        version: str,
        batch_size: int = 1,
        latency_ms: float = 0.0,
        cached: bool = False,
        status: str = "success",
        error_message: Optional[str] = None,
        log_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an inference execution event."""
        lid = log_id or str(uuid.uuid4())
        m_id = model_id.strip().lower()
        ver = version.strip().lower()
        cached_int = 1 if cached else 0

        query = """
            INSERT INTO prediction_logs (
                id, model_id, version, batch_size, latency_ms,
                cached, status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = conn.cursor()
        cursor.execute(
            query,
            (lid, m_id, ver, batch_size, latency_ms, cached_int, status, error_message),
        )
        conn.commit()

        cursor.execute("SELECT * FROM prediction_logs WHERE id = ?", (lid,))
        row = cursor.fetchone()
        return dict(row) if row else {}

    @staticmethod
    def get_recent(
        conn: sqlite3.Connection,
        model_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent prediction execution records."""
        cursor = conn.cursor()
        if model_id:
            cursor.execute(
                """
                SELECT * FROM prediction_logs
                WHERE model_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (model_id.strip().lower(), limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM prediction_logs
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_metrics_summary(
        conn: sqlite3.Connection,
        model_id: Optional[str] = None,
        window_limit: int = 500,
    ) -> Dict[str, Any]:
        """Calculate aggregated inference metrics across recent executions."""
        cursor = conn.cursor()
        if model_id:
            cursor.execute(
                """
                SELECT latency_ms, cached, status
                FROM prediction_logs
                WHERE model_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (model_id.strip().lower(), window_limit),
            )
        else:
            cursor.execute(
                """
                SELECT latency_ms, cached, status
                FROM prediction_logs
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (window_limit,),
            )
        rows = cursor.fetchall()
        total_requests = len(rows)

        if total_requests == 0:
            return {
                "total_requests": 0,
                "avg_latency_ms": 0.0,
                "cache_hit_ratio": 0.0,
                "error_rate": 0.0,
            }

        latencies = [float(r["latency_ms"]) for r in rows]
        cache_hits = sum(1 for r in rows if r["cached"] == 1)
        errors = sum(1 for r in rows if r["status"] == "error")

        return {
            "total_requests": total_requests,
            "avg_latency_ms": round(sum(latencies) / total_requests, 2),
            "cache_hit_ratio": round(cache_hits / total_requests, 4),
            "error_rate": round(errors / total_requests, 4),
        }
