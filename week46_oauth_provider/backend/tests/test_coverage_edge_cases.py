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


def test_auth_code_service_edge_cases(app, seeded_db):
    """Verify unauthorized grant type and code issuance without state."""
    from app.services.auth_code_service import AuthCodeService

    with app.app_context():
        conn = get_db()
        # Client without authorization_code grant
        ClientModel.create(
            conn=conn,
            client_id="credentials-only-client",
            client_name="Credentials Only",
            client_type="confidential",
            client_secret="CredSecret123!",
            redirect_uris=["http://127.0.0.1:3000/callback"],
            grant_types=["client_credentials"],
            scopes=["openid"],
        )

        valid, _, err, desc = AuthCodeService.validate_request(
            conn,
            "code",
            "credentials-only-client",
            "http://127.0.0.1:3000/callback",
            "openid",
        )
        assert not valid
        assert err == "unauthorized_client"

        # Issue code without state
        rec, url = AuthCodeService.issue_code(
            conn=conn,
            client_id="pulse-web-app",
            user_id=1,
            redirect_uri="http://127.0.0.1:3000/callback",
            scope="openid",
            state=None,
        )
        assert rec["code"] is not None
        assert "state=" not in url
