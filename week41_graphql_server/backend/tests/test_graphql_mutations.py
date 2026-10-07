import json


def test_mutation_create_user_success(client):
    """Test creating a new developer profile via GraphQL mutation."""
    mutation = """
    mutation {
        createUser(input: {
            username: "jordan_coder"
            email: "jordan@pulsegraph.io"
            role: DEVELOPER
            bio: "Backend specialist focusing on GraphQL APIs."
        }) {
            success
            message
            user {
                id
                username
                email
                role
                bio
                createdAt
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["createUser"]
    assert res["success"] is True
    assert "successfully" in res["message"]
    user = res["user"]
    assert user["username"] == "jordan_coder"
    assert user["email"] == "jordan@pulsegraph.io"
    assert user["role"] == "DEVELOPER"
    assert user["createdAt"] is not None


def test_mutation_create_user_duplicate_error(client):
    """Test creating a user with an existing username returns error."""
    mutation = """
    mutation {
        createUser(input: {
            username: "alex_dev"
            email: "duplicate@pulsegraph.io"
            role: DEVELOPER
        }) {
            success
            message
            user {
                id
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["createUser"]
    assert res["success"] is False
    assert res["user"] is None
    assert "already exists" in res["message"]


def test_mutation_create_user_empty_fields(client):
    """Test validation when creating a user with whitespace-only username."""
    mutation = """
    mutation {
        createUser(input: {
            username: "   "
            email: "invalid@pulsegraph.io"
        }) {
            success
            message
            user {
                id
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["createUser"]
    assert res["success"] is False
    assert "Username cannot be empty" in res["message"]


def test_mutation_update_user_success(client):
    """Test updating existing developer fields."""
    mutation = """
    mutation {
        updateUser(id: 1, input: {
            bio: "Updated engineer bio for alex."
            role: ADMIN
        }) {
            success
            message
            user {
                id
                bio
                role
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["updateUser"]
    assert res["success"] is True
    assert res["user"]["bio"] == "Updated engineer bio for alex."


def test_mutation_update_user_not_found(client):
    """Test updating a non-existent user returns failure."""
    mutation = """
    mutation {
        updateUser(id: 9999, input: {
            bio: "Ghost bio"
        }) {
            success
            message
            user {
                id
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["updateUser"]
    assert res["success"] is False
    assert "not found" in res["message"]


def test_mutation_delete_user_success(client):
    """Test deleting an existing developer profile."""
    # First create a temp user to delete
    create_m = """
    mutation {
        createUser(input: {
            username: "temp_user"
            email: "temp@pulsegraph.io"
        }) {
            user {
                id
            }
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": create_m}),
        content_type="application/json",
    )
    user_id = res.get_json()["data"]["createUser"]["user"]["id"]

    delete_m = f"""
    mutation {{
        deleteUser(id: {user_id}) {{
            success
            message
            deletedId
        }}
    }}
    """
    del_res = client.post(
        "/graphql",
        data=json.dumps({"query": delete_m}),
        content_type="application/json",
    )
    assert del_res.status_code == 200
    res_data = del_res.get_json()["data"]["deleteUser"]
    assert res_data["success"] is True
    assert res_data["deletedId"] == user_id


def test_mutation_delete_user_not_found(client):
    """Test deleting non-existent user returns not found message."""
    delete_m = """
    mutation {
        deleteUser(id: 9999) {
            success
            message
            deletedId
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": delete_m}),
        content_type="application/json",
    )
    assert res.status_code == 200
    res_data = res.get_json()["data"]["deleteUser"]
    assert res_data["success"] is False
    assert "not found" in res_data["message"]


def test_mutation_create_project_success(client):
    """Test creating a project with linked technologies."""
    mutation = """
    mutation {
        createProject(input: {
            title: "TaskFlow GraphQL Service"
            description: "Distributed task engine built with Python."
            status: ACTIVE
            ownerId: 1
            technologyIds: [1, 2]
        }) {
            success
            message
            project {
                id
                title
                status
                starsCount
                owner {
                    id
                    username
                }
                technologies {
                    id
                    name
                }
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["createProject"]
    assert res["success"] is True
    proj = res["project"]
    assert proj["title"] == "TaskFlow GraphQL Service"
    assert proj["status"] == "ACTIVE"
    assert proj["owner"]["username"] == "alex_dev"
    tech_names = [t["name"] for t in proj["technologies"]]
    assert "Python" in tech_names


def test_mutation_create_project_invalid_owner(client):
    """Test creating a project with a non-existent owner returns error."""
    mutation = """
    mutation {
        createProject(input: {
            title: "Orphan Project"
            ownerId: 9999
        }) {
            success
            message
            project {
                id
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["createProject"]
    assert res["success"] is False
    assert "does not exist" in res["message"]


def test_mutation_create_project_empty_title(client):
    """Test validation when project title is empty."""
    mutation = """
    mutation {
        createProject(input: {
            title: "  "
            ownerId: 1
        }) {
            success
            message
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["createProject"]
    assert res["success"] is False
    assert "cannot be empty" in res["message"]


def test_mutation_update_project_success(client):
    """Test updating existing project title, status, and technologies."""
    mutation = """
    mutation {
        updateProject(id: 1, input: {
            title: "PulseGraph Core Engine"
            status: COMPLETED
            technologyIds: [1, 2, 3]
        }) {
            success
            message
            project {
                id
                title
                status
                technologies {
                    name
                }
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["updateProject"]
    assert res["success"] is True
    proj = res["project"]
    assert proj["title"] == "PulseGraph Core Engine"
    assert proj["status"] == "COMPLETED"
    tech_names = [t["name"] for t in proj["technologies"]]
    assert "React" in tech_names


def test_mutation_update_project_not_found(client):
    """Test updating non-existent project returns failure."""
    mutation = """
    mutation {
        updateProject(id: 9999, input: {
            title: "Phantom"
        }) {
            success
            message
            project {
                id
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": mutation}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["updateProject"]
    assert res["success"] is False
    assert "not found" in res["message"]


def test_mutation_delete_project_success(client):
    """Test deleting project and verifying deletion."""
    delete_m = """
    mutation {
        deleteProject(id: 1) {
            success
            message
            deletedId
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": delete_m}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["deleteProject"]
    assert res["success"] is True
    assert res["deletedId"] == 1


def test_mutation_delete_project_not_found(client):
    """Test deleting non-existent project returns not found."""
    delete_m = """
    mutation {
        deleteProject(id: 9999) {
            success
            message
            deletedId
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": delete_m}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["deleteProject"]
    assert res["success"] is False
    assert "not found" in res["message"]


def test_mutation_star_project(client):
    """Test incrementing stars count on a showcase project."""
    star_m = """
    mutation {
        starProject(id: 1) {
            success
            message
            project {
                id
                starsCount
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": star_m}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["starProject"]
    assert res["success"] is True
    assert res["project"]["starsCount"] >= 43


def test_mutation_star_project_not_found(client):
    """Test starring non-existent project returns failure."""
    star_m = """
    mutation {
        starProject(id: 9999) {
            success
            message
            project {
                id
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": star_m}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["starProject"]
    assert res["success"] is False
    assert "not found" in res["message"]


def test_mutation_create_review_success(client):
    """Test submitting a review and checking updated project metrics."""
    rev_m = """
    mutation {
        createReview(input: {
            projectId: 1
            authorId: 3
            rating: 5
            comment: "Exceptional code quality and clean GraphQL architecture!"
        }) {
            success
            message
            review {
                id
                rating
                comment
                author {
                    username
                }
                project {
                    id
                    title
                }
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": rev_m}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["createReview"]
    assert res["success"] is True
    assert res["review"]["rating"] == 5
    assert res["review"]["author"]["username"] == "marcus_fe"
    assert res["review"]["project"]["id"] == 1


def test_mutation_create_review_invalid_rating(client):
    """Test submitting a review with rating outside 1-5 fails."""
    rev_m = """
    mutation {
        createReview(input: {
            projectId: 1
            authorId: 3
            rating: 10
            comment: "Rating too high"
        }) {
            success
            message
            review {
                id
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": rev_m}),
        content_type="application/json",
    )
    assert response.status_code == 200
    res = response.get_json()["data"]["createReview"]
    assert res["success"] is False
    assert "between 1 and 5" in res["message"]


def test_mutation_create_review_missing_entities(client):
    """Test submitting review for non-existent project or author."""
    # Non-existent project
    rev_proj_missing = """
    mutation {
        createReview(input: {
            projectId: 9999
            authorId: 1
            rating: 4
        }) {
            success
            message
        }
    }
    """
    res1 = client.post(
        "/graphql",
        data=json.dumps({"query": rev_proj_missing}),
        content_type="application/json",
    )
    assert res1.get_json()["data"]["createReview"]["success"] is False

    # Non-existent author
    rev_auth_missing = """
    mutation {
        createReview(input: {
            projectId: 1
            authorId: 9999
            rating: 4
        }) {
            success
            message
        }
    }
    """
    res2 = client.post(
        "/graphql",
        data=json.dumps({"query": rev_auth_missing}),
        content_type="application/json",
    )
    assert res2.get_json()["data"]["createReview"]["success"] is False


def test_relational_traversal_queries(client):
    """Test deep relational queries across users, projects, and reviews."""
    query = """
    query {
        users {
            id
            username
            projectCount
            projects {
                id
                title
                owner {
                    username
                }
                reviews {
                    rating
                    author {
                        username
                    }
                }
            }
            reviews {
                rating
                project {
                    title
                }
            }
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": query}),
        content_type="application/json",
    )
    assert response.status_code == 200
    users = response.get_json()["data"]["users"]
    assert len(users) >= 2
    alex = next((u for u in users if u["username"] == "alex_dev"), None)
    assert alex is not None
    assert alex["projectCount"] >= 1
    assert len(alex["projects"]) >= 1
    assert alex["projects"][0]["owner"]["username"] == "alex_dev"


def test_graphql_project_filters(client):
    """Test GraphQL project catalog filtering by search, tech, minRating."""
    # Filter by search keyword
    q_search = """
    query {
        projects(filter: { search: "PulseGraph" }) {
            id
            title
        }
    }
    """
    res1 = client.post(
        "/graphql",
        data=json.dumps({"query": q_search}),
        content_type="application/json",
    )
    assert res1.status_code == 200
    projs1 = res1.get_json()["data"]["projects"]
    assert len(projs1) >= 1

    # Filter by technologyId and minRating
    q_tech = """
    query {
        projects(filter: { technologyId: 1, minRating: 4.0 }) {
            id
            title
            averageRating
        }
    }
    """
    res2 = client.post(
        "/graphql",
        data=json.dumps({"query": q_tech}),
        content_type="application/json",
    )
    assert res2.status_code == 200
    projs2 = res2.get_json()["data"]["projects"]
    assert len(projs2) >= 1


def test_model_direct_edge_cases(app):
    """Test direct model functions for edge cases and input validation."""
    from app.models.project_model import (
        create_project,
        create_review,
        get_technology_by_id,
        update_project,
    )
    from app.models.user_model import (
        create_user,
        get_user_by_email,
        get_user_by_username,
        update_user,
    )

    with app.app_context():
        # User lookups
        u_by_name = get_user_by_username("alex_dev")
        assert u_by_name is not None
        assert u_by_name["id"] == 1

        u_by_email = get_user_by_email("alex@pulsegraph.io")
        assert u_by_email is not None
        assert u_by_email["id"] == 1

        # Technology lookup
        tech = get_technology_by_id(1)
        assert tech is not None
        assert tech["name"] == "Python"

        # Invalid user creation
        try:
            create_user(username="valid", email="")
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "Email cannot be empty" in str(e)

        try:
            create_user(username="valid", email="v@p.io", role="INVALID_ROLE")
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "Invalid role" in str(e)

        # Update collision
        try:
            update_user(user_id=1, username="sarah_cloud")
            assert False, "Should raise collision ValueError"
        except ValueError as e:
            assert "already in use" in str(e)

        try:
            update_user(user_id=1, role="INVALID_ROLE")
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "Invalid role" in str(e)

        # Invalid project status
        try:
            create_project(title="Test", status="INVALID_STATUS", owner_id=1)
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "Invalid status" in str(e)

        try:
            update_project(project_id=1, status="INVALID_STATUS")
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "Invalid status" in str(e)

        # Invalid review rating
        try:
            create_review(project_id=1, author_id=1, rating="not_a_number")
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "must be an integer" in str(e)
