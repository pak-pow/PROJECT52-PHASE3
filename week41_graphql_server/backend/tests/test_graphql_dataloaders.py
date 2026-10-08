import json

import graphql

from app.graphql.dataloaders import (
    DataLoader,
    batch_load_projects,
    batch_load_projects_for_owners,
    batch_load_reviews_for_authors,
    batch_load_reviews_for_projects,
    batch_load_technologies_for_projects,
    batch_load_users,
    create_dataloaders,
)
from app.graphql.protection import (
    calculate_query_complexity,
    calculate_query_depth,
    validate_query_safety,
)


def test_dataloader_core_caching_and_batching():
    """Test generic DataLoader memoization, batch execution, and stats."""
    call_log = []

    def mock_batch_fn(keys):
        call_log.append(list(keys))
        return {k: f"val_{k}" for k in keys}

    loader = DataLoader(mock_batch_fn)

    # First load misses cache
    val1 = loader.load(10)
    assert val1 == "val_10"
    assert loader.misses == 1
    assert loader.hits == 0
    assert loader.batch_calls == 1

    # Second load hits cache
    val1_cached = loader.load(10)
    assert val1_cached == "val_10"
    assert loader.hits == 1
    assert loader.batch_calls == 1

    # Load many with partial cache
    results = loader.load_many([10, 20, 30, 20])
    assert results == ["val_10", "val_20", "val_30", "val_20"]
    assert loader.batch_calls == 2
    assert call_log[-1] == [20, 30]

    # None handling
    assert loader.load(None) is None
    assert loader.load_many([]) == []
    assert loader.load_many([None]) == [None]

    # Prime, Clear, and Clear All
    loader.prime(99, "val_99")
    assert loader.load(99) == "val_99"
    assert loader.hits == 2

    loader.clear(99)
    assert 99 not in loader.cache

    stats = loader.get_stats()
    assert stats["hits"] == 2
    assert stats["cached_keys"] >= 2
    assert "hit_rate" in stats

    loader.clear_all()
    assert len(loader.cache) == 0


def test_dataloader_with_list_return():
    """Test DataLoader with batch function returning list."""

    def list_batch_fn(keys):
        return [f"res_{k}" for k in keys]

    loader = DataLoader(list_batch_fn)
    res = loader.load_many([1, 2, 3])
    assert res == ["res_1", "res_2", "res_3"]


def test_batch_loaders_direct_queries(app):
    """Test individual entity batch loader functions against SQLite."""
    with app.app_context():
        # Empty inputs return empty dicts without queries
        assert batch_load_users([]) == {}
        assert batch_load_projects([]) == {}
        assert batch_load_technologies_for_projects([]) == {}
        assert batch_load_reviews_for_projects([]) == {}
        assert batch_load_projects_for_owners([]) == {}
        assert batch_load_reviews_for_authors([]) == {}

        # Users batch loading
        users_map = batch_load_users([1, 2, 9999])
        assert 1 in users_map
        assert users_map[1]["username"] == "alex_dev"
        assert 9999 not in users_map

        # Projects batch loading
        projs_map = batch_load_projects([1, 9999])
        assert 1 in projs_map
        assert projs_map[1]["title"] == "PulseGraph API"
        assert projs_map[1]["average_rating"] is not None

        # Project technologies batch loading
        techs_map = batch_load_technologies_for_projects([1])
        assert 1 in techs_map
        assert len(techs_map[1]) >= 2

        # Project reviews batch loading
        revs_map = batch_load_reviews_for_projects([1])
        assert 1 in revs_map
        assert len(revs_map[1]) >= 1

        # Owner projects batch loading
        owner_map = batch_load_projects_for_owners([1])
        assert 1 in owner_map
        assert len(owner_map[1]) >= 1

        # Author reviews batch loading
        author_map = batch_load_reviews_for_authors([2])
        assert 2 in author_map
        assert len(author_map[2]) >= 1


def test_create_dataloaders_registry():
    """Test DataLoaderRegistry instantiation and stats rollup."""
    registry = create_dataloaders()
    stats = registry.get_stats()
    assert "users" in stats
    assert "projects" in stats
    assert "technologies" in stats
    assert "project_reviews" in stats
    assert "owner_projects" in stats
    assert "author_reviews" in stats


def test_query_depth_and_complexity_protection():
    """Test query AST depth and complexity calculations."""
    shallow_query = """
    query {
        hello
        version
    }
    """
    ast_shallow = graphql.parse(shallow_query)
    depth_shallow = calculate_query_depth(ast_shallow)
    assert depth_shallow == 1

    nested_query = """
    query {
        projects {
            owner {
                projects {
                    technologies {
                        name
                    }
                }
            }
        }
    }
    """
    ast_nested = graphql.parse(nested_query)
    depth_nested = calculate_query_depth(ast_nested)
    assert depth_nested == 5

    complexity_nested = calculate_query_complexity(ast_nested)
    assert complexity_nested > 10

    # Safety validator on shallow query
    safe, err, d, c = validate_query_safety(shallow_query)
    assert safe is True
    assert err is None

    # Safety validator rejects excessive depth
    deep_query = """
    query {
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
    safe_deep, err_deep, _, _ = validate_query_safety(deep_query, max_depth=5)
    assert safe_deep is False
    assert "exceeds the maximum allowed depth" in err_deep

    # Safety validator rejects excessive complexity
    safe_comp, err_comp, _, _ = validate_query_safety(nested_query, max_complexity=10)
    assert safe_comp is False
    assert "exceeds maximum allowed limit" in err_comp


def test_graphql_endpoint_query_safety_rejection(client):
    """Test /graphql endpoint rejects queries exceeding depth limit."""
    deep_query = """
    query {
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
    response = client.post(
        "/graphql",
        data=json.dumps({"query": deep_query}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "errors" in data
    assert "exceeds the maximum allowed depth" in data["errors"][0]["message"]


def test_graphql_endpoint_performance_extensions(client):
    """Test /graphql endpoint returns extensions and timing headers."""
    query = """
    query {
        projects {
            id
            title
            owner {
                username
            }
            technologies {
                name
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
    assert "Server-Timing" in response.headers
    assert "gql;dur=" in response.headers["Server-Timing"]

    data = response.get_json()
    assert "extensions" in data
    ext = data["extensions"]
    assert "duration_ms" in ext
    assert "depth" in ext
    assert "complexity" in ext
    assert "dataloaders" in ext
    assert "users" in ext["dataloaders"]


def test_query_protection_syntax_error_and_fragments():
    """Test protection parser handles invalid syntax and fragments."""
    # Syntax error returns safe=True so GraphQL parser can handle error
    safe, err, d, c = validate_query_safety("query { broken_syntax {{")
    assert safe is True
    assert err is None
    assert d == 1
    assert c == 1

    # Query with inline fragment
    fragment_query = """
    query {
        projects {
            ... on ProjectType {
                id
                title
            }
        }
    }
    """
    ast = graphql.parse(fragment_query)
    depth = calculate_query_depth(ast)
    assert depth == 2
    comp = calculate_query_complexity(ast)
    assert comp > 0
