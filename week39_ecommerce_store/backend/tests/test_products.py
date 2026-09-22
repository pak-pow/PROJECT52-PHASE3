from app.models.product_model import ProductModel


def test_list_products_default(client):
    res = client.get("/api/v1/products")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "success"
    assert len(body["data"]) == 12
    assert body["pagination"]["total"] == 12
    assert body["pagination"]["limit"] == 20
    assert body["pagination"]["offset"] == 0


def test_list_products_category_filter(client):
    res = client.get("/api/v1/products?category=keyboards")
    assert res.status_code == 200
    body = res.get_json()
    assert len(body["data"]) == 3
    for p in body["data"]:
        assert p["category_slug"] == "keyboards"


def test_list_products_search(client):
    res = client.get("/api/v1/products?search=wireless")
    assert res.status_code == 200
    body = res.get_json()
    assert len(body["data"]) >= 1
    assert any("wireless" in p["title"].lower() for p in body["data"])


def test_list_products_sort_price_asc(client):
    res = client.get("/api/v1/products?sort=price_asc")
    assert res.status_code == 200
    items = res.get_json()["data"]
    prices = [p["price_cents"] for p in items]
    assert prices == sorted(prices)


def test_list_products_sort_price_desc(client):
    res = client.get("/api/v1/products?sort=price_desc")
    assert res.status_code == 200
    items = res.get_json()["data"]
    prices = [p["price_cents"] for p in items]
    assert prices == sorted(prices, reverse=True)


def test_list_products_sort_name_asc(client):
    res = client.get("/api/v1/products?sort=name_asc")
    assert res.status_code == 200
    items = res.get_json()["data"]
    titles = [p["title"] for p in items]
    assert titles == sorted(titles)


def test_list_products_pagination(client):
    res = client.get("/api/v1/products?limit=3&offset=0")
    assert res.status_code == 200
    body = res.get_json()
    assert len(body["data"]) == 3
    assert body["pagination"]["total"] == 12

    res2 = client.get("/api/v1/products?limit=3&offset=3")
    body2 = res2.get_json()
    assert len(body2["data"]) == 3
    assert body2["data"][0]["id"] != body["data"][0]["id"]


def test_get_product_by_slug_success(client):
    res = client.get("/api/v1/products/vortex-68-wireless-keyboard")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "success"
    product = body["data"]
    assert product["sku"] == "KB-VORTEX-68"
    assert product["price_cents"] == 12900
    assert product["price_formatted"] == "$129.00"
    assert product["stock_quantity"] == 25


def test_get_product_by_slug_not_found(client):
    res = client.get("/api/v1/products/non-existent-product-slug")
    assert res.status_code == 404
    body = res.get_json()
    assert body["status"] == "error"
    assert body["code"] == "PRODUCT_NOT_FOUND"


def test_list_categories(client):
    res = client.get("/api/v1/categories")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "success"
    categories = body["data"]
    assert len(categories) == 4
    cat_slugs = [c["slug"] for c in categories]
    assert "keyboards" in cat_slugs
    assert "audio" in cat_slugs
    assert "accessories" in cat_slugs
    assert "apparel" in cat_slugs


def test_product_model_direct(app, test_db_path):
    with app.app_context():
        p_by_id = ProductModel.get_by_id(1)
        assert p_by_id is not None
        assert p_by_id["id"] == 1

        p_by_sku = ProductModel.get_by_sku(p_by_id["sku"])
        assert p_by_sku is not None
        assert p_by_sku["id"] == 1

        p_none = ProductModel.get_by_id(999999)
        assert p_none is None

        # Stock update
        orig_stock = p_by_id["stock_quantity"]
        assert ProductModel.update_stock(1, -5) is True
        updated = ProductModel.get_by_id(1)
        assert updated["stock_quantity"] == orig_stock - 5

        # Over-deduction fails
        assert ProductModel.update_stock(1, -99999) is False
