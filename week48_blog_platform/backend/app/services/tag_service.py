"""Tag taxonomy, tag cloud weighting, and Jaccard related post service."""

import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.post import PostDAO
from app.models.tag import TagDAO
from app.services.slug_service import generate_unique_slug_for_db


class TagService:
    """Service for managing tags, tag clouds, and tag-based post recommendations."""

    @staticmethod
    def create_tag(
        conn: sqlite3.Connection,
        name: str,
        description: str = "",
        slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a tag with a collision-safe unique slug."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Tag name cannot be empty.")

        # Check case-insensitive duplicate name
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM tags WHERE LOWER(name) = LOWER(?);",
            (clean_name,),
        )
        if cursor.fetchone():
            raise ValueError(f"Tag '{clean_name}' already exists.")

        unique_slug = slug or generate_unique_slug_for_db(conn, "tags", clean_name)
        return TagDAO.create(
            conn, name=clean_name, slug=unique_slug, description=description.strip()
        )

    @staticmethod
    def get_or_create_tags(
        conn: sqlite3.Connection, tag_names: List[str]
    ) -> List[Dict[str, Any]]:
        """Resolve tag names to tag records, creating missing ones automatically."""
        resolved: List[Dict[str, Any]] = []
        seen_ids: Set[int] = set()
        cursor = conn.cursor()

        for raw_name in tag_names:
            clean_name = raw_name.strip()
            if not clean_name:
                continue

            cursor.execute(
                "SELECT id FROM tags WHERE LOWER(name) = LOWER(?);",
                (clean_name,),
            )
            row = cursor.fetchone()
            if row:
                tag = TagDAO.get_by_id(conn, row["id"])
            else:
                tag = TagService.create_tag(conn, clean_name)

            if tag and tag["id"] not in seen_ids:
                seen_ids.add(tag["id"])
                resolved.append(tag)

        return resolved

    @staticmethod
    def list_tags(
        conn: sqlite3.Connection, order_by: str = "count"
    ) -> List[Dict[str, Any]]:
        """List all tags ordered by post count or alphabetically."""
        return TagDAO.list_all(conn, order_by=order_by)

    @staticmethod
    def get_tag_with_posts(
        conn: sqlite3.Connection,
        slug: str,
        page: int = 1,
        page_size: int = 10,
    ) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]], int]]:
        """Fetch a tag by slug alongside its paginated published posts."""
        tag = TagDAO.get_by_slug(conn, slug)
        if not tag:
            return None

        posts, total = PostDAO.list_posts(
            conn,
            status="published",
            tag_slug=slug,
            page=page,
            page_size=page_size,
        )
        return tag, posts, total

    @staticmethod
    def generate_tag_cloud(
        conn: sqlite3.Connection,
        min_size: float = 0.85,
        max_size: float = 2.0,
        include_empty: bool = False,
    ) -> List[Dict[str, Any]]:
        """Build a tag cloud with normalized weights and font-size scaling."""
        all_tags = TagDAO.list_all(conn, order_by="name")
        if not include_empty:
            tags = [t for t in all_tags if t.get("post_count", 0) > 0]
        else:
            tags = all_tags

        if not tags:
            return []

        counts = [t.get("post_count", 0) for t in tags]
        min_count = min(counts)
        max_count = max(counts)
        spread = max_count - min_count

        cloud: List[Dict[str, Any]] = []
        for tag in tags:
            count = tag.get("post_count", 0)
            if spread == 0:
                weight = 1.0 if count > 0 else 0.0
            else:
                weight = (count - min_count) / spread

            font_size = round(min_size + weight * (max_size - min_size), 2)
            enriched = dict(tag)
            enriched["weight"] = round(weight, 4)
            enriched["font_size"] = font_size
            cloud.append(enriched)

        return cloud

    @staticmethod
    def jaccard_similarity(set_a: Set[int], set_b: Set[int]) -> float:
        """Compute Jaccard similarity coefficient J(A, B) = |A & B| / |A | B|."""
        if not set_a and not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        if union == 0:
            return 0.0
        return intersection / union

    @staticmethod
    def find_related_posts(
        conn: sqlite3.Connection, post_id: int, limit: int = 4
    ) -> List[Dict[str, Any]]:
        """Find related published posts ranked by Jaccard tag similarity."""
        target_tags = TagDAO.get_tags_for_post(conn, post_id)
        target_tag_ids = {t["id"] for t in target_tags}
        if not target_tag_ids:
            return []

        candidates, _ = PostDAO.list_posts(conn, status="published", page_size=500)
        scored: List[Tuple[float, str, Dict[str, Any]]] = []

        for candidate in candidates:
            if candidate["id"] == post_id:
                continue

            cand_tag_ids = {t["id"] for t in candidate.get("tags", [])}
            similarity = TagService.jaccard_similarity(target_tag_ids, cand_tag_ids)
            if similarity > 0.0:
                enriched = dict(candidate)
                enriched["similarity_score"] = round(similarity, 4)
                pub_key = str(candidate.get("published_at") or "")
                scored.append((similarity, pub_key, enriched))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[:limit]]
