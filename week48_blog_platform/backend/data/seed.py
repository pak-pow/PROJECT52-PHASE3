"""Seed data and idempotent initialization pipeline for PulsePress."""

import json
import sqlite3
from typing import Any, Dict, List

from werkzeug.security import generate_password_hash

DEFAULT_USERS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "username": "admin",
        "email": "admin@pulsepress.dev",
        "password": "AdminPassword123!",
        "display_name": "System Administrator",
        "bio": "Lead administrator for PulsePress blog engine.",
        "avatar_url": "https://api.dicebear.com/7.x/bottts/svg?seed=admin",
        "role": "admin",
    },
    {
        "id": 2,
        "username": "sarah_dev",
        "email": "sarah@pulsepress.dev",
        "password": "AuthorPassword123!",
        "display_name": "Sarah Chen",
        "bio": "Staff Infrastructure & Search Engineer writing on Python & Systems.",
        "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=sarah",
        "role": "author",
    },
]

DEFAULT_TAGS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "name": "Python",
        "slug": "python",
        "description": "Modern Python programming, concurrency, and architecture.",
    },
    {
        "id": 2,
        "name": "Web Development",
        "slug": "web-development",
        "description": "Full-stack web application development, APIs, and browsers.",
    },
    {
        "id": 3,
        "name": "SEO",
        "slug": "seo",
        "description": "Technical search engine optimization, metadata, and indexing.",
    },
    {
        "id": 4,
        "name": "Machine Learning",
        "slug": "machine-learning",
        "description": "Inference gateways, embeddings, ranking, and models.",
    },
    {
        "id": 5,
        "name": "Architecture",
        "slug": "architecture",
        "description": "Software architecture patterns, distributed systems, and WAL.",
    },
    {
        "id": 6,
        "name": "DevOps",
        "slug": "devops",
        "description": "CI/CD pipelines, containerization, and platform engineering.",
    },
]

DEFAULT_POSTS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "author_id": 2,
        "slug": "building-a-production-grade-blog-engine-with-advanced-seo",
        "title": "Building a Production-Grade Blog Engine with Advanced SEO",
        "excerpt": (
            "Explore how to design an enterprise blog platform from the ground up, "
            "incorporating Open Graph, JSON-LD schemas, and dynamic XML sitemaps."
        ),
        "body_markdown": """# Building a Production-Grade Blog Engine with Advanced SEO

Modern web discovery demands more than just rendering static HTML. To achieve peak
organic discoverability, a modern blog platform must deliver structured metadata,
canonical links, and crawlable site indices.

## The Core Foundations of Technical SEO

Technical SEO encompasses several key pillars:
1. Canonical URL resolution to eliminate duplicate indexing penalties.
2. Structured JSON-LD metadata for Google Rich Snippets.
3. Open Graph and Twitter Card protocol headers for rich social media cards.

```python
def generate_canonical_url(base_url: str, slug: str) -> str:
    return f"{base_url.rstrip('/')}/posts/{slug}"
```

## Automating Sitemaps and Feeds

An automated XML sitemap provides crawlers with instant knowledge of new posts.
Coupled with RSS 2.0 syndication, readers and indexers stay synchronized.
""",
        "body_html": "",
        "featured_image": (
            "https://images.unsplash.com/photo-1499750310107-5fef28a66643"
        ),
        "status": "published",
        "reading_time_minutes": 3,
        "toc_json": json.dumps(
            [
                {
                    "level": 2,
                    "title": "The Core Foundations of Technical SEO",
                    "anchor": "the-core-foundations-of-technical-seo",
                },
                {
                    "level": 2,
                    "title": "Automating Sitemaps and Feeds",
                    "anchor": "automating-sitemaps-and-feeds",
                },
            ]
        ),
        "published_at": "2026-11-20 10:00:00",
        "tags": [1, 2, 3],
    },
    {
        "id": 2,
        "author_id": 2,
        "slug": "demystifying-bm25-search-ranking-with-python",
        "title": "Demystifying BM25 Search Ranking with Python",
        "excerpt": (
            "A deep dive into the mathematical mechanics of BM25 probabilistic "
            "relevance ranking and how to build an inverted index inside SQLite."
        ),
        "body_markdown": """# Demystifying BM25 Search Ranking with Python

Full-text search in production often starts with BM25 (Best Matching 25), the
gold-standard probabilistic scoring function used across Lucene and Elasticsearch.

## Understanding the BM25 Formula

The core equation balances term frequency with document length penalization:

```python
def bm25_score(tf: int, doc_len: int, avg_doc_len: float, idf: float,
               k1: float = 1.5, b: float = 0.75) -> float:
    numerator = tf * (k1 + 1)
    denominator = tf + k1 * (1 - b + b * (doc_len / avg_doc_len))
    return idf * (numerator / denominator)
```

## Constructing the Inverted Index

By breaking text into normalized token stems and storing post frequency weights,
we can perform sub-millisecond keyword lookups over thousands of articles.
""",
        "body_html": "",
        "featured_image": (
            "https://images.unsplash.com/photo-1518770660439-4636190af475"
        ),
        "status": "published",
        "reading_time_minutes": 4,
        "toc_json": json.dumps(
            [
                {
                    "level": 2,
                    "title": "Understanding the BM25 Formula",
                    "anchor": "understanding-the-bm25-formula",
                },
                {
                    "level": 2,
                    "title": "Constructing the Inverted Index",
                    "anchor": "constructing-the-inverted-index",
                },
            ]
        ),
        "published_at": "2026-11-21 14:30:00",
        "tags": [1, 4, 5],
    },
    {
        "id": 3,
        "author_id": 1,
        "slug": "clean-architecture-in-flask-monolith-to-microservices",
        "title": "Clean Architecture in Flask: From Monolith to Microservices",
        "excerpt": (
            "Learn how decoupling domain entities, repository DAOs, and service "
            "layers allows monolithic web applications to scale gracefully."
        ),
        "body_markdown": (
            "# Clean Architecture in Flask: Monolith to Microservices\n\n"
            "Well-structured Flask applications follow clean boundaries\n"
            "between transport, business logic, and persistent storage mechanisms.\n\n"
            "## Layer Separation and Boundaries\n\n"
            "- Transport layer: HTTP blueprints, routing, serialization.\n"
            "- Service layer: Domain rules, validation, workflow coordination.\n"
            "- Data access layer: Isolated DAOs executing SQLite WAL transactions.\n\n"
            "```python\n"
            "class PostService:\n"
            "    def __init__(self, post_dao: PostDAO, tag_dao: TagDAO):\n"
            "        self.post_dao = post_dao\n"
            "        self.tag_dao = tag_dao\n"
            "```\n\n"
            "By keeping services decoupled from SQL execution, testing is effortless.\n"
        ),
        "body_html": "",
        "featured_image": (
            "https://images.unsplash.com/photo-1451187580459-43490279c0fa"
        ),
        "status": "published",
        "reading_time_minutes": 3,
        "toc_json": json.dumps(
            [
                {
                    "level": 2,
                    "title": "Layer Separation and Boundaries",
                    "anchor": "layer-separation-and-boundaries",
                }
            ]
        ),
        "published_at": "2026-11-22 09:15:00",
        "tags": [1, 2, 5, 6],
    },
]

DEFAULT_COMMENTS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "post_id": 1,
        "parent_id": None,
        "author_name": "Marcus Vance",
        "author_email": "marcus@example.com",
        "author_ip_hash": (
            "e3b0c44298fc1c149afbf4c8996fb924" "27ae41e4649b934ca495991b7852b855"
        ),
        "body": "Fantastic breakdown on Open Graph metadata. Very actionable!",
        "status": "approved",
    },
    {
        "id": 2,
        "post_id": 1,
        "parent_id": 1,
        "author_name": "Sarah Chen",
        "author_email": "sarah@pulsepress.dev",
        "author_ip_hash": (
            "a1b2c3d4e5f60718293a4b5c6d7e8f90" "123456789abcdef0123456789abcdef0"
        ),
        "body": "Thanks Marcus! In Day 3 we expand on schema.org JSON-LD generation.",
        "status": "approved",
    },
    {
        "id": 3,
        "post_id": 2,
        "parent_id": None,
        "author_name": "Alex Rivera",
        "author_email": "alex@example.org",
        "author_ip_hash": (
            "11223344556677889900aabbccddeeff" "11223344556677889900aabbccddeeff"
        ),
        "body": "BM25 with SQLite is shockingly fast. Looking forward to Day 2!",
        "status": "approved",
    },
]


def seed_database(conn: sqlite3.Connection) -> None:
    """Idempotently seed users, tags, posts, post-tag mappings, and comments."""
    cursor = conn.cursor()

    # 1. Seed Users
    for u in DEFAULT_USERS:
        pwd_hash = generate_password_hash(u["password"])
        cursor.execute(
            """
            INSERT OR REPLACE INTO users (
                id, username, email, password_hash, display_name, bio, avatar_url, role
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                u["id"],
                u["username"],
                u["email"],
                pwd_hash,
                u["display_name"],
                u["bio"],
                u["avatar_url"],
                u["role"],
            ),
        )

    # 2. Seed Tags
    for t in DEFAULT_TAGS:
        cursor.execute(
            """
            INSERT OR REPLACE INTO tags (id, name, slug, description, post_count)
            VALUES (?, ?, ?, ?, ?);
            """,
            (t["id"], t["name"], t["slug"], t["description"], 0),
        )

    # 3. Seed Posts and Post-Tag Junction
    from app.content.markdown_engine import MarkdownEngine
    from app.services.search_engine import SearchEngine

    md_engine = MarkdownEngine()
    search_engine = SearchEngine()

    tag_id_to_name = {t["id"]: t["name"] for t in DEFAULT_TAGS}

    for p in DEFAULT_POSTS:
        # Pre-render Markdown content
        processed = md_engine.process(p["body_markdown"])
        body_html = processed["body_html"]
        toc_json = p.get("toc_json") or processed["toc_json"]
        reading_time = processed["reading_time_minutes"]
        excerpt = p.get("excerpt") or processed["excerpt"]

        cursor.execute(
            """
            INSERT OR REPLACE INTO posts (
                id, author_id, slug, title, body_markdown, body_html, excerpt,
                featured_image, status, reading_time_minutes, toc_json, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                p["id"],
                p["author_id"],
                p["slug"],
                p["title"],
                p["body_markdown"],
                body_html,
                excerpt,
                p["featured_image"],
                p["status"],
                reading_time,
                toc_json,
                p["published_at"],
            ),
        )

        # Clear existing tags for this post before inserting
        cursor.execute("DELETE FROM post_tags WHERE post_id = ?;", (p["id"],))
        tag_names: List[str] = []
        for tag_id in p.get("tags", []):
            cursor.execute(
                """
                INSERT OR IGNORE INTO post_tags (post_id, tag_id)
                VALUES (?, ?);
                """,
                (p["id"], tag_id),
            )
            if tag_id in tag_id_to_name:
                tag_names.append(tag_id_to_name[tag_id])

        # Index post terms into inverted search index
        search_engine.index_post(
            conn, p["id"], p["title"], p["body_markdown"], tag_names
        )

    # 4. Update Tag Post Counts
    cursor.execute("""
        UPDATE tags SET post_count = (
            SELECT COUNT(*) FROM post_tags WHERE post_tags.tag_id = tags.id
        );
        """)

    # 5. Seed Comments
    for c in DEFAULT_COMMENTS:
        cursor.execute(
            """
            INSERT OR REPLACE INTO comments (
                id, post_id, parent_id, author_name, author_email,
                author_ip_hash, body, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                c["id"],
                c["post_id"],
                c["parent_id"],
                c["author_name"],
                c["author_email"],
                c["author_ip_hash"],
                c["body"],
                c["status"],
            ),
        )

    conn.commit()
