"""BM25 Full-Text Search Engine with Inverted Index and Multi-Field Weighting."""

import collections
import math
import re
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Set

from app.models.search_entry import SearchIndexDAO
from app.services.stemmer import tokenize


class SearchEngine:
    """Probabilistic BM25 Search Engine with field-weighted relevance scoring."""

    DEFAULT_WEIGHTS = {
        "title": 3.0,
        "tag": 2.0,
        "body": 1.0,
    }

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        weights: Optional[Dict[str, float]] = None,
    ):
        """Initialize engine with BM25 hyperparameters and field weights."""
        self.k1 = k1
        self.b = b
        self.weights = weights or self.DEFAULT_WEIGHTS

    def index_post(
        self,
        conn: sqlite3.Connection,
        post_id: int,
        title: str,
        body_markdown: str,
        tag_names: Sequence[str],
    ) -> None:
        """Tokenize post fields and populate inverted index entries in SQLite."""
        # Index Title
        title_tokens = tokenize(title)
        title_len = max(1, len(title_tokens))
        title_tf = collections.Counter(title_tokens)
        SearchIndexDAO.insert_terms(conn, post_id, "title", dict(title_tf), title_len)

        # Index Body
        body_tokens = tokenize(body_markdown)
        body_len = max(1, len(body_tokens))
        body_tf = collections.Counter(body_tokens)
        SearchIndexDAO.insert_terms(conn, post_id, "body", dict(body_tf), body_len)

        # Index Tags
        tags_text = " ".join(tag_names)
        tag_tokens = tokenize(tags_text)
        tag_len = max(1, len(tag_tokens))
        tag_tf = collections.Counter(tag_tokens)
        SearchIndexDAO.insert_terms(conn, post_id, "tag", dict(tag_tf), tag_len)

    def remove_post_from_index(self, conn: sqlite3.Connection, post_id: int) -> int:
        """Purge all index entries associated with a post."""
        return SearchIndexDAO.delete_by_post(conn, post_id)

    def rebuild_index_all(self, conn: sqlite3.Connection) -> int:
        """Index all currently published posts in the database."""
        from app.models.post import PostDAO

        posts, _ = PostDAO.list_posts(conn, status=None, page=1, page_size=1000)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM search_index;")
        conn.commit()

        indexed_count = 0
        for summary in posts:
            p = PostDAO.get_by_id(conn, summary["id"])
            if not p:
                continue
            tag_names = [t["name"] for t in p.get("tags", [])]
            self.index_post(
                conn,
                p["id"],
                p["title"],
                p.get("body_markdown", ""),
                tag_names,
            )
            indexed_count += 1

        return indexed_count

    def compute_idf(self, total_docs: int, matching_docs: int) -> float:
        """Compute Robertson-Spärck Jones IDF with positive floor."""
        numerator = total_docs - matching_docs + 0.5
        denominator = matching_docs + 0.5
        return math.log(max(0.0, numerator / denominator) + 1.0)

    def search(
        self,
        conn: sqlite3.Connection,
        query: str,
        limit: int = 10,
        offset: int = 0,
        published_only: bool = True,
    ) -> Dict[str, Any]:
        """Execute BM25 search across indexed fields with relevance ranking."""
        query_terms = list(dict.fromkeys(tokenize(query)))
        if not query_terms:
            return {
                "results": [],
                "total": 0,
                "query": query,
                "terms": [],
            }

        # Gather field document length statistics
        fields = ("title", "tag", "body")
        avg_lengths = {
            f: SearchIndexDAO.get_avg_doc_length(conn, field=f) for f in fields
        }

        # Query all candidate posts matching any query term
        placeholders = ",".join("?" for _ in query_terms)
        sql = f"""
            SELECT post_id, field, term, term_frequency, doc_length
            FROM search_index
            WHERE term IN ({placeholders});
        """  # nosec B608

        cursor = conn.cursor()
        cursor.execute(sql, query_terms)
        rows = cursor.fetchall()

        if not rows:
            return {
                "results": [],
                "total": 0,
                "query": query,
                "terms": query_terms,
            }

        # Precompute document frequencies per (field, term)
        term_doc_counts: Dict[str, Dict[str, Set[int]]] = {
            f: collections.defaultdict(set) for f in fields
        }
        post_field_records: Dict[int, List[Any]] = collections.defaultdict(list)

        for row in rows:
            pid = row["post_id"]
            field = row["field"]
            term = row["term"]
            term_doc_counts[field][term].add(pid)
            post_field_records[pid].append(row)

        # Total distinct posts in the index
        total_docs = max(1, SearchIndexDAO.get_total_indexed_posts(conn))

        # Calculate BM25 scores per candidate post
        post_scores: Dict[int, float] = collections.defaultdict(float)
        post_matched_terms: Dict[int, Set[str]] = collections.defaultdict(set)

        for pid, records in post_field_records.items():
            for r in records:
                field = r["field"]
                term = r["term"]
                tf = r["term_frequency"]
                doc_len = r["doc_length"]

                post_matched_terms[pid].add(term)

                field_weight = self.weights.get(field, 1.0)
                n_t = len(term_doc_counts[field][term])
                idf = self.compute_idf(total_docs, n_t)
                avgdl = avg_lengths.get(field, 1.0) or 1.0

                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / avgdl))

                bm25_term = idf * (numerator / denominator)
                post_scores[pid] += field_weight * bm25_term

        # Filter published status if requested
        ranked_pids = sorted(
            post_scores.keys(), key=lambda pid: post_scores[pid], reverse=True
        )

        from app.models.post import PostDAO

        valid_results: List[Dict[str, Any]] = []
        for pid in ranked_pids:
            post = PostDAO.get_by_id(conn, pid)
            if not post:
                continue
            if published_only and post.get("status") != "published":
                continue

            snippet = self.extract_snippet(post.get("body_markdown", ""), query_terms)

            valid_results.append(
                {
                    "post": post,
                    "score": round(post_scores[pid], 4),
                    "snippet": snippet,
                    "matched_terms": sorted(post_matched_terms[pid]),
                }
            )

        total_matching = len(valid_results)
        paginated_results = valid_results[offset : offset + limit]

        return {
            "results": paginated_results,
            "total": total_matching,
            "query": query,
            "terms": query_terms,
            "page": (offset // limit) + 1 if limit > 0 else 1,
            "page_size": limit,
        }

    def extract_snippet(
        self, body_text: str, query_terms: Sequence[str], max_chars: int = 160
    ) -> str:
        """Extract a highlighted text snippet around the first matching term."""
        if not body_text:
            return ""

        # Remove code fences and markdown hashes
        clean = re.sub(r"```[\s\S]*?```", " ", body_text)
        clean = re.sub(r"^#+\s+", "", clean, flags=re.MULTILINE)
        clean = " ".join(clean.split())

        lower_clean = clean.lower()
        earliest_pos = len(clean)

        for term in query_terms:
            pos = lower_clean.find(term)
            if 0 <= pos < earliest_pos:
                earliest_pos = pos

        if earliest_pos == len(clean):
            # No term found in plain text (could be in title or tag)
            snippet = clean[:max_chars].rstrip()
            return snippet + "..." if len(clean) > max_chars else snippet

        # Center the window around earliest_pos
        half = max_chars // 2
        start = max(0, earliest_pos - half)
        end = min(len(clean), start + max_chars)

        # Adjust start and end to word boundaries
        if start > 0:
            next_space = clean.find(" ", start)
            if next_space != -1 and next_space < start + 20:
                start = next_space + 1

        if end < len(clean):
            last_space = clean.rfind(" ", start, end)
            if last_space != -1 and last_space > end - 20:
                end = last_space

        raw_snippet = clean[start:end].strip()
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(clean) else ""

        # Highlight query terms
        pattern = r"\b(" + "|".join(re.escape(t) for t in query_terms) + r")\b"
        highlighted = re.sub(
            pattern,
            r"<mark>\1</mark>",
            raw_snippet,
            flags=re.IGNORECASE,
        )

        return f"{prefix}{highlighted}{suffix}"

    def autocomplete(
        self, conn: sqlite3.Connection, prefix: str, limit: int = 10
    ) -> List[str]:
        """Find matching indexed vocabulary terms matching prefix."""
        clean_prefix = prefix.strip().lower()
        if not clean_prefix:
            return []
        return SearchIndexDAO.autocomplete_terms(conn, clean_prefix, limit=limit)
