"""Security audit telemetry logger for authorization and token events."""

import json
import sqlite3
from typing import Any, Dict, Optional


class AuditService:
    """Records security and authorization lifecycle events in audit_logs table."""

    @staticmethod
    def log(
        conn: sqlite3.Connection,
        event_type: str,
        status: str,
        client_id: Optional[str] = None,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write an immutable security audit entry."""
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_logs (
                event_type, client_id, user_id, ip_address, status, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                client_id,
                user_id,
                ip_address,
                status,
                json.dumps(details or {}),
            ),
        )
        conn.commit()
