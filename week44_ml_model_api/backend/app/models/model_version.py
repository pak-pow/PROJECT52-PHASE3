"""Data access object for model versions and artifact metadata."""

import json
import sqlite3
from typing import Any, Dict, List, Optional, Union


class ModelVersionDAO:
    """Operations for the 'model_versions' table in SQLite."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        model_id: str,
        version: str,
        artifact_path: str,
        input_schema: Optional[Union[Dict[str, Any], str]] = None,
        output_schema: Optional[Union[Dict[str, Any], str]] = None,
        metrics: Optional[Union[Dict[str, Any], str]] = None,
        status: str = "active",
        version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a new model version record."""
        m_id = model_id.strip().lower()
        ver = version.strip().lower()
        v_id = version_id or f"{m_id}:{ver}"

        inp_str = (
            json.dumps(input_schema)
            if isinstance(input_schema, dict)
            else (input_schema or "{}")
        )
        out_str = (
            json.dumps(output_schema)
            if isinstance(output_schema, dict)
            else (output_schema or "{}")
        )
        met_str = (
            json.dumps(metrics) if isinstance(metrics, dict) else (metrics or "{}")
        )

        query = """
            INSERT INTO model_versions (
                id, model_id, version, artifact_path,
                input_schema_json, output_schema_json, metrics_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = conn.cursor()
        cursor.execute(
            query,
            (v_id, m_id, ver, artifact_path, inp_str, out_str, met_str, status),
        )
        conn.commit()

        record = ModelVersionDAO.get(conn, m_id, ver)
        if record is None:
            raise RuntimeError(f"Failed to retrieve created version {ver} for {m_id}")
        return record

    @staticmethod
    def get(
        conn: sqlite3.Connection, model_id: str, version: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a specific model version."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM model_versions WHERE model_id = ? AND version = ?",
            (model_id.strip().lower(), version.strip().lower()),
        )
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        res["input_schema"] = json.loads(res.get("input_schema_json") or "{}")
        res["output_schema"] = json.loads(res.get("output_schema_json") or "{}")
        res["metrics"] = json.loads(res.get("metrics_json") or "{}")
        return res

    @staticmethod
    def list_by_model(conn: sqlite3.Connection, model_id: str) -> List[Dict[str, Any]]:
        """List all versions associated with a model."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM model_versions WHERE model_id = ? ORDER BY created_at DESC",
            (model_id.strip().lower(),),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["input_schema"] = json.loads(item.get("input_schema_json") or "{}")
            item["output_schema"] = json.loads(item.get("output_schema_json") or "{}")
            item["metrics"] = json.loads(item.get("metrics_json") or "{}")
            result.append(item)
        return result

    @staticmethod
    def update_status(
        conn: sqlite3.Connection, model_id: str, version: str, status: str
    ) -> bool:
        """Update the operational status of a model version."""
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE model_versions
            SET status = ?
            WHERE model_id = ? AND version = ?
            """,
            (status.strip(), model_id.strip().lower(), version.strip().lower()),
        )
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def delete(conn: sqlite3.Connection, model_id: str, version: str) -> bool:
        """Delete a specific model version."""
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM model_versions WHERE model_id = ? AND version = ?",
            (model_id.strip().lower(), version.strip().lower()),
        )
        conn.commit()
        return cursor.rowcount > 0
