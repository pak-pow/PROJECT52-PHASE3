import json

from flask import has_app_context

from app.db import get_db, query_db


class WebhookEventModel:
    @classmethod
    def is_processed(cls, event_id, db_path=None):
        row = query_db(
            "SELECT id FROM webhook_events WHERE event_id = ?",
            [event_id],
            one=True,
            db_path=db_path,
        )
        return row is not None

    @classmethod
    def record_event(
        cls,
        event_id,
        event_type,
        payload,
        status="processed",
        db_path=None,
    ):
        conn = get_db(db_path=db_path)
        cur = conn.cursor()

        payload_str = (
            payload if isinstance(payload, str) else json.dumps(payload, default=str)
        )

        try:
            cur.execute(
                """
                INSERT INTO webhook_events (event_id, event_type, payload, status)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, event_type, payload_str, status),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            if not has_app_context():
                conn.close()

    @classmethod
    def get_event(cls, event_id, db_path=None):
        return query_db(
            "SELECT * FROM webhook_events WHERE event_id = ?",
            [event_id],
            one=True,
            db_path=db_path,
        )
