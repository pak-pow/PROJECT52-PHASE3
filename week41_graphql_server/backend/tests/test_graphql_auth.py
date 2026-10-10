import time
from unittest.mock import MagicMock

import pytest
from graphql import GraphQLError

from app.graphql.auth import (
    AUTH_SECRET_KEY,
    decode_auth_token,
    generate_auth_token,
    get_current_user,
    redact_email,
    require_auth,
    require_role,
)
from app.models.project_model import create_project
from app.models.user_model import create_user, get_user_by_id


def test_token_generation_and_tamper_detection():
    """Verifies HMAC token generation, payload decoding, and tamper resistance."""
    user = {"id": 1, "username": "alex_dev", "role": "DEVELOPER"}
    token = generate_auth_token(user)

    assert token is not None
    assert "." in token

    decoded = decode_auth_token(token)
    assert decoded is not None
    assert decoded["sub"] == 1
    assert decoded["username"] == "alex_dev"
    assert decoded["role"] == "DEVELOPER"

    # Tampered signature should fail
    parts = token.split(".")
    tampered_sig = parts[0] + ".00000000000000000000000000000000"
    assert decode_auth_token(tampered_sig) is None

    # Invalid token strings
    assert decode_auth_token("not-a-token") is None
    assert decode_auth_token("") is None
    assert decode_auth_token(None) is None

    # Error handling for invalid user
    with pytest.raises(ValueError):
        generate_auth_token(None)


def test_expired_token_handling():
    """Verifies decode_auth_token rejects expired tokens."""
    import hashlib
    import hmac
    import json

    expired_payload = {
        "sub": 99,
        "username": "expired_user",
        "role": "DEVELOPER",
        "iat": int(time.time()) - 1000,
        "exp": int(time.time()) - 500,
    }
    payload_json = json.dumps(expired_payload, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    expired_token = f"{payload_json.encode('utf-8').hex()}.{sig}"

    assert decode_auth_token(expired_token) is None


def test_email_redaction_helper():
    """Verifies PII email redaction logic."""
    assert redact_email("alex@example.com") == "a***x@example.com"
    assert redact_email("me@domain.org") == "m***@domain.org"
    assert redact_email("") == "redacted@example.com"
    assert redact_email(None) == "redacted@example.com"
    assert redact_email("no_at_sign") == "redacted@example.com"


def test_auth_decorators_direct():
    """Verifies require_auth and require_role decorators directly."""

    @require_auth
    def dummy_auth(root, info):
        return "authenticated"

    @require_role(["ADMIN"])
    def dummy_admin(root, info):
        return "admin_only"

    # 1. Unauthenticated info
    mock_info_anon = MagicMock()
    mock_info_anon.context = {}

    with pytest.raises(GraphQLError, match="Authentication required"):
        dummy_auth(None, mock_info_anon)

    with pytest.raises(GraphQLError, match="Authentication required"):
        dummy_admin(None, mock_info_anon)

    # 2. DEVELOPER info
    mock_info_dev = MagicMock()
    mock_info_dev.context = {
        "current_user": {"id": 2, "role": "DEVELOPER", "username": "dev"}
    }

    assert dummy_auth(None, mock_info_dev) == "authenticated"
    with pytest.raises(GraphQLError, match="insufficient permissions"):
        dummy_admin(None, mock_info_dev)

    # 3. ADMIN info
    mock_info_admin = MagicMock()
    mock_info_admin.context = {
        "current_user": {"id": 1, "role": "ADMIN", "username": "admin"}
    }
    assert dummy_admin(None, mock_info_admin) == "admin_only"


def test_get_current_user_helper():
    """Verifies get_current_user extracts user from various context shapes."""
    assert get_current_user(None) is None

    mock_info = MagicMock()
    mock_info.context = {"current_user": {"id": 5}}
    assert get_current_user(mock_info) == {"id": 5}

    class ContextObj:
        current_user = {"id": 10}

    mock_info2 = MagicMock()
    mock_info2.context = ContextObj()
    assert get_current_user(mock_info2) == {"id": 10}


def test_login_mutation(client):
    """Verifies GraphQL login mutation for existing user and unknown user."""
    query = """
    mutation Login($username: String!) {
        login(username: $username) {
            success
            message
            token
            user {
                id
                username
                role
                email
            }
        }
    }
    """
    res = client.post(
        "/graphql",
        json={"query": query, "variables": {"username": "alex_dev"}},
    )
    assert res.status_code == 200
    data = res.get_json()["data"]["login"]
    assert data["success"] is True
    assert data["token"] is not None
    assert data["user"]["username"] == "alex_dev"
    assert data["user"]["email"] == "alex@pulsegraph.io"

    # Login by email
    res_email = client.post(
        "/graphql",
        json={
            "query": query,
            "variables": {
                "username": "unknown_alias",
                "email": "sarah@pulsegraph.io",
            },
        },
    )
    assert res_email.status_code == 200

    # Unknown user
    res_fail = client.post(
        "/graphql",
        json={"query": query, "variables": {"username": "nonexistent_ghost"}},
    )
    assert res_fail.status_code == 200
    fail_data = res_fail.get_json()["data"]["login"]
    assert fail_data["success"] is False
    assert fail_data["token"] is None
    assert "not found" in fail_data["message"]


def test_viewer_query_anonymous_vs_authenticated(client):
    """Verifies viewer field resolution for anonymous and authenticated clients."""
    query = """
    query GetViewer {
        viewer {
            id
            username
            role
        }
    }
    """
    # 1. Anonymous request
    res_anon = client.post("/graphql", json={"query": query})
    assert res_anon.status_code == 200
    assert res_anon.get_json()["data"]["viewer"] is None

    # 2. Authenticated with Bearer token
    user = get_user_by_id(1)
    token = generate_auth_token(user)

    res_auth = client.post(
        "/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_auth.status_code == 200
    viewer = res_auth.get_json()["data"]["viewer"]
    assert viewer is not None
    assert viewer["id"] == 1
    assert viewer["username"] == user["username"]

    # 3. Authenticated via X-User-Id header
    res_xuid = client.post(
        "/graphql",
        json={"query": query},
        headers={"X-User-Id": "2"},
    )
    assert res_xuid.status_code == 200
    viewer_x = res_xuid.get_json()["data"]["viewer"]
    assert viewer_x is not None
    assert viewer_x["id"] == 2


def test_field_level_email_permission(client):
    """Verifies email is redacted for public view and revealed for owner/admin."""
    target_user = get_user_by_id(2)  # sarah_cloud (DEVELOPER)
    raw_email = target_user["email"]

    query = f"""
    query GetUser {{
        user(id: {target_user["id"]}) {{
            id
            email
            isCurrentUser
        }}
    }}
    """

    # 1. Anonymous requester -> Redacted email
    res_anon = client.post("/graphql", json={"query": query})
    user_data = res_anon.get_json()["data"]["user"]
    assert user_data["email"] != raw_email
    assert "***" in user_data["email"]
    assert user_data["isCurrentUser"] is False

    # 2. Target user viewing themselves -> Full email
    token_self = generate_auth_token(target_user)
    res_self = client.post(
        "/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token_self}"},
    )
    user_self = res_self.get_json()["data"]["user"]
    assert user_self["email"] == raw_email
    assert user_self["isCurrentUser"] is True

    # 3. Different developer user viewing -> Redacted email
    other_user = get_user_by_id(3)
    token_other = generate_auth_token(other_user)
    res_other = client.post(
        "/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token_other}"},
    )
    user_other = res_other.get_json()["data"]["user"]
    assert user_other["email"] != raw_email
    assert "***" in user_other["email"]
    assert user_other["isCurrentUser"] is False

    # 4. Admin user viewing -> Full email
    admin_user = get_user_by_id(1)  # alex_dev (ADMIN)
    token_admin = generate_auth_token(admin_user)
    res_admin = client.post(
        "/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    user_admin = res_admin.get_json()["data"]["user"]
    assert user_admin["email"] == raw_email


def test_admin_audit_users_rbac(client):
    """Verifies role-based access control on admin_users query."""
    query = """
    query AuditUsers {
        adminUsers {
            id
            username
            role
        }
    }
    """

    # 1. Anonymous -> Rejected
    res_anon = client.post("/graphql", json={"query": query})
    assert res_anon.status_code == 200
    assert "Authentication required" in res_anon.get_json()["errors"][0]["message"]

    # 2. DEVELOPER role -> Access denied
    dev_user = get_user_by_id(2)  # Role is DEVELOPER
    token_dev = generate_auth_token(dev_user)
    res_dev = client.post(
        "/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token_dev}"},
    )
    assert res_dev.status_code == 200
    assert "ADMIN role required" in res_dev.get_json()["errors"][0]["message"]

    # 3. ADMIN role -> Granted
    admin_user = get_user_by_id(1)  # Role is ADMIN
    token_admin = generate_auth_token(admin_user)
    res_admin = client.post(
        "/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_admin.status_code == 200
    users = res_admin.get_json()["data"]["adminUsers"]
    assert len(users) >= 2


def test_project_mutation_rbac_ownership(client):
    """Verifies project update and delete mutations enforce owner or admin role."""
    owner = get_user_by_id(2)  # sarah_cloud
    other = get_user_by_id(3)  # marcus_fe
    admin = get_user_by_id(1)  # alex_dev (ADMIN)

    proj = create_project(
        title="Owner Test Project",
        owner_id=owner["id"],
        description="Testing ownership enforcement",
    )
    proj_id = proj["id"]

    update_query = """
    mutation UpdateProj($id: Int!, $input: ProjectUpdateInput!) {
        updateProject(id: $id, input: $input) {
            success
            message
        }
    }
    """

    # 1. Non-owner developer attempts update -> Access denied
    token_other = generate_auth_token(other)
    res_denied = client.post(
        "/graphql",
        json={
            "query": update_query,
            "variables": {"id": proj_id, "input": {"title": "Hacked Title"}},
        },
        headers={"Authorization": f"Bearer {token_other}"},
    )
    assert res_denied.status_code == 200
    res_data = res_denied.get_json()["data"]["updateProject"]
    assert res_data["success"] is False
    assert "Access denied" in res_data["message"]

    # 2. Project owner updates -> Success
    token_owner = generate_auth_token(owner)
    res_owner = client.post(
        "/graphql",
        json={
            "query": update_query,
            "variables": {
                "id": proj_id,
                "input": {"title": "Legit Owner Update"},
            },
        },
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert res_owner.status_code == 200
    assert res_owner.get_json()["data"]["updateProject"]["success"] is True

    # 3. Admin updates -> Success
    token_admin = generate_auth_token(admin)
    res_admin = client.post(
        "/graphql",
        json={
            "query": update_query,
            "variables": {"id": proj_id, "input": {"title": "Admin Override"}},
        },
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.get_json()["data"]["updateProject"]["success"] is True

    # 4. Non-owner attempts delete -> Access denied
    delete_query = """
    mutation DeleteProj($id: Int!) {
        deleteProject(id: $id) {
            success
            message
        }
    }
    """
    res_del_denied = client.post(
        "/graphql",
        json={"query": delete_query, "variables": {"id": proj_id}},
        headers={"Authorization": f"Bearer {token_other}"},
    )
    assert res_del_denied.status_code == 200
    assert res_del_denied.get_json()["data"]["deleteProject"]["success"] is False

    # 5. Owner deletes project -> Success
    res_del_owner = client.post(
        "/graphql",
        json={"query": delete_query, "variables": {"id": proj_id}},
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert res_del_owner.status_code == 200
    assert res_del_owner.get_json()["data"]["deleteProject"]["success"] is True


def test_delete_user_mutation_rbac(client):
    """Verifies deleteUser requires account owner or admin."""
    user_target = create_user("victim_user", "victim@pg.io", role="DEVELOPER")
    user_other = get_user_by_id(3)
    admin = get_user_by_id(1)

    del_user_query = """
    mutation DeleteUserTest($id: Int!) {
        deleteUser(id: $id) {
            success
            message
        }
    }
    """

    # 1. Other user attempts delete -> Denied
    token_other = generate_auth_token(user_other)
    res_other = client.post(
        "/graphql",
        json={"query": del_user_query, "variables": {"id": user_target["id"]}},
        headers={"Authorization": f"Bearer {token_other}"},
    )
    assert res_other.status_code == 200
    assert res_other.get_json()["data"]["deleteUser"]["success"] is False
    assert "Access denied" in res_other.get_json()["data"]["deleteUser"]["message"]

    # 2. Admin deletes user -> Success
    token_admin = generate_auth_token(admin)
    res_admin = client.post(
        "/graphql",
        json={"query": del_user_query, "variables": {"id": user_target["id"]}},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.get_json()["data"]["deleteUser"]["success"] is True
