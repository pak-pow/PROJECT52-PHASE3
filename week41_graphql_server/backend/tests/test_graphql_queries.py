import json

from app.graphql.schema import execute_query, get_sdl


def test_schema_sdl_endpoint(client):
    """Test /graphql/sdl returns plain-text GraphQL Schema Definition."""
    response = client.get("/graphql/sdl")
    assert response.status_code == 200
    assert "text/plain" in response.content_type
    sdl_text = response.data.decode("utf-8")
    assert "type Query" in sdl_text
    assert "type UserType" in sdl_text
    assert "type ProjectType" in sdl_text
    assert "type TechnologyType" in sdl_text
    assert "interface TimestampedInterface" in sdl_text
    assert "enum ProjectStatusEnum" in sdl_text
    assert "enum TechCategoryEnum" in sdl_text
    assert "enum UserRoleEnum" in sdl_text
    assert "input ProjectFilterInput" in sdl_text


def test_graphql_endpoint_empty_body(client):
    """Test /graphql returns 400 error when query string is missing."""
    response = client.post(
        "/graphql",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "errors" in data
    assert "Must provide query string" in data["errors"][0]["message"]


def test_graphql_hello_and_version_query(client):
    """Test querying hello greeting and API version."""
    query = """
    query {
        hello
        version
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": query}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["hello"] == "Welcome to PulseGraph GraphQL API"
    assert data["data"]["version"] == "1.0.0"


def test_graphql_system_stats_query(client):
    """Test querying aggregate system statistics."""
    query = """
    query {
        stats {
            totalUsers
            totalProjects
            totalReviews
            totalTechnologies
        }
    }
    """
    response = client.post(
        "/graphql",
        data=json.dumps({"query": query}),
        content_type="application/json",
    )
    assert response.status_code == 200
    stats = response.get_json()["data"]["stats"]
    assert stats["totalUsers"] >= 2
    assert stats["totalProjects"] >= 1
    assert stats["totalReviews"] >= 1
    assert stats["totalTechnologies"] >= 4


def test_graphql_technologies_query(client):
    """Test querying technologies with and without category filtering."""
    query_all = """
    query {
        technologies {
            id
            name
            category
            iconSlug
        }
    }
    """
    res_all = client.post(
        "/graphql",
        data=json.dumps({"query": query_all}),
        content_type="application/json",
    )
    assert res_all.status_code == 200
    techs = res_all.get_json()["data"]["technologies"]
    assert len(techs) == 4
    names = [t["name"] for t in techs]
    assert "Python" in names
    assert "GraphQL" in names

    query_filtered = """
    query {
        technologies(category: BACKEND) {
            id
            name
            category
        }
    }
    """
    res_filt = client.post(
        "/graphql",
        data=json.dumps({"query": query_filtered}),
        content_type="application/json",
    )
    assert res_filt.status_code == 200
    filt_techs = res_filt.get_json()["data"]["technologies"]
    assert len(filt_techs) == 2
    for t in filt_techs:
        assert t["category"] == "BACKEND"


def test_graphql_users_query(client):
    """Test querying list of users and individual user by id."""
    query_users = """
    query {
        users {
            id
            username
            email
            role
            bio
            createdAt
            updatedAt
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": query_users}),
        content_type="application/json",
    )
    assert res.status_code == 200
    users = res.get_json()["data"]["users"]
    assert len(users) >= 2
    assert users[0]["username"] == "alex_dev"
    assert users[0]["role"] == "ADMIN"
    assert "createdAt" in users[0]

    # Query single existing user
    query_user = """
    query {
        user(id: 1) {
            id
            username
            email
            role
        }
    }
    """
    res_single = client.post(
        "/graphql",
        data=json.dumps({"query": query_user}),
        content_type="application/json",
    )
    assert res_single.status_code == 200
    user = res_single.get_json()["data"]["user"]
    assert user["id"] == 1
    assert user["username"] == "alex_dev"

    # Query non-existent user
    query_nonexistent = """
    query {
        user(id: 9999) {
            id
            username
        }
    }
    """
    res_none = client.post(
        "/graphql",
        data=json.dumps({"query": query_nonexistent}),
        content_type="application/json",
    )
    assert res_none.status_code == 200
    assert res_none.get_json()["data"]["user"] is None


def test_graphql_projects_query(client):
    """Test querying projects catalog and individual project by id."""
    query_projects = """
    query {
        projects {
            id
            title
            description
            status
            starsCount
            averageRating
            reviewCount
            createdAt
            updatedAt
        }
    }
    """
    res = client.post(
        "/graphql",
        data=json.dumps({"query": query_projects}),
        content_type="application/json",
    )
    assert res.status_code == 200
    projects = res.get_json()["data"]["projects"]
    assert len(projects) >= 1
    assert projects[0]["title"] == "PulseGraph API"
    assert projects[0]["status"] == "ACTIVE"

    # Filter projects by status
    query_filter = """
    query {
        projects(filter: { status: ACTIVE }) {
            id
            title
            status
        }
    }
    """
    res_filt = client.post(
        "/graphql",
        data=json.dumps({"query": query_filter}),
        content_type="application/json",
    )
    assert res_filt.status_code == 200
    filt_projects = res_filt.get_json()["data"]["projects"]
    assert len(filt_projects) >= 1

    # Query single existing project
    query_proj = """
    query {
        project(id: 1) {
            id
            title
            status
        }
    }
    """
    res_proj = client.post(
        "/graphql",
        data=json.dumps({"query": query_proj}),
        content_type="application/json",
    )
    assert res_proj.status_code == 200
    project = res_proj.get_json()["data"]["project"]
    assert project["id"] == 1
    assert project["title"] == "PulseGraph API"

    # Query non-existent project
    query_no_proj = """
    query {
        project(id: 9999) {
            id
            title
        }
    }
    """
    res_no_proj = client.post(
        "/graphql",
        data=json.dumps({"query": query_no_proj}),
        content_type="application/json",
    )
    assert res_no_proj.status_code == 200
    assert res_no_proj.get_json()["data"]["project"] is None


def test_graphql_query_syntax_error(client):
    """Test error response when invalid GraphQL query syntax is supplied."""
    query = "query { nonExistentField }"
    response = client.post(
        "/graphql",
        data=json.dumps({"query": query}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "errors" in data
    assert len(data["errors"]) > 0


def test_schema_direct_execution():
    """Test schema direct execution helper and SDL generator."""
    sdl = get_sdl()
    assert isinstance(sdl, str)
    assert "type Query" in sdl

    result = execute_query(
        "query GetUser($id: Int!) { user(id: $id) { username } }",
        variables={"id": 1},
    )
    assert result.data is not None
    assert result.data["user"]["username"] == "alex_dev"
    assert result.errors is None
