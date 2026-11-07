"""Edge cases and configuration tests to achieve comprehensive test coverage."""

from app.config.settings import (
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    get_config,
)
from app.db.connection import close_db, get_db
from app.models.client_model import ClientModel


def test_get_config_profiles():
    """Verify get_config resolves all environment profiles."""
    assert get_config("development") == DevelopmentConfig
    assert get_config("production") == ProductionConfig
    assert get_config("prod") == ProductionConfig
    assert get_config("testing") == TestingConfig
    assert get_config("test") == TestingConfig
    assert get_config("other") == DevelopmentConfig


def test_client_model_missing_client_branches(app):
    """Verify ClientModel validation methods gracefully handle nonexistent clients."""
    with app.app_context():
        conn = get_db(app.config["DATABASE_PATH"])
        assert not ClientModel.validate_redirect_uri(
            conn, "missing_client", "http://any.com"
        )
        assert not ClientModel.validate_scopes(conn, "missing_client", ["openid"])
        assert not ClientModel.validate_grant_type(conn, "missing_client", "code")
        assert not ClientModel.verify_secret(conn, "missing_client", "secret")


def test_database_connection_teardown(app):
    """Verify close_db teardown function safely handles open and closed contexts."""
    with app.app_context():
        conn = get_db()
        assert conn is not None
        close_db()
        # Safe to call multiple times
        close_db()
