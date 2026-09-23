from app.models.cart_model import CartModel


def test_get_or_create_cart_new(client):
    res = client.get("/api/v1/cart")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "success"
    cart = body["data"]
    assert "token" in cart
    assert cart["items"] == []
    assert cart["pricing"]["subtotal_cents"] == 0
    assert cart["pricing"]["total_cents"] == 0
    assert "X-Cart-Token" in res.headers


def test_get_cart_existing_token(client):
    res1 = client.get("/api/v1/cart")
    token = res1.headers["X-Cart-Token"]

    res2 = client.get("/api/v1/cart", headers={"X-Cart-Token": token})
    assert res2.status_code == 200
    assert res2.get_json()["data"]["token"] == token


def test_add_item_success(client):
    res = client.post(
        "/api/v1/cart/items",
        json={"product_id": 1, "quantity": 2},
    )
    assert res.status_code == 200
    body = res.get_json()
    cart = body["data"]
    assert len(cart["items"]) == 1
    item = cart["items"][0]
    assert item["product_id"] == 1
    assert item["quantity"] == 2
    assert item["price_cents"] == 12900
    assert item["line_total_cents"] == 25800
    assert cart["pricing"]["subtotal_cents"] == 25800
    # Over $50 -> Free shipping
    assert cart["pricing"]["shipping_cents"] == 0


def test_add_item_duplicate_increments(client):
    res1 = client.post(
        "/api/v1/cart/items",
        json={"product_id": 1, "quantity": 2},
    )
    token = res1.headers["X-Cart-Token"]

    res2 = client.post(
        "/api/v1/cart/items",
        headers={"X-Cart-Token": token},
        json={"product_id": 1, "quantity": 3},
    )
    assert res2.status_code == 200
    items = res2.get_json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["quantity"] == 5


def test_add_item_exceeds_stock(client):
    res = client.post(
        "/api/v1/cart/items",
        json={"product_id": 1, "quantity": 999},
    )
    assert res.status_code == 409
    body = res.get_json()
    assert body["code"] == "INSUFFICIENT_STOCK"


def test_add_item_invalid_product(client):
    res = client.post(
        "/api/v1/cart/items",
        json={"product_id": 99999, "quantity": 1},
    )
    assert res.status_code == 404
    body = res.get_json()
    assert body["code"] == "ITEM_UNAVAILABLE"


def test_add_item_invalid_payload(client):
    res1 = client.post("/api/v1/cart/items", json={"product_id": "one"})
    assert res1.status_code == 400
    assert res1.get_json()["code"] == "INVALID_PRODUCT_ID"

    res2 = client.post("/api/v1/cart/items", json={"product_id": 1, "quantity": -5})
    assert res2.status_code == 400
    assert res2.get_json()["code"] == "INVALID_QUANTITY"


def test_update_item_quantity(client):
    res = client.post(
        "/api/v1/cart/items",
        json={"product_id": 1, "quantity": 2},
    )
    token = res.headers["X-Cart-Token"]

    res_patch = client.patch(
        "/api/v1/cart/items/1",
        headers={"X-Cart-Token": token},
        json={"quantity": 4},
    )
    assert res_patch.status_code == 200
    assert res_patch.get_json()["data"]["items"][0]["quantity"] == 4

    # Quantity 0 removes item
    res_zero = client.patch(
        "/api/v1/cart/items/1",
        headers={"X-Cart-Token": token},
        json={"quantity": 0},
    )
    assert res_zero.status_code == 200
    assert res_zero.get_json()["data"]["items"] == []

    # Invalid input
    res_bad = client.patch(
        "/api/v1/cart/items/1",
        headers={"X-Cart-Token": token},
        json={"quantity": "bad"},
    )
    assert res_bad.status_code == 400


def test_remove_item(client):
    res = client.post(
        "/api/v1/cart/items",
        json={"product_id": 1, "quantity": 2},
    )
    token = res.headers["X-Cart-Token"]

    res_del = client.delete(
        "/api/v1/cart/items/1",
        headers={"X-Cart-Token": token},
    )
    assert res_del.status_code == 200
    assert res_del.get_json()["data"]["items"] == []


def test_clear_cart(client):
    res = client.post(
        "/api/v1/cart/items",
        json={"product_id": 1, "quantity": 2},
    )
    token = res.headers["X-Cart-Token"]

    res_clear = client.delete(
        "/api/v1/cart",
        headers={"X-Cart-Token": token},
    )
    assert res_clear.status_code == 200
    assert res_clear.get_json()["data"]["items"] == []


def test_shipping_tier_calculations(client):
    # Product 11 is $34.00 (3400 cents) -> under $50 threshold -> $6.99 shipping
    res1 = client.post(
        "/api/v1/cart/items",
        json={"product_id": 11, "quantity": 1},
    )
    token = res1.headers["X-Cart-Token"]
    cart1 = res1.get_json()["data"]
    assert cart1["pricing"]["subtotal_cents"] == 3400
    assert cart1["pricing"]["shipping_cents"] == 699
    assert cart1["pricing"]["free_shipping_eligible"] is False

    # Add second tee ($34.00 x 2 = $68.00) -> over $50 -> Free shipping
    res2 = client.post(
        "/api/v1/cart/items",
        headers={"X-Cart-Token": token},
        json={"product_id": 11, "quantity": 1},
    )
    cart2 = res2.get_json()["data"]
    assert cart2["pricing"]["subtotal_cents"] == 6800
    assert cart2["pricing"]["shipping_cents"] == 0
    assert cart2["pricing"]["free_shipping_eligible"] is True


def test_promo_codes(client):
    # Add product 11 ($34.00, 3400 cents)
    res = client.post(
        "/api/v1/cart/items",
        json={"product_id": 11, "quantity": 1},
    )
    token = res.headers["X-Cart-Token"]

    # Test DISCOUNT10 (10% off 3400 = 340 cents discount)
    res_promo1 = client.post(
        "/api/v1/cart/promo",
        headers={"X-Cart-Token": token},
        json={"promo_code": "discount10"},
    )
    assert res_promo1.status_code == 200
    cart_p1 = res_promo1.get_json()["data"]
    assert cart_p1["pricing"]["discount_cents"] == 340
    assert cart_p1["pricing"]["promo_code"] == "DISCOUNT10"

    # Test FREESHIP (shipping becomes 0)
    res_promo2 = client.post(
        "/api/v1/cart/promo",
        headers={"X-Cart-Token": token},
        json={"promo_code": "FREESHIP"},
    )
    assert res_promo2.status_code == 200
    cart_p2 = res_promo2.get_json()["data"]
    assert cart_p2["pricing"]["shipping_cents"] == 0
    assert cart_p2["pricing"]["promo_code"] == "FREESHIP"

    # Test SAVE20 failure when under $100
    res_promo3 = client.post(
        "/api/v1/cart/promo",
        headers={"X-Cart-Token": token},
        json={"promo_code": "SAVE20"},
    )
    assert res_promo3.status_code == 400
    assert res_promo3.get_json()["code"] == "PROMO_NOT_APPLIED"

    # Remove promo
    res_del_promo = client.delete(
        "/api/v1/cart/promo",
        headers={"X-Cart-Token": token},
    )
    assert res_del_promo.status_code == 200
    assert res_del_promo.get_json()["data"]["pricing"]["promo_code"] is None

    # Invalid promo code
    res_invalid = client.post(
        "/api/v1/cart/promo",
        headers={"X-Cart-Token": token},
        json={"promo_code": "INVALID_CODE_XYZ"},
    )
    assert res_invalid.status_code == 400

    # Missing promo code payload
    res_empty = client.post(
        "/api/v1/cart/promo",
        headers={"X-Cart-Token": token},
        json={},
    )
    assert res_empty.status_code == 400


def test_cart_model_edge_cases(app, test_db_path):
    with app.app_context():
        # Add item with quantity <= 0
        success, msg, _ = CartModel.add_item("mock-token", 1, quantity=0)
        assert success is False

        # Apply promo on non-existent cart
        success, msg, _ = CartModel.apply_promo("nonexistent-cart-token", "DISCOUNT10")
        assert success is False

        # Remove promo on non-existent cart
        success, msg, _ = CartModel.remove_promo("nonexistent-cart-token")
        assert success is False

        # Update item exceeding stock
        success, msg, _ = CartModel.update_quantity("mock-token", 1, quantity=99999)
        assert success is False

        # Update non-existent product
        success, msg, _ = CartModel.update_quantity("mock-token", 99999, quantity=2)
        assert success is False
