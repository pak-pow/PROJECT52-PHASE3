import uuid
from datetime import datetime, timezone

from flask import has_app_context

from app.db import get_db, query_db
from app.models.cart_model import CartModel
from app.services.payment_service import get_payment_adapter
from app.services.pricing_service import format_cents


class OrderModel:
    VALID_TRANSITIONS = {
        "pending": ["processing", "paid", "cancelled"],
        "processing": ["paid", "cancelled"],
        "paid": ["shipped", "refunded"],
        "shipped": ["refunded"],
        "cancelled": [],
        "refunded": [],
    }

    @classmethod
    def _format_order(cls, order_row, items_rows=None):
        if not order_row:
            return None
        data = dict(order_row)
        for key in [
            "subtotal_cents",
            "discount_cents",
            "shipping_cents",
            "tax_cents",
            "total_cents",
        ]:
            if key in data:
                fmt_key = key.replace("_cents", "_formatted")
                data[fmt_key] = format_cents(data[key])

        if items_rows is not None:
            items = []
            for ir in items_rows:
                item = dict(ir)
                item["price_formatted"] = format_cents(item["price_cents"])
                item["line_total_formatted"] = format_cents(item["line_total_cents"])
                items.append(item)
            data["items"] = items
        return data

    @classmethod
    def create_order(
        cls,
        cart_token,
        customer_email,
        customer_name,
        shipping_address,
        db_path=None,
    ):
        cart = CartModel.get_cart_by_token(cart_token, db_path=db_path)
        if not cart or not cart.get("items"):
            return False, "Cannot create order from an empty cart.", None

        items = cart["items"]
        pricing = cart["pricing"]

        conn = get_db(db_path=db_path)
        cur = conn.cursor()

        try:
            # Atomic stock reservation: deduct all items
            for item in items:
                cur.execute(
                    """
                    UPDATE products
                    SET stock_quantity = stock_quantity - ?
                    WHERE id = ? AND stock_quantity >= ?
                    """,
                    (item["quantity"], item["product_id"], item["quantity"]),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return (
                        False,
                        f"Insufficient stock for {item['title']}.",
                        None,
                    )

            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
            order_number = f"ORD-{date_str}-{uuid.uuid4().hex[:6].upper()}"

            cur.execute(
                """
                INSERT INTO orders (
                    order_number, cart_token, customer_email, customer_name,
                    shipping_address, status, subtotal_cents, discount_cents,
                    promo_code, shipping_cents, tax_cents, total_cents
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_number,
                    cart_token,
                    customer_email.strip(),
                    customer_name.strip(),
                    shipping_address.strip(),
                    pricing["subtotal_cents"],
                    pricing["discount_cents"],
                    pricing["promo_code"],
                    pricing["shipping_cents"],
                    pricing["tax_cents"],
                    pricing["total_cents"],
                ),
            )
            order_id = cur.lastrowid

            for item in items:
                cur.execute(
                    """
                    INSERT INTO order_items (
                        order_id, product_id, product_title, product_sku,
                        price_cents, quantity, line_total_cents
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        item["product_id"],
                        item["title"],
                        item["sku"],
                        item["price_cents"],
                        item["quantity"],
                        item["line_total_cents"],
                    ),
                )

            # Create payment intent via adapter
            adapter = get_payment_adapter()
            payment_info = adapter.create_payment_intent(
                pricing["total_cents"],
                currency="usd",
                metadata={"order_number": order_number, "order_id": order_id},
            )

            cur.execute(
                "UPDATE orders SET payment_intent_id = ? WHERE id = ?",
                (payment_info["id"], order_id),
            )

            conn.commit()

            # Clear cart on successful order initiation
            CartModel.clear_cart(cart_token, db_path=db_path)

        except Exception as e:
            conn.rollback()
            return False, f"Failed to initialize order: {e}", None
        finally:
            if not has_app_context():
                conn.close()

        order_data = cls.get_by_order_number(order_number, db_path=db_path)
        if order_data:
            order_data["client_secret"] = payment_info["client_secret"]
            order_data["payment_intent_id"] = payment_info["id"]

        return True, None, order_data

    @classmethod
    def get_by_order_number(cls, order_number, db_path=None):
        order = query_db(
            "SELECT * FROM orders WHERE order_number = ?",
            [order_number],
            one=True,
            db_path=db_path,
        )
        if not order:
            return None
        items = query_db(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY id ASC",
            [order["id"]],
            db_path=db_path,
        )
        return cls._format_order(order, items)

    @classmethod
    def get_by_payment_intent_id(cls, payment_intent_id, db_path=None):
        order = query_db(
            "SELECT * FROM orders WHERE payment_intent_id = ?",
            [payment_intent_id],
            one=True,
            db_path=db_path,
        )
        if not order:
            return None
        items = query_db(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY id ASC",
            [order["id"]],
            db_path=db_path,
        )
        return cls._format_order(order, items)

    @classmethod
    def transition_status(cls, order_number, new_status, db_path=None):
        order = cls.get_by_order_number(order_number, db_path=db_path)
        if not order:
            return False, f"Order '{order_number}' not found.", None

        current_status = order["status"]
        allowed = cls.VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            return (
                False,
                f"Cannot transition order from '{current_status}' to '{new_status}'.",
                None,
            )

        conn = get_db(db_path=db_path)
        cur = conn.cursor()

        try:
            # If transitioning to cancelled or refunded, restore reserved stock
            if new_status in ("cancelled", "refunded"):
                for item in order["items"]:
                    cur.execute(
                        """
                        UPDATE products
                        SET stock_quantity = stock_quantity + ?
                        WHERE id = ?
                        """,
                        (item["quantity"], item["product_id"]),
                    )

            cur.execute(
                """
                UPDATE orders
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_status, order["id"]),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            return False, f"Database error during transition: {e}", None
        finally:
            if not has_app_context():
                conn.close()

        updated_order = cls.get_by_order_number(order_number, db_path=db_path)
        return True, None, updated_order

    @classmethod
    def get_invoice(cls, order_number, db_path=None):
        order = cls.get_by_order_number(order_number, db_path=db_path)
        if not order:
            return None

        return {
            "invoice_number": f"INV-{order['order_number'].replace('ORD-', '')}",
            "order_number": order["order_number"],
            "issue_date": order["created_at"],
            "status": order["status"],
            "payment_intent_id": order.get("payment_intent_id"),
            "customer": {
                "name": order["customer_name"],
                "email": order["customer_email"],
                "shipping_address": order["shipping_address"],
            },
            "items": order["items"],
            "pricing": {
                "subtotal_cents": order["subtotal_cents"],
                "subtotal_formatted": order["subtotal_formatted"],
                "discount_cents": order["discount_cents"],
                "discount_formatted": order["discount_formatted"],
                "promo_code": order["promo_code"],
                "shipping_cents": order["shipping_cents"],
                "shipping_formatted": order["shipping_formatted"],
                "tax_cents": order["tax_cents"],
                "tax_formatted": order["tax_formatted"],
                "total_cents": order["total_cents"],
                "total_formatted": order["total_formatted"],
            },
        }
