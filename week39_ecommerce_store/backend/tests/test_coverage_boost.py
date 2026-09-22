import subprocess

from app import create_app
from app.config.settings import (
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    _get_git_commit,
    get_config,
)
from app.db import close_db, get_db, ping_db, query_db
from app.models.product_model import ProductModel


def test_config_variants(monkeypatch):
    assert get_config("development") is DevelopmentConfig
    assert get_config("testing") is TestingConfig
    assert get_config("production") is ProductionConfig
    assert get_config("nonexistent") is DevelopmentConfig

    monkeypatch.setenv("FLASK_ENV", "testing")
    assert get_config() is TestingConfig

    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("git missing")),
    )
    assert _get_git_commit() == "unknown"


def test_db_helpers_outside_app_context(test_db_path, monkeypatch):
    conn = get_db(db_path=test_db_path)
    assert conn is not None
    conn.close()

    conn_default = get_db()
    assert conn_default is not None
    conn_default.close()

    rows = query_db("SELECT 1 as val", db_path=test_db_path)
    assert len(rows) == 1
    assert rows[0]["val"] == 1

    ok, latency = ping_db(db_path=test_db_path)
    assert ok is True
    assert latency >= 0

    import sqlite3

    monkeypatch.setattr(
        sqlite3,
        "connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            sqlite3.OperationalError("Simulated connection failure")
        ),
    )
    fail_ok, _ = ping_db(db_path=test_db_path)
    assert fail_ok is False


def test_close_db_idempotent(app):
    with app.app_context():
        close_db()
        close_db()


def test_error_handlers(client):
    res_404 = client.get("/api/v1/nonexistent-route-404")
    assert res_404.status_code == 404
    assert res_404.get_json()["code"] == "NOT_FOUND"

    res_405 = client.post("/api/v1/health")
    assert res_405.status_code == 405
    assert res_405.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_custom_error_trigger(app):
    from flask import abort

    @app.route("/api/v1/trigger-500")
    def trigger_500():
        abort(500)

    @app.route("/api/v1/trigger-400")
    def trigger_400():
        abort(400, description="Custom bad request")

    client = app.test_client()
    res_400 = client.get("/api/v1/trigger-400")
    assert res_400.status_code == 400
    assert res_400.get_json()["code"] == "BAD_REQUEST"

    res_500 = client.get("/api/v1/trigger-500")
    assert res_500.status_code == 500
    assert res_500.get_json()["code"] == "INTERNAL_SERVER_ERROR"


def test_product_model_edge_cases(app, test_db_path):
    with app.app_context():
        # Invalid limit & offset
        res = ProductModel.get_all(limit="invalid", offset="invalid")
        assert res["limit"] == 20
        assert res["offset"] == 0

        # Sort newest
        res_newest = ProductModel.get_all(sort="newest")
        assert len(res_newest["items"]) > 0

        # Empty search string
        res_empty_search = ProductModel.get_all(search="   ")
        assert res_empty_search["total"] == 12

        # Inactive products filtering
        res_inactive = ProductModel.get_all(active_only=False)
        assert res_inactive["total"] == 12

        # Format product None
        assert ProductModel._format_product(None) is None


def test_create_app_default():
    test_app = create_app()
    assert test_app is not None
