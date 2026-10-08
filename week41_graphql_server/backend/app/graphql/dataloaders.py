from collections import defaultdict

from app.db import get_db


class DataLoader:
    """Generic memoizing batch loader for resolving graph entities."""

    def __init__(self, batch_load_fn):
        self.batch_load_fn = batch_load_fn
        self.cache = {}
        self.hits = 0
        self.misses = 0
        self.batch_calls = 0

    def load(self, key):
        """Loads a single key, returning cached value or batch fetching it."""
        if key is None:
            return None

        if key in self.cache:
            self.hits += 1
            return self.cache[key]

        self.misses += 1
        results = self.load_many([key])
        return results[0] if results else None

    def load_many(self, keys):
        """Loads multiple keys, fetching missing items in a single batch."""
        if not keys:
            return []

        uncached_keys = []
        for k in keys:
            if k not in self.cache and k is not None:
                if k not in uncached_keys:
                    uncached_keys.append(k)

        if uncached_keys:
            self.batch_calls += 1
            batch_results = self.batch_load_fn(uncached_keys)
            if isinstance(batch_results, dict):
                for k in uncached_keys:
                    self.cache[k] = batch_results.get(k)
            elif isinstance(batch_results, list):
                for k, v in zip(uncached_keys, batch_results):
                    self.cache[k] = v

        output = []
        for k in keys:
            if k is None:
                output.append(None)
            else:
                output.append(self.cache.get(k))
        return output

    def prime(self, key, value):
        """Pre-populates the cache with a known key-value pair."""
        if key is not None and key not in self.cache:
            self.cache[key] = value

    def clear(self, key):
        """Invalidates a single key in the cache."""
        self.cache.pop(key, None)

    def clear_all(self):
        """Clears the entire cache."""
        self.cache.clear()

    def get_stats(self):
        """Returns cache efficiency metrics."""
        total = self.hits + self.misses
        hit_rate = round(self.hits / total, 2) if total > 0 else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "batch_calls": self.batch_calls,
            "hit_rate": hit_rate,
            "cached_keys": len(self.cache),
        }


def batch_load_users(user_ids):
    """Batches lookup of multiple users by id in a single SQL query."""
    if not user_ids:
        return {}

    db = get_db()
    placeholders = ",".join(["?"] * len(user_ids))
    query = f"""
        SELECT id, username, email, role, bio, created_at, updated_at
        FROM users
        WHERE id IN ({placeholders})
    """  # nosec B608
    cursor = db.execute(query, user_ids)
    user_map = {}
    for row in cursor.fetchall():
        data = dict(row)
        user_map[data["id"]] = data
    return user_map


def batch_load_projects(project_ids):
    """Batches lookup of multiple projects by id in a single query."""
    if not project_ids:
        return {}

    db = get_db()
    placeholders = ",".join(["?"] * len(project_ids))
    query = f"""
        SELECT p.id, p.title, p.description, p.status, p.stars_count,
               p.owner_id, p.created_at, p.updated_at,
               COALESCE(AVG(r.rating), 0.0) AS avg_rating,
               COUNT(r.id) AS rev_count
        FROM projects p
        LEFT JOIN reviews r ON r.project_id = p.id
        WHERE p.id IN ({placeholders})
        GROUP BY p.id
    """  # nosec B608
    cursor = db.execute(query, project_ids)
    proj_map = {}
    for row in cursor.fetchall():
        item = dict(row)
        item["average_rating"] = (
            round(item["avg_rating"], 2) if item["rev_count"] > 0 else None
        )
        item["review_count"] = item["rev_count"]
        del item["avg_rating"]
        del item["rev_count"]
        proj_map[item["id"]] = item
    return proj_map


def batch_load_technologies_for_projects(project_ids):
    """Batches loading of tagged technologies grouped by project id."""
    if not project_ids:
        return {}

    db = get_db()
    placeholders = ",".join(["?"] * len(project_ids))
    query = f"""
        SELECT pt.project_id, t.id, t.name, t.category, t.icon_slug
        FROM technologies t
        INNER JOIN project_technologies pt ON pt.technology_id = t.id
        WHERE pt.project_id IN ({placeholders})
        ORDER BY t.name ASC
    """  # nosec B608
    cursor = db.execute(query, project_ids)
    tech_map = defaultdict(list)
    for row in cursor.fetchall():
        data = dict(row)
        pid = data.pop("project_id")
        tech_map[pid].append(data)
    return tech_map


def batch_load_reviews_for_projects(project_ids):
    """Batches loading of peer reviews grouped by project id."""
    if not project_ids:
        return {}

    db = get_db()
    placeholders = ",".join(["?"] * len(project_ids))
    query = f"""
        SELECT id, project_id, author_id, rating, comment, created_at
        FROM reviews
        WHERE project_id IN ({placeholders})
        ORDER BY id DESC
    """  # nosec B608
    cursor = db.execute(query, project_ids)
    rev_map = defaultdict(list)
    for row in cursor.fetchall():
        data = dict(row)
        rev_map[data["project_id"]].append(data)
    return rev_map


def batch_load_projects_for_owners(owner_ids):
    """Batches loading of projects owned by specified developer ids."""
    if not owner_ids:
        return {}

    db = get_db()
    placeholders = ",".join(["?"] * len(owner_ids))
    query = f"""
        SELECT p.id, p.title, p.description, p.status, p.stars_count,
               p.owner_id, p.created_at, p.updated_at,
               COALESCE(AVG(r.rating), 0.0) AS avg_rating,
               COUNT(r.id) AS rev_count
        FROM projects p
        LEFT JOIN reviews r ON r.project_id = p.id
        WHERE p.owner_id IN ({placeholders})
        GROUP BY p.id
        ORDER BY p.id DESC
    """  # nosec B608
    cursor = db.execute(query, owner_ids)
    owner_map = defaultdict(list)
    for row in cursor.fetchall():
        item = dict(row)
        item["average_rating"] = (
            round(item["avg_rating"], 2) if item["rev_count"] > 0 else None
        )
        item["review_count"] = item["rev_count"]
        del item["avg_rating"]
        del item["rev_count"]
        owner_map[item["owner_id"]].append(item)
    return owner_map


def batch_load_reviews_for_authors(author_ids):
    """Batches loading of reviews written by specified author ids."""
    if not author_ids:
        return {}

    db = get_db()
    placeholders = ",".join(["?"] * len(author_ids))
    query = f"""
        SELECT id, project_id, author_id, rating, comment, created_at
        FROM reviews
        WHERE author_id IN ({placeholders})
        ORDER BY id DESC
    """  # nosec B608
    cursor = db.execute(query, author_ids)
    author_map = defaultdict(list)
    for row in cursor.fetchall():
        data = dict(row)
        author_map[data["author_id"]].append(data)
    return author_map


class DataLoaderRegistry:
    """Registry container encapsulating request-scoped DataLoader instances."""

    def __init__(self):
        self.user_loader = DataLoader(batch_load_users)
        self.project_loader = DataLoader(batch_load_projects)
        self.project_technologies_loader = DataLoader(
            batch_load_technologies_for_projects
        )
        self.project_reviews_loader = DataLoader(batch_load_reviews_for_projects)
        self.owner_projects_loader = DataLoader(batch_load_projects_for_owners)
        self.author_reviews_loader = DataLoader(batch_load_reviews_for_authors)

    def get_stats(self):
        """Collects combined metrics across all loaders in the registry."""
        return {
            "users": self.user_loader.get_stats(),
            "projects": self.project_loader.get_stats(),
            "technologies": self.project_technologies_loader.get_stats(),
            "project_reviews": self.project_reviews_loader.get_stats(),
            "owner_projects": self.owner_projects_loader.get_stats(),
            "author_reviews": self.author_reviews_loader.get_stats(),
        }


def create_dataloaders():
    """Factory creating a new DataLoaderRegistry for a request context."""
    return DataLoaderRegistry()
