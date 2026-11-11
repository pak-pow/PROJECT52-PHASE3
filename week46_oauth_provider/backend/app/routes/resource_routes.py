"""Protected demo resource server endpoints validating Bearer JWTs."""

import uuid

from flask import Blueprint, jsonify, request

from app.services.token_guard import require_oauth_token

resource_bp = Blueprint("resource", __name__)


@resource_bp.route("/api/v1/resource/profile", methods=["GET"])
@require_oauth_token(any_of_scopes=["profile", "read:profile", "openid"])
def get_resource_profile():
    """Protected resource returning authenticated subject profile details."""
    user = getattr(request, "oauth_user", None)
    sub = getattr(request, "oauth_sub", None)
    client_id = getattr(request, "oauth_client_id", None)
    scopes = list(getattr(request, "oauth_scopes", []))

    profile_data = {
        "sub": sub,
        "client_id": client_id,
        "authorized_scopes": scopes,
    }

    if user:
        profile_data.update(
            {
                "email": user.get("email"),
                "full_name": user.get("full_name"),
                "is_active": bool(user.get("is_active")),
            }
        )

    return jsonify({"status": "success", "data": profile_data}), 200


@resource_bp.route("/api/v1/resource/documents", methods=["GET"])
@require_oauth_token(required_scopes=["read:documents"])
def get_resource_documents():
    """Protected resource returning sensitive documents (read:documents scope)."""
    sub = getattr(request, "oauth_sub", None)
    client_id = getattr(request, "oauth_client_id", None)

    documents = [
        {
            "id": "doc-sec-001",
            "title": "OAuth 2.0 / OIDC Identity Architecture Specification",
            "classification": "Confidential",
            "owner": sub,
        },
        {
            "id": "doc-sec-002",
            "title": "Decentralized RS256 JWKS Key Distribution Policy",
            "classification": "Internal",
            "owner": sub,
        },
        {
            "id": "doc-sec-003",
            "title": "PKCE S256 Cryptographic Verification Playbook",
            "classification": "Restricted",
            "owner": sub,
        },
    ]

    return (
        jsonify(
            {
                "status": "success",
                "client_id": client_id,
                "count": len(documents),
                "data": documents,
            }
        ),
        200,
    )


@resource_bp.route("/api/v1/resource/documents", methods=["POST"])
@require_oauth_token(required_scopes=["write:documents"])
def create_resource_document():
    """Protected resource creating a new document (write:documents scope)."""
    data = request.get_json(silent=True) or request.form or {}
    title = data.get("title")
    if not title:
        return (
            jsonify(
                {
                    "error": "invalid_request",
                    "error_description": "Missing required 'title' parameter.",
                }
            ),
            400,
        )

    classification = data.get("classification", "Internal")
    doc_id = f"doc-user-{uuid.uuid4().hex[:8]}"
    sub = getattr(request, "oauth_sub", None)
    client_id = getattr(request, "oauth_client_id", None)

    created_doc = {
        "id": doc_id,
        "title": title.strip(),
        "classification": classification,
        "owner": sub,
        "client_id": client_id,
    }

    return (
        jsonify(
            {
                "status": "success",
                "message": "Document created successfully.",
                "data": created_doc,
            }
        ),
        201,
    )
