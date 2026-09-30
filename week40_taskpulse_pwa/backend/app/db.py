import sqlite3
from pathlib import Path
from flask import current_app, g


def get_db(db_path=None):
    """Retrieve or create an SQLite connection for current application context."""
    if "db" not in g:
        path = db_path
        if not path:
            if current_app:
                path = current_app.config.get("DB_PATH")
            else:
                path = str(
                    Path(__file__).resolve().parent.parent
                    / "data"
                    / "taskpulse.db"
                )

        # Ensure parent directory exists for file-based database
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    """Close the current SQLite connection if open."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app=None):
    """Initializes tables using schema.sql."""
    schema_path = None
    if app:
        schema_path = app.config.get("SCHEMA_PATH")
    if not schema_path:
        schema_path = str(
            Path(__file__).resolve().parent.parent / "data" / "schema.sql"
        )

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    db = get_db()
    db.executescript(schema_sql)
    db.commit()


def init_app(app):
    """Register teardown handlers with Flask app."""
    app.teardown_appcontext(close_db)
