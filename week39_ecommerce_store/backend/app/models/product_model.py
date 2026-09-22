from flask import has_app_context

from app.db import get_db, query_db


class ProductModel:
    SORT_MAP = {
        "price_asc": "p.price_cents ASC, p.id ASC",
        "price_desc": "p.price_cents DESC, p.id ASC",
        "name_asc": "p.title ASC, p.id ASC",
        "newest": "p.created_at DESC, p.id DESC",
    }

    @classmethod
    def _format_product(cls, row):
        if not row:
            return None
        data = dict(row)
        data["price_formatted"] = f"${data['price_cents'] / 100:.2f}"
        return data

    @classmethod
    def get_all(
        cls,
        category=None,
        sort=None,
        search=None,
        limit=20,
        offset=0,
        active_only=True,
        db_path=None,
    ):
        try:
            limit = max(1, min(int(limit), 100))
        except (ValueError, TypeError):
            limit = 20

        try:
            offset = max(0, int(offset))
        except (ValueError, TypeError):
            offset = 0

        where_clauses = []
        params = []

        if active_only:
            where_clauses.append("p.is_active = 1")

        if category:
            where_clauses.append("p.category_slug = ?")
            params.append(category)

        if search and search.strip():
            search_term = f"%{search.strip()}%"
            where_clauses.append("(p.title LIKE ? OR p.description LIKE ?)")
            params.extend([search_term, search_term])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        order_by = cls.SORT_MAP.get(sort, "p.id ASC")

        count_sql = f"""
            SELECT COUNT(*) as count
            FROM products p
            JOIN categories c ON p.category_slug = c.slug
            {where_sql}
        """  # nosec B608
        count_res = query_db(count_sql, params, one=True, db_path=db_path)
        total = count_res["count"] if count_res else 0

        data_sql = f"""
            SELECT p.*, c.name as category_name
            FROM products p
            JOIN categories c ON p.category_slug = c.slug
            {where_sql}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """  # nosec B608
        data_params = list(params) + [limit, offset]
        rows = query_db(data_sql, data_params, db_path=db_path)

        items = [cls._format_product(r) for r in rows]

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @classmethod
    def get_by_slug(cls, slug, active_only=True, db_path=None):
        where = "p.slug = ?"
        params = [slug]
        if active_only:
            where += " AND p.is_active = 1"

        sql = f"""
            SELECT p.*, c.name as category_name
            FROM products p
            JOIN categories c ON p.category_slug = c.slug
            WHERE {where}
        """  # nosec B608
        row = query_db(sql, params, one=True, db_path=db_path)
        return cls._format_product(row)

    @classmethod
    def get_by_id(cls, product_id, db_path=None):
        sql = """
            SELECT p.*, c.name as category_name
            FROM products p
            JOIN categories c ON p.category_slug = c.slug
            WHERE p.id = ?
        """
        row = query_db(sql, [product_id], one=True, db_path=db_path)
        return cls._format_product(row)

    @classmethod
    def get_by_sku(cls, sku, db_path=None):
        sql = """
            SELECT p.*, c.name as category_name
            FROM products p
            JOIN categories c ON p.category_slug = c.slug
            WHERE p.sku = ?
        """
        row = query_db(sql, [sku], one=True, db_path=db_path)
        return cls._format_product(row)

    @classmethod
    def get_categories(cls, db_path=None):
        sql = """
            SELECT c.id, c.slug, c.name, c.description,
                   COUNT(p.id) as product_count
            FROM categories c
            LEFT JOIN products p ON c.slug = p.category_slug AND p.is_active = 1
            GROUP BY c.id
            ORDER BY c.name ASC
        """
        return query_db(sql, db_path=db_path)

    @classmethod
    def update_stock(cls, product_id, delta, db_path=None):
        conn = get_db(db_path=db_path)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE products
            SET stock_quantity = stock_quantity + ?
            WHERE id = ? AND stock_quantity + ? >= 0
            """,
            (delta, product_id, delta),
        )
        affected = cur.rowcount
        conn.commit()
        if not has_app_context():
            conn.close()
        return affected > 0
