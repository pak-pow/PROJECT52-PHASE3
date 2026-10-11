import json
from unittest.mock import patch

from app.graphql.auth import generate_auth_token
from app.graphql.schema import execute_query
from app.models.project_model import (
    get_reviews_by_author,
    get_reviews_by_project,
    get_technologies_by_project,
)


def test_e2e_developer_and_project_lifecycle(client):
    """Verifies complete developer registration, project publishing, and query flow."""
    # 1. Register new developer
    create_user_mutation = """
    mutation CreateDeveloper {
        createUser(input: {
            username: "elena_craft"
            email: "elena@pulsegraph.io"
            role: DEVELOPER
            bio: "Distributed systems and cloud architect."
        }) {
            success
            message
            user {
                id
                username
                email
                role
                bio
            }
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": create_user_mutation}),
        content_type="application/json",
    )
    assert res.status_code == 200
    user_data = res.get_json()["data"]["createUser"]
    assert user_data["success"] is True
    elena = user_data["user"]
    elena_id = elena["id"]
    assert elena["username"] == "elena_craft"
    assert elena["email"] == "elena@pulsegraph.io"

    # 2. Generate HMAC Bearer token and verify viewer query
    token = generate_auth_token(
        {"id": elena_id, "username": "elena_craft", "role": "DEVELOPER"}
    )
    viewer_query = """
    query GetViewer {
        viewer {
            id
            username
            email
            role
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": viewer_query}),
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/json",
    )
    assert res.status_code == 200
    viewer_res = res.get_json()["data"]["viewer"]
    assert viewer_res["id"] == elena_id
    assert viewer_res["username"] == "elena_craft"
    # Owner sees their own unredacted email
    assert viewer_res["email"] == "elena@pulsegraph.io"

    # 3. Create project with technologies
    create_proj_mutation = f"""
    mutation CreateProject {{
        createProject(input: {{
            title: "QuantumMesh Gateway"
            description: "Ultra-fast service mesh built in Python and React."
            status: ACTIVE
            ownerId: {elena_id}
            technologyIds: [1, 2]
        }}) {{
            success
            message
            project {{
                id
                title
                status
                starsCount
                owner {{
                    username
                }}
                technologies {{
                    id
                    name
                }}
            }}
        }}
    }}
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": create_proj_mutation}),
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/json",
    )
    assert res.status_code == 200
    proj_data = res.get_json()["data"]["createProject"]
    assert proj_data["success"] is True
    project = proj_data["project"]
    proj_id = project["id"]
    assert project["title"] == "QuantumMesh Gateway"
    assert project["owner"]["username"] == "elena_craft"
    assert len(project["technologies"]) == 2

    # 4. Update project description
    update_proj_mutation = f"""
    mutation UpdateProject {{
        updateProject(id: {proj_id}, input: {{
            description: "Updated service mesh with sub-millisecond routing."
        }}) {{
            success
            message
            project {{
                id
                description
            }}
        }}
    }}
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": update_proj_mutation}),
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/json",
    )
    assert res.status_code == 200
    update_data = res.get_json()["data"]["updateProject"]
    assert update_data["success"] is True
    assert "sub-millisecond routing" in update_data["project"]["description"]

    # 5. Public unauthenticated query verifies email redaction and extensions
    public_query = f"""
    query PublicProjectDetails {{
        project(id: {proj_id}) {{
            id
            title
            status
            averageRating
            reviewCount
            starsCount
            owner {{
                username
                email
            }}
            technologies {{
                id
                name
                category
            }}
        }}
    }}
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": public_query}),
        content_type="application/json",
    )
    assert res.status_code == 200
    pub_data = res.get_json()
    proj_details = pub_data["data"]["project"]
    assert proj_details["title"] == "QuantumMesh Gateway"
    assert proj_details["averageRating"] is None
    assert proj_details["reviewCount"] == 0
    # Redacted email for public unauthenticated view
    assert proj_details["owner"]["email"] == "e***a@pulsegraph.io"
    # Extensions and Server-Timing header verification
    assert "Server-Timing" in res.headers
    assert "gql;dur=" in res.headers["Server-Timing"]
    ext = pub_data.get("extensions", {})
    assert "duration_ms" in ext
    assert "depth" in ext
    assert "complexity" in ext
    assert "dataloaders" in ext


def test_e2e_peer_review_lifecycle_and_recalculation(client):
    """Verifies peer review submissions, aggregate rating updates, and stars."""
    # 1. Register author Marcus and reviewer Sophia
    res_m = client.post(
        "/graphql",
        data=json.dumps({"query": """
            mutation {
                createUser(input: {
                    username: "marcus_author"
                    email: "marcus_author@pulsegraph.io"
                    role: DEVELOPER
                }) {
                    user { id username }
                }
            }
            """}),
        content_type="application/json",
    )
    marcus_id = res_m.get_json()["data"]["createUser"]["user"]["id"]

    res_s = client.post(
        "/graphql",
        data=json.dumps({"query": """
            mutation {
                createUser(input: {
                    username: "sophia_reviewer"
                    email: "sophia_reviewer@pulsegraph.io"
                    role: DEVELOPER
                }) {
                    user { id username }
                }
            }
            """}),
        content_type="application/json",
    )
    sophia_id = res_s.get_json()["data"]["createUser"]["user"]["id"]

    # 2. Marcus creates project
    res_p = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            mutation {{
                createProject(input: {{
                    title: "Apex Core Engine"
                    description: "High speed runtime engine."
                    status: ACTIVE
                    ownerId: {marcus_id}
                    technologyIds: [1]
                }}) {{
                    project {{ id }}
                }}
            }}
            """}),
        content_type="application/json",
    )
    proj_id = res_p.get_json()["data"]["createProject"]["project"]["id"]

    # 3. Sophia adds 5-star review
    token_sophia = generate_auth_token(
        {"id": sophia_id, "username": "sophia_reviewer", "role": "DEVELOPER"}
    )
    res_r1 = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            mutation {{
                createReview(input: {{
                    projectId: {proj_id}
                    authorId: {sophia_id}
                    rating: 5
                    comment: "Outstanding execution and architecture."
                }}) {{
                    success
                    review {{ id rating }}
                }}
            }}
            """}),
        headers={"Authorization": f"Bearer {token_sophia}"},
        content_type="application/json",
    )
    assert res_r1.status_code == 200
    rev1 = res_r1.get_json()["data"]["createReview"]["review"]
    assert rev1["rating"] == 5

    # Verify project rating is 5.0 and reviewCount is 1
    res_check = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            query {{
                project(id: {proj_id}) {{
                    averageRating
                    reviewCount
                }}
            }}
            """}),
        content_type="application/json",
    )
    p_stat = res_check.get_json()["data"]["project"]
    assert p_stat["averageRating"] == 5.0
    assert p_stat["reviewCount"] == 1

    # 4. Marcus adds 3-star review
    token_marcus = generate_auth_token(
        {"id": marcus_id, "username": "marcus_author", "role": "DEVELOPER"}
    )
    res_r2 = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            mutation {{
                createReview(input: {{
                    projectId: {proj_id}
                    authorId: {marcus_id}
                    rating: 3
                    comment: "Initial release, needs performance tuning."
                }}) {{
                    success
                    review {{ id rating }}
                }}
            }}
            """}),
        headers={"Authorization": f"Bearer {token_marcus}"},
        content_type="application/json",
    )
    assert res_r2.status_code == 200

    # Verify project average rating recalculated: (5 + 3) / 2 = 4.0
    res_check2 = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            query {{
                project(id: {proj_id}) {{
                    averageRating
                    reviewCount
                }}
            }}
            """}),
        content_type="application/json",
    )
    p_stat2 = res_check2.get_json()["data"]["project"]
    assert p_stat2["averageRating"] == 4.0
    assert p_stat2["reviewCount"] == 2

    # 5. Sophia stars project
    res_star = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            mutation {{
                starProject(id: {proj_id}) {{
                    success
                    project {{
                        starsCount
                    }}
                }}
            }}
            """}),
        headers={"Authorization": f"Bearer {token_sophia}"},
        content_type="application/json",
    )
    star_res = res_star.get_json()["data"]["starProject"]
    assert star_res["success"] is True
    assert star_res["project"]["starsCount"] >= 1

    # 6. Delete project
    res_del_proj = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            mutation {{
                deleteProject(id: {proj_id}) {{
                    success
                    deletedId
                }}
            }}
            """}),
        headers={"Authorization": f"Bearer {token_marcus}"},
        content_type="application/json",
    )
    assert res_del_proj.status_code == 200
    del_data = res_del_proj.get_json()["data"]["deleteProject"]
    assert del_data["success"] is True
    assert del_data["deletedId"] == proj_id

    # Confirm project is deleted
    res_check3 = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            query {{
                project(id: {proj_id}) {{
                    id
                    title
                }}
            }}
            """}),
        content_type="application/json",
    )
    assert res_check3.get_json()["data"]["project"] is None


def test_e2e_security_depth_limit_protection(client):
    """Verifies recursive AST query exceeding depth 7 is rejected with HTTP 400."""
    deep_query = """
    query ExcessiveDepth {
        projects {
            owner {
                projects {
                    owner {
                        projects {
                            owner {
                                projects {
                                    owner {
                                        id
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": deep_query}),
        content_type="application/json",
    )
    assert res.status_code == 400
    errors = res.get_json()["errors"]
    assert any("maximum allowed depth" in err["message"].lower() for err in errors)


def test_e2e_security_complexity_limit_protection(client):
    """Verifies complex query exceeding limit 300 is rejected with HTTP 400."""
    complex_query = """
    query ExcessiveComplexity {
        p1: projects {
            technologies { id name }
            reviews { id rating author { projects { technologies { id name } } } }
        }
        p2: projects {
            technologies { id name }
            reviews { id rating author { projects { technologies { id name } } } }
        }
        p3: projects {
            technologies { id name }
            reviews { id rating author { projects { technologies { id name } } } }
        }
        p4: projects {
            technologies { id name }
            reviews { id rating author { projects { technologies { id name } } } }
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": complex_query}),
        content_type="application/json",
    )
    assert res.status_code == 400
    errors = res.get_json()["errors"]
    assert any("maximum allowed limit" in err["message"].lower() for err in errors)


def test_e2e_security_auth_rbac_and_ownership_guards(client):
    """Verifies authorization, role-based access, and cross-user ownership guards."""
    # 1. Create Alice and Dave
    res_a = client.post(
        "/graphql",
        data=json.dumps({"query": """
            mutation {
                createUser(input: {
                    username: "alice_author"
                    email: "alice@pulsegraph.io"
                    role: DEVELOPER
                }) { user { id } }
            }
            """}),
        content_type="application/json",
    )
    alice_id = res_a.get_json()["data"]["createUser"]["user"]["id"]

    res_d = client.post(
        "/graphql",
        data=json.dumps({"query": """
            mutation {
                createUser(input: {
                    username: "dave_attacker"
                    email: "dave@pulsegraph.io"
                    role: DEVELOPER
                }) { user { id } }
            }
            """}),
        content_type="application/json",
    )
    dave_id = res_d.get_json()["data"]["createUser"]["user"]["id"]

    token_dave = generate_auth_token(
        {"id": dave_id, "username": "dave_attacker", "role": "DEVELOPER"}
    )

    # 2. Alice creates a project
    res_p = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            mutation {{
                createProject(input: {{
                    title: "Alice Vault"
                    description: "Private secure vault."
                    status: ACTIVE
                    ownerId: {alice_id}
                }}) {{ project {{ id }} }}
            }}
            """}),
        content_type="application/json",
    )
    alice_proj_id = res_p.get_json()["data"]["createProject"]["project"]["id"]

    # 3. Dave attempts to update Alice's project -> denied
    res_hack_up = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            mutation {{
                updateProject(id: {alice_proj_id}, input: {{
                    title: "Compromised Title"
                }}) {{
                    success
                    message
                }}
            }}
            """}),
        headers={"Authorization": f"Bearer {token_dave}"},
        content_type="application/json",
    )
    assert res_hack_up.status_code == 200
    res_data = res_hack_up.get_json()["data"]["updateProject"]
    assert res_data["success"] is False
    assert (
        "denied" in res_data["message"].lower()
        or "owner" in res_data["message"].lower()
    )

    # 4. Dave attempts to delete Alice's project -> denied
    res_hack_del = client.post(
        "/graphql",
        data=json.dumps({"query": f"""
            mutation {{
                deleteProject(id: {alice_proj_id}) {{
                    success
                    message
                }}
            }}
            """}),
        headers={"Authorization": f"Bearer {token_dave}"},
        content_type="application/json",
    )
    assert res_hack_del.status_code == 200
    res_del_data = res_hack_del.get_json()["data"]["deleteProject"]
    assert res_del_data["success"] is False
    assert (
        "denied" in res_del_data["message"].lower()
        or "owner" in res_del_data["message"].lower()
    )

    # 5. Role guard: Unauthenticated user accesses adminUsers -> fails
    res_unauth_admin = client.post(
        "/graphql",
        data=json.dumps({"query": "query { adminUsers { id username } }"}),
        content_type="application/json",
    )
    assert res_unauth_admin.status_code == 200
    assert "errors" in res_unauth_admin.get_json()
    assert (
        "authentication required"
        in res_unauth_admin.get_json()["errors"][0]["message"].lower()
    )

    # 6. Role guard: Developer accesses adminUsers -> fails
    res_dev_admin = client.post(
        "/graphql",
        data=json.dumps({"query": "query { adminUsers { id username } }"}),
        headers={"Authorization": f"Bearer {token_dave}"},
        content_type="application/json",
    )
    assert res_dev_admin.status_code == 200
    assert "errors" in res_dev_admin.get_json()
    assert "access denied" in res_dev_admin.get_json()["errors"][0]["message"].lower()

    # 7. Role guard: Admin user accesses adminUsers -> succeeds
    token_admin = generate_auth_token(
        {"id": 1, "username": "alex_dev", "role": "ADMIN"}
    )
    res_ok_admin = client.post(
        "/graphql",
        data=json.dumps({"query": """
            query {
                adminUsers {
                    id
                    username
                    email
                    role
                }
            }
            """}),
        headers={"Authorization": f"Bearer {token_admin}"},
        content_type="application/json",
    )
    assert res_ok_admin.status_code == 200
    admin_users = res_ok_admin.get_json()["data"]["adminUsers"]
    assert len(admin_users) >= 3
    # Admin sees raw emails
    assert any(u["email"] == "alex@pulsegraph.io" for u in admin_users)


def test_e2e_token_tampering_and_malformed_auth(client):
    """Verifies tampered tokens and malformed authorization headers do not crash."""
    # Tampered signature
    res_tamper = client.post(
        "/graphql",
        data=json.dumps({"query": "query { viewer { id username } }"}),
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.corrupt.signature"},
        content_type="application/json",
    )
    assert res_tamper.status_code == 200
    assert res_tamper.get_json()["data"]["viewer"] is None

    # Empty Bearer string
    res_empty = client.post(
        "/graphql",
        data=json.dumps({"query": "query { viewer { id username } }"}),
        headers={"Authorization": "Bearer "},
        content_type="application/json",
    )
    assert res_empty.status_code == 200
    assert res_empty.get_json()["data"]["viewer"] is None

    # Invalid non-integer X-User-Id header
    res_bad_header = client.post(
        "/graphql",
        data=json.dumps({"query": "query { viewer { id username } }"}),
        headers={"X-User-Id": "not_an_int"},
        content_type="application/json",
    )
    assert res_bad_header.status_code == 200
    assert res_bad_header.get_json()["data"]["viewer"] is None


def test_e2e_named_and_inline_fragments_ast_safety(client):
    """Verifies queries with fragments and introspection fields compute safely."""
    fragment_query = """
    fragment ProjectSummary on ProjectType {
        id
        title
        status
        __typename
    }

    query FragmentTest {
        projects {
            ...ProjectSummary
            owner {
                id
                username
                ... on UserType {
                    role
                    __typename
                }
            }
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": fragment_query}),
        content_type="application/json",
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "data" in data
    assert len(data["data"]["projects"]) > 0
    first_proj = data["data"]["projects"][0]
    assert first_proj["__typename"] == "ProjectType"
    assert first_proj["owner"]["__typename"] == "UserType"


def test_e2e_analytics_and_stats_aggregation(client):
    """Verifies system stats, technologies by category, and analytics overview."""
    query = """
    query AnalyticsAndStats {
        stats {
            totalUsers
            totalProjects
            totalReviews
            totalTechnologies
        }
        technologies(category: BACKEND) {
            id
            name
            category
        }
        frontendTech: technologies(category: FRONTEND) {
            id
            name
            category
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": query}),
        content_type="application/json",
    )
    assert res.status_code == 200
    data = res.get_json()["data"]
    stats = data["stats"]
    assert stats["totalUsers"] >= 3
    assert stats["totalProjects"] >= 1
    assert stats["totalReviews"] >= 1
    assert stats["totalTechnologies"] >= 8

    # Categorized technologies
    backend_techs = data["technologies"]
    assert any(t["name"] == "Python" for t in backend_techs)
    frontend_techs = data["frontendTech"]
    assert any(t["name"] == "React" for t in frontend_techs)


def test_e2e_direct_execution_and_fallback_resolvers(app):
    """Verifies schema execution fallback pathways when DataLoaders are omitted."""
    with app.app_context():
        # Direct execution without context dataloaders
        direct_query = """
        query DirectExecution {
            projects {
                id
                title
                owner {
                    id
                    username
                }
                technologies {
                    id
                    name
                }
                reviews {
                    id
                    rating
                    comment
                    author {
                        username
                    }
                    project {
                        title
                    }
                }
            }
        }
        """
        result = execute_query(direct_query, context_value=None)
        assert result.errors is None
        assert result.data is not None
        assert len(result.data["projects"]) > 0
        proj = result.data["projects"][0]
        assert proj["owner"]["username"] is not None
        assert len(proj["technologies"]) > 0
        assert len(proj["reviews"]) > 0
        assert proj["reviews"][0]["author"]["username"] is not None
        assert proj["reviews"][0]["project"]["title"] is not None

        # Direct model helper verification
        revs_proj = get_reviews_by_project(1)
        assert len(revs_proj) > 0
        revs_author = get_reviews_by_author(2)
        assert len(revs_author) > 0
        techs_proj = get_technologies_by_project(1)
        assert len(techs_proj) > 0


def test_e2e_queries_and_mutations_error_fallbacks(app):
    """Verifies graceful fallback behavior when model functions encounter errors."""
    with app.app_context():
        # Mock exceptions in query resolvers to exercise mock fallbacks
        with patch(
            "app.models.project_model.get_system_stats",
            side_effect=Exception("DB Error"),
        ):
            q_stats = execute_query("query { stats { totalUsers } }")
            assert q_stats.data["stats"]["totalUsers"] > 0

        with patch(
            "app.models.project_model.list_technologies",
            side_effect=Exception("DB Error"),
        ):
            q_tech = execute_query("query { technologies(category: BACKEND) { name } }")
            assert len(q_tech.data["technologies"]) > 0

        with patch(
            "app.models.user_model.list_users",
            side_effect=Exception("DB Error"),
        ):
            q_users = execute_query("query { users { username } }")
            assert len(q_users.data["users"]) > 0

        with patch(
            "app.models.project_model.list_projects",
            side_effect=Exception("DB Error"),
        ):
            q_proj = execute_query("query { projects { title } }")
            assert len(q_proj.data["projects"]) > 0

        with patch(
            "app.models.project_model.get_project_by_id",
            side_effect=Exception("DB Error"),
        ):
            q_single = execute_query("query { project(id: 1) { title } }")
            assert q_single.data["project"]["title"] is not None

        # Mock mutation error catches
        with patch(
            "app.models.user_model.delete_user",
            return_value=False,
        ):
            res_del_u = execute_query("mutation { deleteUser(id: 999) { success } }")
            assert res_del_u.data["deleteUser"]["success"] is False

        with patch(
            "app.models.project_model.get_project_by_id",
            return_value=None,
        ):
            res_up_p = execute_query(
                "mutation { updateProject(id: 999, "
                'input: { title: "Fail" }) { success } }'
            )
            assert res_up_p.data["updateProject"]["success"] is False

        with patch(
            "app.models.project_model.delete_project",
            return_value=False,
        ):
            res_del_p = execute_query("mutation { deleteProject(id: 999) { success } }")
            assert res_del_p.data["deleteProject"]["success"] is False

        with patch(
            "app.models.project_model.star_project",
            return_value=None,
        ):
            res_star = execute_query("mutation { starProject(id: 999) { success } }")
            assert res_star.data["starProject"]["success"] is False
