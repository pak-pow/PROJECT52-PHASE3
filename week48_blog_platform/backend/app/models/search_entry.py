"""Search index data access object for BM25 full-text indexing."""

import sqlite3
from typing import Any, Dict, List, Tuple


class SearchIndexDAO:
    """Data Access Object for inverted index terms and statistics."""

    @staticmethod
    def insert_terms(
        conn: sqlite3.Connection,
        post_id: int,
        field: str,
        term_frequencies: Dict[str, int],
        doc_length: int,
    ) -> None:
        """Insert indexed terms for a specific post and field."""
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM search_index WHERE post_id = ? AND field = ?;",
            (post_id, field),
        )
        for term, tf in term_frequencies.items():
            cursor.execute(
                """
                INSERT INTO search_index (
                    post_id, field, term, term_frequency, doc_length
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (post_id, field, term, tf, doc_length),
            )
        conn.commit()

    @staticmethod
    def delete_by_post(conn: sqlite3.Connection, post_id: int) -> int:
        """Purge all index entries for a given post."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM search_index WHERE post_id = ?;", (post_id,))
        conn.commit()
        return cursor.rowcount

    @staticmethod
    def get_terms_for_post(
        conn: sqlite3.Connection, post_id: int
    ) -> List[Dict[str, Any]]:
        """Retrieve all term records for a post."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, post_id, field, term, term_frequency, doc_length
            FROM search_index WHERE post_id = ?;
            """,
            (post_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def get_post_matches_for_term(
        conn: sqlite3.Connection, term: str
    ) -> List[Tuple[int, str, int, int]]:
        """Retrieve matching (post_id, field, tf, doc_length) for a term."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT post_id, field, term_frequency, doc_length
            FROM search_index WHERE term = ?;
            """,
            (term,),
        )
        return cursor.fetchall()

    @staticmethod
    def get_total_indexed_posts(conn: sqlite3.Connection) -> int:
        """Count total distinct posts registered in the search index."""
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT post_id) FROM search_index;")
        return cursor.fetchone()[0]

    @staticmethod
    def get_avg_doc_length(conn: sqlite3.Connection, field: str = "body") -> float:
        """Calculate average document length across indexed posts for field."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT AVG(doc_length) FROM (
                SELECT DISTINCT post_id, doc_length
                FROM search_index
                WHERE field = ?
            );
            """,
            (field,),
        )
        res = cursor.fetchone()[0]
        return float(res) if res is not None else 1.0

    @staticmethod
    def autocomplete_terms(
        conn: sqlite3.Connection, prefix: str, limit: int = 10
    ) -> List[str]:
        """Find matching indexed terms beginning with the prefix string."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT term FROM search_index
            WHERE term LIKE ?
            ORDER BY term ASC
            LIMIT ?;
            """,
            (f"{prefix}%", limit),
        )
        return [r[0] for r in cursor.fetchall()]
