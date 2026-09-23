import uuid

from flask import has_app_context

from app.db import get_db, query_db
from app.models.product_model import ProductModel
from app.services.pricing_service import (
    calculate_pricing,
    format_cents,
    validate_promo_code,
)


class CartModel:
    @classmethod
    def get_or_create(cls, token=None, db_path=None):
        conn = get_db(db_path=db_path)
        cur = conn.cursor()

        if token:
            cart = query_db(
                "SELECT * FROM carts WHERE token = ?",
                [token],
                one=True,
                db_path=db_path,
            )
            if cart:
                return dict(cart)

        new_token = uuid.uuid4().hex
        cur.execute("INSERT INTO carts (token) VALUES (?)", (new_token,))
        cart_id = cur.lastrowid
        conn.commit()

        if not has_app_context():
            conn.close()

        return {
            "id": cart_id,
            "token": new_token,
            "promo_code": None,
        }

    @classmethod
    def get_cart_by_token(cls, token, db_path=None):
        cart_row = query_db(
            "SELECT * FROM carts WHERE token = ?",
            [token],
            one=True,
            db_path=db_path,
        )
        if not cart_row:
            return None

        cart = dict(cart_row)
        items_sql = """
            SELECT ci.id as item_id, ci.cart_id, ci.product_id, ci.quantity,
                   p.sku, p.title, p.slug, p.price_cents, p.stock_quantity,
                   p.image_url, p.is_active, c.name as category_name
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            JOIN categories c ON p.category_slug = c.slug
            WHERE ci.cart_id = ?
            ORDER BY ci.id ASC
        """
        rows = query_db(items_sql, [cart["id"]], db_path=db_path)

        items = []
        for r in rows:
            item = dict(r)
            item["price_formatted"] = format_cents(item["price_cents"])
            line_cents = item["price_cents"] * item["quantity"]
            item["line_total_cents"] = line_cents
            item["line_total_formatted"] = format_cents(line_cents)
            item["in_stock"] = (
                item["stock_quantity"] >= item["quantity"] and item["is_active"] == 1
            )
            items.append(item)

        pricing = calculate_pricing(items, promo_code=cart.get("promo_code"))

        cart["items"] = items
        cart["pricing"] = pricing
        return cart

    @classmethod
    def add_item(cls, token, product_id, quantity=1, db_path=None):
        if quantity <= 0:
            return False, "Quantity must be greater than zero.", None

        cart = cls.get_or_create(token=token, db_path=db_path)
        product = ProductModel.get_by_id(product_id, db_path=db_path)
        if not product or product["is_active"] != 1:
            return False, "Product is not available.", None

        existing = query_db(
            "SELECT quantity FROM cart_items WHERE cart_id = ? AND product_id = ?",
            (cart["id"], product_id),
            one=True,
            db_path=db_path,
        )
        current_qty = existing["quantity"] if existing else 0
        new_qty = current_qty + quantity

        if new_qty > product["stock_quantity"]:
            avail = product["stock_quantity"]
            return False, f"Cannot add {quantity} more. Only {avail} in stock.", None

        conn = get_db(db_path=db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cart_items (cart_id, product_id, quantity, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(cart_id, product_id) DO UPDATE SET
                quantity = excluded.quantity,
                updated_at = CURRENT_TIMESTAMP
            """,
            (cart["id"], product_id, new_qty),
        )
        conn.commit()
        if not has_app_context():
            conn.close()

        updated_cart = cls.get_cart_by_token(cart["token"], db_path=db_path)
        return True, None, updated_cart

    @classmethod
    def update_quantity(cls, token, product_id, quantity, db_path=None):
        cart = cls.get_or_create(token=token, db_path=db_path)

        if quantity <= 0:
            return cls.remove_item(cart["token"], product_id, db_path=db_path)

        product = ProductModel.get_by_id(product_id, db_path=db_path)
        if not product or product["is_active"] != 1:
            return False, "Product is not available.", None

        if quantity > product["stock_quantity"]:
            avail = product["stock_quantity"]
            return (
                False,
                f"Cannot update to {quantity}. Only {avail} in stock.",
                None,
            )

        conn = get_db(db_path=db_path)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE cart_items
            SET quantity = ?, updated_at = CURRENT_TIMESTAMP
            WHERE cart_id = ? AND product_id = ?
            """,
            (quantity, cart["id"], product_id),
        )
        conn.commit()
        if not has_app_context():
            conn.close()

        updated_cart = cls.get_cart_by_token(cart["token"], db_path=db_path)
        return True, None, updated_cart

    @classmethod
    def remove_item(cls, token, product_id, db_path=None):
        cart = cls.get_or_create(token=token, db_path=db_path)
        conn = get_db(db_path=db_path)
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?",
            (cart["id"], product_id),
        )
        conn.commit()
        if not has_app_context():
            conn.close()

        updated_cart = cls.get_cart_by_token(cart["token"], db_path=db_path)
        return True, None, updated_cart

    @classmethod
    def clear_cart(cls, token, db_path=None):
        cart = cls.get_or_create(token=token, db_path=db_path)
        conn = get_db(db_path=db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart["id"],))
        cur.execute(
            "UPDATE carts SET promo_code = NULL WHERE id = ?",
            (cart["id"],),
        )
        conn.commit()
        if not has_app_context():
            conn.close()

        updated_cart = cls.get_cart_by_token(cart["token"], db_path=db_path)
        return True, None, updated_cart

    @classmethod
    def apply_promo(cls, token, promo_code, db_path=None):
        cart = cls.get_cart_by_token(token, db_path=db_path)
        if not cart:
            return False, "Cart session not found.", None

        subtotal = cart["pricing"]["subtotal_cents"]
        is_valid, err = validate_promo_code(promo_code, subtotal)
        if not is_valid:
            return False, err, None

        clean_code = promo_code.strip().upper()
        conn = get_db(db_path=db_path)
        cur = conn.cursor()
        cur.execute(
            "UPDATE carts SET promo_code = ? WHERE id = ?",
            (clean_code, cart["id"]),
        )
        conn.commit()
        if not has_app_context():
            conn.close()

        updated_cart = cls.get_cart_by_token(token, db_path=db_path)
        return True, None, updated_cart

    @classmethod
    def remove_promo(cls, token, db_path=None):
        cart = cls.get_cart_by_token(token, db_path=db_path)
        if not cart:
            return False, "Cart session not found.", None

        conn = get_db(db_path=db_path)
        cur = conn.cursor()
        cur.execute("UPDATE carts SET promo_code = NULL WHERE id = ?", (cart["id"],))
        conn.commit()
        if not has_app_context():
            conn.close()

        updated_cart = cls.get_cart_by_token(token, db_path=db_path)
        return True, None, updated_cart
