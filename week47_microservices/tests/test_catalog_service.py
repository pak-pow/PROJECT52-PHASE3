"""Unit and integration tests for Catalog & Inventory Service."""

import pytest
from flask.testing import FlaskClient

from services.catalog.app import create_catalog_app
from shared.config import TestingConfig


@pytest.fixture
def catalog_client() -> FlaskClient:
    """Fixture providing a test client for an isolated in-memory Catalog app."""
    app = create_catalog_app(config_class=TestingConfig, db_path=":memory:")
    return app.test_client()


def test_catalog_health_probe(catalog_client: FlaskClient) -> None:
    """Verify catalog vitality probe."""
    res = catalog_client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "UP"
    assert data["service"] == "catalog-service"
    assert "instance_id" in data


def test_product_creation_and_listing(catalog_client: FlaskClient) -> None:
    """Verify product SKU registration and retrieval with available stock."""
    # Register product
    res = catalog_client.post(
        "/api/v1/products",
        json={
            "sku": "PROD-LAPTOP-01",
            "name": "PulseBook Pro 16",
            "price_cents": 199900,
            "stock_quantity": 25,
            "description": "High performance developer laptop",
        },
    )
    assert res.status_code == 201
    product = res.get_json()
    assert product["sku"] == "PROD-LAPTOP-01"
    assert product["available_stock"] == 25
    assert product["reserved_stock"] == 0
    prod_id = product["id"]

    # Fetch product by ID
    get_res = catalog_client.get(f"/api/v1/products/{prod_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["name"] == "PulseBook Pro 16"

    # List products
    list_res = catalog_client.get("/api/v1/products")
    assert list_res.status_code == 200
    assert list_res.get_json()["count"] == 1


def test_product_creation_validation_errors(
    catalog_client: FlaskClient,
) -> None:
    """Verify validation errors on malformed product payloads."""
    # Empty payload
    res = catalog_client.post("/api/v1/products", data="bad", content_type="text/plain")
    assert res.status_code == 400

    # Empty SKU
    res = catalog_client.post(
        "/api/v1/products",
        json={"sku": "", "name": "Item", "price_cents": 100, "stock_quantity": 5},
    )
    assert res.status_code == 400
    assert "SKU cannot be empty" in res.get_json()["message"]

    # Empty Name
    res = catalog_client.post(
        "/api/v1/products",
        json={"sku": "SKU-1", "name": " ", "price_cents": 100, "stock_quantity": 5},
    )
    assert res.status_code == 400

    # Negative price
    res = catalog_client.post(
        "/api/v1/products",
        json={"sku": "SKU-2", "name": "Item", "price_cents": -5, "stock_quantity": 5},
    )
    assert res.status_code == 400

    # Valid product
    catalog_client.post(
        "/api/v1/products",
        json={
            "sku": "SKU-UNIQUE",
            "name": "Item",
            "price_cents": 500,
            "stock_quantity": 10,
        },
    )

    # Duplicate SKU
    dup_res = catalog_client.post(
        "/api/v1/products",
        json={
            "sku": "SKU-UNIQUE",
            "name": "Item 2",
            "price_cents": 500,
            "stock_quantity": 10,
        },
    )
    assert dup_res.status_code == 400
    assert "already exists" in dup_res.get_json()["message"]


def test_atomic_inventory_reservation_lifecycle(
    catalog_client: FlaskClient,
) -> None:
    """Verify atomic reservation, available stock calculations, and idempotency."""
    # Create two products
    p1 = catalog_client.post(
        "/api/v1/products",
        json={
            "sku": "ITEM-A",
            "name": "Keyboard",
            "price_cents": 9900,
            "stock_quantity": 10,
        },
    ).get_json()
    p2 = catalog_client.post(
        "/api/v1/products",
        json={
            "sku": "ITEM-B",
            "name": "Mouse",
            "price_cents": 4900,
            "stock_quantity": 5,
        },
    ).get_json()

    # Reserve 2 Keyboards and 3 Mice for order ord_001
    res = catalog_client.post(
        "/api/v1/inventory/reserve",
        json={
            "order_id": "ord_001",
            "items": [
                {"product_id": p1["id"], "quantity": 2},
                {"product_id": p2["id"], "quantity": 3},
            ],
        },
    )
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["status"] == "RESERVED"
    assert res_data["reservation_count"] == 2

    # Check available stock
    p1_updated = catalog_client.get(f"/api/v1/products/{p1['id']}").get_json()
    assert p1_updated["available_stock"] == 8
    assert p1_updated["reserved_stock"] == 2

    p2_updated = catalog_client.get(f"/api/v1/products/{p2['id']}").get_json()
    assert p2_updated["available_stock"] == 2
    assert p2_updated["reserved_stock"] == 3

    # Idempotent re-reservation of same order
    re_res = catalog_client.post(
        "/api/v1/inventory/reserve",
        json={
            "order_id": "ord_001",
            "items": [{"product_id": p1["id"], "quantity": 2}],
        },
    )
    assert re_res.status_code == 200
    assert re_res.get_json()["already_reserved"] is True


def test_insufficient_stock_atomic_rollback(
    catalog_client: FlaskClient,
) -> None:
    """Verify insufficient stock rejects entire reservation without partial reserves."""
    p1 = catalog_client.post(
        "/api/v1/products",
        json={
            "sku": "ITEM-C",
            "name": "Monitor",
            "price_cents": 35000,
            "stock_quantity": 2,
        },
    ).get_json()

    # Attempt to reserve 5 when only 2 available
    res = catalog_client.post(
        "/api/v1/inventory/reserve",
        json={
            "order_id": "ord_overflow",
            "items": [{"product_id": p1["id"], "quantity": 5}],
        },
    )
    assert res.status_code == 400
    assert "Insufficient stock" in res.get_json()["message"]

    # Verify stock remained untouched
    p1_check = catalog_client.get(f"/api/v1/products/{p1['id']}").get_json()
    assert p1_check["available_stock"] == 2
    assert p1_check["reserved_stock"] == 0


def test_compensating_release_lifecycle(
    catalog_client: FlaskClient,
) -> None:
    """Verify compensating release restores available stock upon order failure."""
    p = catalog_client.post(
        "/api/v1/products",
        json={
            "sku": "ITEM-D",
            "name": "Headphones",
            "price_cents": 12000,
            "stock_quantity": 4,
        },
    ).get_json()

    # Reserve 3 units
    catalog_client.post(
        "/api/v1/inventory/reserve",
        json={
            "order_id": "ord_fail_01",
            "items": [{"product_id": p["id"], "quantity": 3}],
        },
    )
    assert (
        catalog_client.get(f"/api/v1/products/{p['id']}").get_json()["available_stock"]
        == 1
    )

    # Compensating action: Release reservation
    rel_res = catalog_client.post(
        "/api/v1/inventory/release", json={"order_id": "ord_fail_01"}
    )
    assert rel_res.status_code == 200
    assert rel_res.get_json()["released_count"] == 1

    # Available stock restored
    assert (
        catalog_client.get(f"/api/v1/products/{p['id']}").get_json()["available_stock"]
        == 4
    )


def test_commit_stock_lifecycle(catalog_client: FlaskClient) -> None:
    """Verify committing stock permanently deducts from product stock_quantity."""
    p = catalog_client.post(
        "/api/v1/products",
        json={
            "sku": "ITEM-E",
            "name": "Tablet",
            "price_cents": 45000,
            "stock_quantity": 10,
        },
    ).get_json()

    # Reserve 4 units
    catalog_client.post(
        "/api/v1/inventory/reserve",
        json={
            "order_id": "ord_commit_01",
            "items": [{"product_id": p["id"], "quantity": 4}],
        },
    )

    # Commit stock permanently
    com_res = catalog_client.post(
        "/api/v1/inventory/commit", json={"order_id": "ord_commit_01"}
    )
    assert com_res.status_code == 200
    assert com_res.get_json()["committed_count"] == 1

    # Check that stock_quantity itself was decremented from 10 to 6
    p_after = catalog_client.get(f"/api/v1/products/{p['id']}").get_json()
    assert p_after["stock_quantity"] == 6
    assert p_after["available_stock"] == 6
    assert p_after["reserved_stock"] == 0

    # Query reservation history
    hist_res = catalog_client.get("/api/v1/inventory/orders/ord_commit_01")
    assert hist_res.status_code == 200
    assert hist_res.get_json()["reservations"][0]["status"] == "COMMITTED"


def test_catalog_edge_cases(catalog_client: FlaskClient) -> None:
    """Verify error edge cases across catalog endpoints and inventory engine."""
    # Product not found
    assert catalog_client.get("/api/v1/products/prod_missing").status_code == 404

    # Reserve non-dict payload
    bad_res = catalog_client.post(
        "/api/v1/inventory/reserve", data="bad", content_type="text/plain"
    )
    assert bad_res.status_code == 400

    # Reserve with empty order_id or empty items
    res_empty_ord = catalog_client.post(
        "/api/v1/inventory/reserve",
        json={"order_id": "", "items": [{"product_id": "x", "quantity": 1}]},
    )
    assert res_empty_ord.status_code == 400

    res_empty_items = catalog_client.post(
        "/api/v1/inventory/reserve", json={"order_id": "ord_1", "items": []}
    )
    assert res_empty_items.status_code == 400

    # Reserve with missing product_id or invalid quantity
    res_bad_item = catalog_client.post(
        "/api/v1/inventory/reserve",
        json={"order_id": "ord_1", "items": [{"quantity": 1}]},
    )
    assert res_bad_item.status_code == 400

    res_bad_qty = catalog_client.post(
        "/api/v1/inventory/reserve",
        json={"order_id": "ord_1", "items": [{"product_id": "x", "quantity": -1}]},
    )
    assert res_bad_qty.status_code == 400

    # Reserve with unknown product ID
    res_unknown_prod = catalog_client.post(
        "/api/v1/inventory/reserve",
        json={
            "order_id": "ord_1",
            "items": [{"product_id": "prod_unknown", "quantity": 1}],
        },
    )
    assert res_unknown_prod.status_code == 400

    # Release without order_id
    assert catalog_client.post("/api/v1/inventory/release", json={}).status_code == 400

    # Commit without order_id
    assert catalog_client.post("/api/v1/inventory/commit", json={}).status_code == 400
