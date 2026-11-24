"""Tests for Markdown rendering engine, Pygments syntax highlighting, and TOC."""

from app.content.markdown_engine import MarkdownEngine


def test_render_markdown_basic_formatting():
    """Verify standard Markdown transforms to HTML with tables and lists."""
    engine = MarkdownEngine()
    md = """# Title Heading

This is **bold** and *italic* text with [a link](https://example.com).

> Blockquote insight

| Col A | Col B |
| :--- | :--- |
| Val 1 | Val 2 |
"""
    html = engine.render(md)
    assert '<h1 id="title-heading">Title Heading</h1>' in html
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert 'href="https://example.com"' in html
    assert "<blockquote>" in html
    assert "<table>" in html
    assert "Col A" in html
    assert "Col B" in html


def test_render_fenced_code_syntax_highlighting():
    """Verify fenced code blocks produce Pygments highlighted HTML."""
    engine = MarkdownEngine()
    md = """```python
def calculate_area(radius: float) -> float:
    return 3.14159 * (radius ** 2)
```"""
    html = engine.render(md)
    assert 'class="highlight"' in html
    assert "<pre>" in html
    assert '<span class="k">def</span>' in html
    assert "calculate_area" in html


def test_extract_toc_hierarchy():
    """Verify table of contents extracts structured headings with anchors."""
    engine = MarkdownEngine()
    md = """# Architecture Overview
Intro text.

## Database WAL Mode
Details about SQLite WAL.

### Concurrency Guarantees
Concurrent readers and writers.

## Search Indexing
Inverted index details.
"""
    toc = engine.extract_toc(md)
    assert len(toc) == 4
    assert toc[0]["title"] == "Architecture Overview"
    assert toc[0]["level"] == 1
    assert toc[0]["anchor"] == "architecture-overview"

    assert toc[1]["title"] == "Database WAL Mode"
    assert toc[1]["level"] == 2
    assert toc[1]["anchor"] == "database-wal-mode"

    assert toc[2]["title"] == "Concurrency Guarantees"
    assert toc[2]["level"] == 3
    assert toc[2]["anchor"] == "concurrency-guarantees"

    assert toc[3]["title"] == "Search Indexing"
    assert toc[3]["level"] == 2
    assert toc[3]["anchor"] == "search-indexing"


def test_estimate_reading_time():
    """Verify reading time accounts for prose words and code block density."""
    engine = MarkdownEngine(wpm=200)

    # 100 words prose -> 1 min
    short_prose = "word " * 100
    assert engine.estimate_reading_time(short_prose) == 1

    # 450 words prose -> ceil(450/200) = 3 min
    medium_prose = "word " * 450
    assert engine.estimate_reading_time(medium_prose) == 3

    # Prose with 40-line code block:
    # 40 lines * 2.5 = 100 eq words + 150 words = 250 words -> 2 min
    code_lines = "\n".join(f"line_{i} = {i}" for i in range(40))
    code_post = "word " * 150 + f"\n```python\n{code_lines}\n```"
    assert engine.estimate_reading_time(code_post) == 2


def test_extract_excerpt():
    """Verify clean excerpt extraction without headers, code, or links."""
    engine = MarkdownEngine()
    md = """# Main Header

![Banner](https://example.com/banner.png)

```python
import sys
```

This is the primary summary paragraph explaining **distributed systems** and
[relational integrity](https://example.com/link) across nodes.

Second paragraph that should not be in the excerpt.
"""
    excerpt = engine.extract_excerpt(md, max_chars=120)
    assert "#" not in excerpt
    assert "https://example.com" not in excerpt
    assert "import sys" not in excerpt
    assert "primary summary paragraph" in excerpt
    assert "distributed systems" in excerpt
    assert "Second paragraph" not in excerpt


def test_process_bundle_output():
    """Verify process returns consolidated dictionary of all rendered fields."""
    engine = MarkdownEngine()
    md = """# Microservices in Flask

Explore how to decouple domains into services.

## Service Boundaries
Define RPC interfaces.
"""
    result = engine.process(md)
    assert "body_html" in result
    assert "toc" in result
    assert "toc_json" in result
    assert "reading_time_minutes" in result
    assert "excerpt" in result
    assert result["reading_time_minutes"] >= 1
    assert len(result["toc"]) == 2
    assert "Microservices in Flask" in result["body_html"]


def test_empty_markdown_graceful_handling():
    """Verify empty input strings return neutral fallback values."""
    engine = MarkdownEngine()
    assert engine.render("") == ""
    assert engine.extract_toc("") == []
    assert engine.estimate_reading_time("") == 1
    assert engine.extract_excerpt("") == ""

    bundle = engine.process("")
    assert bundle["body_html"] == ""
    assert bundle["toc"] == []
    assert bundle["reading_time_minutes"] == 1
    assert bundle["excerpt"] == ""
