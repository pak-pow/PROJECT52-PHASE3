"""Tests for BM25 search engine, inverted indexing, and Porter stemmer."""

from app.models.post import PostDAO
from app.services.search_engine import SearchEngine
from app.services.stemmer import STEMMER, tokenize


def test_stemmer_classical_rules():
    """Verify core morphological stemming rules in PorterStemmer."""
    assert STEMMER.stem("caresses") == "caress"
    assert STEMMER.stem("ponies") == "poni"
    assert STEMMER.stem("ties") == "ti"
    assert STEMMER.stem("cats") == "cat"
    assert STEMMER.stem("feed") == "feed"
    assert STEMMER.stem("agreed") == "agre"
    assert STEMMER.stem("plastered") == "plaster"
    assert STEMMER.stem("motoring") == "motor"
    assert STEMMER.stem("sing") == "sing"
    assert STEMMER.stem("relational") == "relat"
    assert STEMMER.stem("conditional") == "condit"
    assert STEMMER.stem("rational") == "ration"
    assert STEMMER.stem("sensibility") == "sensibl"
    assert STEMMER.stem("controller") == "control"


def test_tokenizer_filtering_and_stopwords():
    """Verify tokenizer strips punctuation, lowercase, and filters stopwords."""
    text = "The quick brown fox jumps over the lazy dog in Python!"
    tokens = tokenize(text)
    assert "the" not in tokens
    assert "in" not in tokens
    assert "over" not in tokens
    assert "quick" in tokens
    assert "brown" in tokens
    assert "fox" in tokens
    assert "jump" in tokens  # jumps stemmed to jump
    assert "lazi" in tokens  # lazy stemmed to lazi
    assert "dog" in tokens
    assert "python" in tokens


def test_search_engine_index_and_bm25_ranking(empty_db_conn):
    """Verify BM25 ranks documents with higher term relevance higher."""
    # Create two posts
    from app.models.user import UserDAO

    user = UserDAO.create(
        empty_db_conn, "author1", "a1@test.com", "pass123", "Author One"
    )

    p1 = PostDAO.create(
        empty_db_conn,
        author_id=user["id"],
        title="Python Asyncio Event Loops",
        body_markdown="Python asyncio provides event loops for high concurrency.",
        status="published",
    )
    p2 = PostDAO.create(
        empty_db_conn,
        author_id=user["id"],
        title="Database WAL Architecture",
        body_markdown="SQLite WAL mode uses write ahead logging. Mentions python.",
        status="published",
    )

    engine = SearchEngine()
    engine.index_post(
        empty_db_conn,
        p1["id"],
        p1["title"],
        p1["body_markdown"],
        ["Python", "Asyncio"],
    )
    engine.index_post(
        empty_db_conn,
        p2["id"],
        p2["title"],
        p2["body_markdown"],
        ["Database", "SQLite"],
    )

    # Search for asyncio
    res = engine.search(empty_db_conn, "asyncio")
    assert res["total"] == 1
    assert res["results"][0]["post"]["id"] == p1["id"]
    assert res["results"][0]["score"] > 0.0
    assert "asyncio" in res["results"][0]["matched_terms"]

    # Search for python: p1 has python in title + body + tag; p2 only in body
    res_py = engine.search(empty_db_conn, "python")
    assert res_py["total"] == 2
    # p1 should score significantly higher than p2
    assert res_py["results"][0]["post"]["id"] == p1["id"]
    assert res_py["results"][0]["score"] > res_py["results"][1]["score"]


def test_search_engine_multi_field_weighting(empty_db_conn):
    """Verify title matches (weight 3.0) rank above body-only matches."""
    from app.models.user import UserDAO

    user = UserDAO.create(
        empty_db_conn, "author2", "a2@test.com", "pass123", "Author Two"
    )

    # Post A has term in title
    post_a = PostDAO.create(
        empty_db_conn,
        author_id=user["id"],
        title="Microservices Architecture Guide",
        body_markdown="General engineering article discussing patterns.",
        status="published",
    )
    # Post B has term only in body
    post_b = PostDAO.create(
        empty_db_conn,
        author_id=user["id"],
        title="Distributed Computing Principles",
        body_markdown="This guide mentions microservices once.",
        status="published",
    )

    engine = SearchEngine()
    engine.index_post(
        empty_db_conn, post_a["id"], post_a["title"], post_a["body_markdown"], []
    )
    engine.index_post(
        empty_db_conn, post_b["id"], post_b["title"], post_b["body_markdown"], []
    )

    res = engine.search(empty_db_conn, "microservices")
    assert res["total"] == 2
    assert res["results"][0]["post"]["id"] == post_a["id"]
    assert res["results"][0]["score"] > res["results"][1]["score"]


def test_rebuild_index_all_and_purge(db_conn):
    """Verify rebuild_index_all indexes seeded posts and purge cleans up."""
    engine = SearchEngine()
    count = engine.rebuild_index_all(db_conn)
    assert count >= 3

    # Search across seeded posts
    res = engine.search(db_conn, "BM25")
    assert res["total"] >= 1
    assert "bm25" in res["terms"]

    # Remove post 1
    deleted = engine.remove_post_from_index(db_conn, 1)
    assert deleted > 0


def test_search_snippet_highlighting():
    """Verify extract_snippet wraps search terms in <mark> tags."""
    engine = SearchEngine()
    body = (
        "Here is the introduction to our technical architecture. "
        "The distributed event bus processes millions of messages per minute. "
        "Conclusion and recommendations for deployment."
    )
    snippet = engine.extract_snippet(body, ["event", "bus"], max_chars=80)
    assert "<mark>" in snippet
    assert "</mark>" in snippet
    assert "event" in snippet.lower()


def test_autocomplete_term_suggestions(db_conn):
    """Verify autocomplete returns matching indexed term prefixes."""
    engine = SearchEngine()
    engine.rebuild_index_all(db_conn)

    suggestions = engine.autocomplete(db_conn, "py")
    assert any("python" in s for s in suggestions)

    empty_sug = engine.autocomplete(db_conn, "")
    assert empty_sug == []


def test_search_empty_and_no_match(db_conn):
    """Verify empty queries or non-matching terms return structured empty result."""
    engine = SearchEngine()

    empty_res = engine.search(db_conn, "")
    assert empty_res["total"] == 0
    assert empty_res["results"] == []

    no_match_res = engine.search(db_conn, "xylophone_zebra_never_present")
    assert no_match_res["total"] == 0
    assert no_match_res["results"] == []
