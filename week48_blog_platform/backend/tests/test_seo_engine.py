"""Comprehensive unit and integration tests for PulsePress SEO Engine."""

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from app.models.post import PostDAO
from app.seo import RobotsGenerator, RSSFeedGenerator, SEOEngine, SitemapGenerator


def test_canonical_url_resolution() -> None:
    """Verify canonical URL formatting, trailing slashes, and post slug resolution."""
    seo = SEOEngine(base_url="https://pulsepress.example.com")
    assert seo.canonical_url("/") == "https://pulsepress.example.com/"
    assert seo.canonical_url("about") == "https://pulsepress.example.com/about"
    assert (
        seo.canonical_url("/tags/python")
        == "https://pulsepress.example.com/tags/python"
    )
    assert seo.canonical_url("https://external.com/path") == "https://external.com/path"
    assert seo.canonical_url("") == "https://pulsepress.example.com/"
    assert (
        seo.post_canonical_url("modern-blog-engine")
        == "https://pulsepress.example.com/posts/modern-blog-engine"
    )
    assert (
        seo.post_canonical_url("/with-slashes/")
        == "https://pulsepress.example.com/posts/with-slashes"
    )


def test_generate_meta_description() -> None:
    """Verify markdown stripping, word-boundary truncation, and fallbacks."""
    seo = SEOEngine(default_description="Fallback site description.")

    # None or empty fallback
    assert seo.generate_meta_description(None) == "Fallback site description."
    assert seo.generate_meta_description("") == "Fallback site description."
    assert seo.generate_meta_description("   ") == "Fallback site description."

    # Stripping markdown elements
    markdown_text = (
        "# Main Heading\n\n"
        "This is an **important** intro paragraph with a [link](https://example.com) "
        "and `inline code`.\n\n"
        "```python\ndef hello():\n    print('world')\n```\n\n"
        "> Blockquote text here\n\n"
        "- List item 1\n- List item 2"
    )
    desc = seo.generate_meta_description(markdown_text, max_length=160)
    assert "Main Heading" not in desc or "This is an important" in desc
    assert "**" not in desc
    assert "```" not in desc
    assert "def hello" not in desc
    assert "https://example.com" not in desc
    assert "important intro paragraph" in desc

    # Truncation boundary
    long_text = "Word " * 60  # 300 characters
    truncated = seo.generate_meta_description(long_text, max_length=100)
    assert len(truncated) <= 103  # with ellipsis
    assert truncated.endswith("...")


def test_generate_meta_tags_article_and_website() -> None:
    """Verify Open Graph and Twitter Card tags for articles and website pages."""
    seo = SEOEngine(
        base_url="https://pulsepress.dev",
        site_name="PulsePress Dev",
        default_description="Tech blog",
        default_image="/images/og.png",
    )

    # 1. Post Article Meta Tags
    post = {
        "title": "Scaling Search Engines",
        "slug": "scaling-search-engines",
        "body_markdown": "Full text about search architectures and inverted indexes.",
        "excerpt": "Detailed guide on search engine scaling.",
        "featured_image": "/images/search.png",
        "published_at": "2026-11-23T10:00:00Z",
        "updated_at": "2026-11-24T12:00:00Z",
        "author_name": "Alice Engineer",
        "tags": [{"name": "Search"}, {"name": "BM25"}],
    }
    meta = seo.generate_meta_tags(post=post)
    assert meta["title"] == "Scaling Search Engines | PulsePress Dev"
    assert meta["description"] == "Detailed guide on search engine scaling."
    assert meta["canonical"] == "https://pulsepress.dev/posts/scaling-search-engines"

    og = meta["og"]
    assert og["og:title"] == "Scaling Search Engines | PulsePress Dev"
    assert og["og:type"] == "article"
    assert og["og:url"] == "https://pulsepress.dev/posts/scaling-search-engines"
    assert og["og:image"] == "https://pulsepress.dev/images/search.png"
    assert og["og:site_name"] == "PulsePress Dev"
    assert og["article:published_time"] == "2026-11-23T10:00:00Z"
    assert og["article:modified_time"] == "2026-11-24T12:00:00Z"
    assert og["article:author"] == "Alice Engineer"
    assert og["article:tag"] == ["Search", "BM25"]

    tw = meta["twitter"]
    assert tw["twitter:card"] == "summary_large_image"
    assert tw["twitter:title"] == "Scaling Search Engines | PulsePress Dev"
    assert tw["twitter:image"] == "https://pulsepress.dev/images/search.png"

    # 2. General Website Meta Tags
    site_meta = seo.generate_meta_tags(
        custom_title="Archive",
        custom_description="Explore past articles",
        custom_path="/archive",
    )
    assert site_meta["title"] == "Archive | PulsePress Dev"
    assert site_meta["description"] == "Explore past articles"
    assert site_meta["canonical"] == "https://pulsepress.dev/archive"
    assert site_meta["og"]["og:type"] == "website"


def test_generate_json_ld_schema() -> None:
    """Verify Schema.org BlogPosting and WebSite structured data."""
    seo = SEOEngine(
        base_url="https://pulsepress.dev",
        site_name="PulsePress",
    )

    # 1. Homepage WebSite schema
    site_ld = seo.generate_json_ld()
    assert site_ld["@context"] == "https://schema.org"
    assert site_ld["@type"] == "WebSite"
    assert site_ld["url"] == "https://pulsepress.dev/"
    assert "potentialAction" in site_ld
    assert site_ld["potentialAction"]["@type"] == "SearchAction"

    # 2. BlogPosting schema with breadcrumbs
    dt = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
    post = {
        "title": "Understanding BM25",
        "slug": "understanding-bm25",
        "body_markdown": "A comprehensive deep dive into BM25 information retrieval.",
        "excerpt": "A deep dive into BM25.",
        "featured_image": "/images/bm25.jpg",
        "published_at": dt,
        "author_name": "Bob Author",
        "author_bio": "Distributed systems engineer",
        "tags": [{"name": "Information Retrieval"}, {"name": "Algorithms"}],
    }
    breadcrumbs = [
        {"name": "Home", "path": "/"},
        {"name": "Posts", "path": "/posts"},
        {"name": "Understanding BM25", "path": "/posts/understanding-bm25"},
    ]
    post_ld = seo.generate_json_ld(post=post, breadcrumbs=breadcrumbs)
    assert post_ld["@context"] == "https://schema.org"
    assert post_ld["@type"] == "BlogPosting"
    assert post_ld["headline"] == "Understanding BM25"
    assert (
        post_ld["mainEntityOfPage"]["@id"]
        == "https://pulsepress.dev/posts/understanding-bm25"
    )
    assert post_ld["author"]["@type"] == "Person"
    assert post_ld["author"]["name"] == "Bob Author"
    assert post_ld["author"]["description"] == "Distributed systems engineer"
    assert post_ld["publisher"]["@type"] == "Organization"
    assert post_ld["datePublished"] == dt.isoformat()
    assert "Information Retrieval, Algorithms" in post_ld["keywords"]
    assert post_ld["wordCount"] == 8

    bc = post_ld["breadcrumb"]
    assert bc["@type"] == "BreadcrumbList"
    assert len(bc["itemListElement"]) == 3
    assert bc["itemListElement"][0]["position"] == 1
    assert bc["itemListElement"][0]["name"] == "Home"
    assert bc["itemListElement"][2]["name"] == "Understanding BM25"


def test_render_html_meta() -> None:
    """Verify HTML rendering of head tags and embedded JSON-LD validity."""
    seo = SEOEngine(base_url="https://pulsepress.dev", site_name="PulsePress")
    post = {
        "title": "HTML Head Test",
        "slug": "html-head-test",
        "body_markdown": "Testing rendering of head tags.",
        "excerpt": "Testing rendering.",
    }
    html_output = seo.render_html_meta(post=post)
    assert "<title>HTML Head Test | PulsePress</title>" in html_output
    assert '<meta name="description" content="Testing rendering.">' in html_output
    assert (
        '<link rel="canonical" href="https://pulsepress.dev/posts/html-head-test">'
        in html_output
    )
    assert '<meta property="og:type" content="article">' in html_output
    assert '<meta name="twitter:card" content="summary_large_image">' in html_output
    assert '<script type="application/ld+json">' in html_output

    # Validate JSON-LD script can be parsed cleanly
    start = html_output.find('<script type="application/ld+json">') + len(
        '<script type="application/ld+json">'
    )
    end = html_output.find("</script>", start)
    extracted_json = html_output[start:end].strip()
    parsed = json.loads(extracted_json)
    assert parsed["@type"] == "BlogPosting"
    assert parsed["headline"] == "HTML Head Test"


def test_sitemap_generator() -> None:
    """Verify XML Sitemap 0.9 protocol compliance and element parsing."""
    generator = SitemapGenerator(base_url="https://pulsepress.dev")

    posts = [
        {
            "slug": "post-one",
            "status": "published",
            "published_at": "2026-11-20T10:00:00Z",
            "updated_at": "2026-11-22T12:00:00Z",
        },
        {
            "slug": "draft-post",
            "status": "draft",
            "published_at": "2026-11-21T10:00:00Z",
        },
        {
            "slug": "post-two",
            "status": "published",
            "published_at": datetime(2026, 11, 23, 8, 30),
        },
    ]
    tags = [
        {"slug": "python"},
        {"slug": "sqlite"},
    ]
    static_pages = [
        {"path": "/about", "changefreq": "monthly", "priority": "0.7"},
    ]

    xml_str = generator.generate(posts=posts, tags=tags, static_pages=static_pages)
    assert xml_str.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in xml_str

    # Parse with standard XML parser to verify validity
    root = ET.fromstring(xml_str)
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"

    locs = [
        elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc").text
        for elem in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url")
    ]

    # Homepage
    assert "https://pulsepress.dev/" in locs
    # Static page
    assert "https://pulsepress.dev/about" in locs
    # Published posts included
    assert "https://pulsepress.dev/posts/post-one" in locs
    assert "https://pulsepress.dev/posts/post-two" in locs
    # Draft post excluded
    assert "https://pulsepress.dev/posts/draft-post" not in locs
    # Tags included
    assert "https://pulsepress.dev/tags/python" in locs
    assert "https://pulsepress.dev/tags/sqlite" in locs


def test_rss_and_atom_feed_generator() -> None:
    """Verify RSS 2.0 and Atom 1.0 feed structure and XML validity."""
    feed_gen = RSSFeedGenerator(
        base_url="https://pulsepress.dev",
        site_name="PulsePress Feed",
        site_description="Engineering articles",
        language="en-us",
    )

    posts = [
        {
            "slug": "rss-article",
            "title": "Syndication Architecture",
            "excerpt": "Guide to building RSS and Atom feeds.",
            "status": "published",
            "published_at": "2026-11-23T12:00:00Z",
            "author_name": "Syndication Bot",
            "tags": [{"name": "RSS"}, {"name": "Architecture"}],
        },
        {
            "slug": "draft-article",
            "title": "Unpublished Notes",
            "status": "draft",
        },
    ]

    # 1. RSS 2.0
    rss_xml = feed_gen.generate_rss(posts=posts)
    assert rss_xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert '<rss version="2.0"' in rss_xml
    assert "<channel>" in rss_xml
    assert "<title>PulsePress Feed</title>" in rss_xml
    assert "<item>" in rss_xml
    assert "<title>Syndication Architecture</title>" in rss_xml
    assert "<category>RSS</category>" in rss_xml
    assert "<category>Architecture</category>" in rss_xml
    assert "Unpublished Notes" not in rss_xml

    # Parse RSS
    rss_root = ET.fromstring(rss_xml)
    assert rss_root.tag == "rss"
    channel = rss_root.find("channel")
    assert channel is not None
    items = channel.findall("item")
    assert len(items) == 1
    assert items[0].find("title").text == "Syndication Architecture"
    assert items[0].find("link").text == "https://pulsepress.dev/posts/rss-article"

    # 2. Atom 1.0
    atom_xml = feed_gen.generate_atom(posts=posts)
    assert atom_xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert '<feed xmlns="http://www.w3.org/2005/Atom">' in atom_xml
    atom_root = ET.fromstring(atom_xml)
    assert atom_root.tag == "{http://www.w3.org/2005/Atom}feed"
    entries = atom_root.findall("{http://www.w3.org/2005/Atom}entry")
    assert len(entries) == 1
    assert (
        entries[0].find("{http://www.w3.org/2005/Atom}title").text
        == "Syndication Architecture"
    )


def test_robots_generator() -> None:
    """Verify robots.txt directives, disallow rules, and sitemap reference."""
    robots_gen = RobotsGenerator(base_url="https://pulsepress.dev")
    robots_txt = robots_gen.generate()

    assert "User-agent: *" in robots_txt
    assert "Allow: /" in robots_txt
    assert "Disallow: /admin" in robots_txt
    assert "Disallow: /api/" in robots_txt
    assert "Sitemap: https://pulsepress.dev/sitemap.xml" in robots_txt

    # Custom rules test
    custom_rules = {
        "Googlebot": {
            "allow": ["/public/"],
            "disallow": ["/private/"],
            "crawl_delay": 2,
        }
    }
    custom_txt = robots_gen.generate(
        crawl_delay=1,
        bot_rules=custom_rules,
    )
    assert "Crawl-delay: 1" in custom_txt
    assert "User-agent: Googlebot" in custom_txt
    assert "Allow: /public/" in custom_txt
    assert "Disallow: /private/" in custom_txt
    assert "Crawl-delay: 2" in custom_txt


def test_sitemap_generator_edge_cases() -> None:
    """Verify sitemap date parsing, priority calculation, and invalid post handling."""
    from datetime import timedelta

    generator = SitemapGenerator(base_url="https://pulsepress.dev")

    # Date formatting edge cases
    assert generator.format_date(None) is None
    assert generator.format_date(12345) is None
    assert generator.format_date("2026-11-25T10:00:00") == "2026-11-25"
    assert generator.format_date("not-a-date") is None

    # Priority calculations
    now = datetime.now()
    assert generator.calculate_post_priority({}) == "0.6"
    assert generator.calculate_post_priority({"published_at": "invalid"}) == "0.8"
    assert (
        generator.calculate_post_priority({"published_at": now - timedelta(days=5)})
        == "0.9"
    )
    assert (
        generator.calculate_post_priority({"published_at": now - timedelta(days=60)})
        == "0.8"
    )
    assert (
        generator.calculate_post_priority({"published_at": now - timedelta(days=200)})
        == "0.6"
    )

    # Empty slugs and drafts in sitemap
    xml = generator.generate(
        posts=[
            {"slug": "", "status": "published"},
            {"slug": "draft-one", "status": "draft"},
        ],
        tags=[{"slug": ""}],
    )
    assert "draft-one" not in xml


def test_feed_generator_edge_cases() -> None:
    """Verify RSS/Atom date parsing fallbacks and empty post handling."""
    feed_gen = RSSFeedGenerator(base_url="https://pulsepress.dev")

    # Formatting fallbacks
    assert "GMT" in feed_gen.format_rfc822("invalid-date-string")
    assert "Z" in feed_gen.format_iso8601("invalid-date-string")

    # Empty slugs and drafts skipped
    posts = [
        {"slug": "", "status": "published"},
        {"slug": "draft-feed", "status": "draft"},
    ]
    rss = feed_gen.generate_rss(posts=posts)
    atom = feed_gen.generate_atom(posts=posts)
    assert "draft-feed" not in rss
    assert "draft-feed" not in atom


def test_seo_http_endpoints(client, db_conn) -> None:
    """Verify HTTP responses for sitemap.xml, feeds, robots.txt, and metadata APIs."""
    posts, _ = PostDAO.list_posts(db_conn, status="published")
    assert len(posts) > 0
    post_slug = posts[0]["slug"]
    post_id = posts[0]["id"]
    post_title = posts[0]["title"]

    # 1. /sitemap.xml
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert "application/xml" in res.content_type
    assert b"<urlset" in res.data
    assert post_slug.encode() in res.data

    # 2. /rss.xml and /feed.xml
    res = client.get("/rss.xml")
    assert res.status_code == 200
    assert "application/rss+xml" in res.content_type
    assert b'<rss version="2.0"' in res.data
    assert post_slug.encode() in res.data

    res_feed = client.get("/feed.xml")
    assert res_feed.status_code == 200
    assert "application/rss+xml" in res_feed.content_type

    # 3. /atom.xml
    res = client.get("/atom.xml")
    assert res.status_code == 200
    assert "application/atom+xml" in res.content_type
    assert b"<feed" in res.data
    assert post_slug.encode() in res.data

    # 4. /robots.txt
    res = client.get("/robots.txt")
    assert res.status_code == 200
    assert "text/plain" in res.content_type
    assert b"User-agent: *" in res.data
    assert b"Sitemap:" in res.data

    # 5. /api/seo/site
    res = client.get("/api/seo/site")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert "meta_tags" in data
    assert "json_ld" in data
    assert "html_head" in data
    assert data["json_ld"]["@type"] == "WebSite"

    # 6. /api/seo/post/<id_or_slug>
    res = client.get(f"/api/seo/post/{post_slug}")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["meta_tags"]["title"].startswith(post_title)
    assert data["json_ld"]["@type"] == "BlogPosting"
    assert post_title in data["html_head"]

    # Test lookup by numeric ID
    res_num = client.get(f"/api/seo/post/{post_id}")
    assert res_num.status_code == 200

    # Test 404 for nonexistent post
    res_404 = client.get("/api/seo/post/non-existent-article-slug")
    assert res_404.status_code == 404
    assert res_404.get_json()["status"] == "error"
