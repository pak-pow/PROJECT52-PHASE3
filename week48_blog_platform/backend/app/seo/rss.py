"""RSS 2.0 and Atom syndication feed generator for PulsePress blog platform."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape  # nosec B406


class RSSFeedGenerator:
    """Generates standard-compliant RSS 2.0 and Atom syndication feeds."""

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        site_name: str = "PulsePress",
        site_description: str = (
            "A full-featured technical blog with advanced SEO and full-text search."
        ),
        language: str = "en-us",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.site_name = site_name
        self.site_description = site_description
        self.language = language

    def format_rfc822(self, val: Any) -> str:
        """Format a datetime or ISO string to RFC 822 format (e.g. GMT date)."""
        dt: Optional[datetime] = None
        if isinstance(val, datetime):
            dt = val
        elif isinstance(val, str) and val.strip():
            try:
                dt = datetime.fromisoformat(val.strip().replace("Z", "+00:00"))
            except Exception:
                dt = None

        if dt is None:
            dt = datetime.now(timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

    def format_iso8601(self, val: Any) -> str:
        """Format a datetime or ISO string to ISO 8601 UTC string."""
        dt: Optional[datetime] = None
        if isinstance(val, datetime):
            dt = val
        elif isinstance(val, str) and val.strip():
            try:
                dt = datetime.fromisoformat(val.strip().replace("Z", "+00:00"))
            except Exception:
                dt = None

        if dt is None:
            dt = datetime.now(timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def generate_rss(
        self,
        posts: Optional[List[Dict[str, Any]]] = None,
        feed_url: Optional[str] = None,
    ) -> str:
        """Generate RSS 2.0 compliant XML feed string."""
        resolved_feed_url = feed_url or f"{self.base_url}/rss.xml"
        now_rfc = self.format_rfc822(datetime.now(timezone.utc))

        lines: List[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
            "  <channel>",
            f"    <title>{escape(self.site_name)}</title>",
            f"    <link>{escape(self.base_url)}/</link>",
            f"    <description>{escape(self.site_description)}</description>",
            f"    <language>{escape(self.language)}</language>",
            f"    <lastBuildDate>{escape(now_rfc)}</lastBuildDate>",
            (
                f'    <atom:link href="{escape(resolved_feed_url)}" '
                'rel="self" type="application/rss+xml" />'
            ),
        ]

        if posts:
            for post in posts:
                # Filter for published posts only
                if post.get("status") != "published":
                    continue

                slug = post.get("slug", "")
                if not slug:
                    continue

                item_url = f"{self.base_url}/posts/{slug.strip('/')}"
                title = post.get("title", "Untitled Post")
                excerpt = (
                    post.get("excerpt")
                    or post.get("body_markdown", "")[:300]
                    or "No description provided."
                )
                pub_val = (
                    post.get("published_at")
                    or post.get("updated_at")
                    or post.get("created_at")
                )
                pub_date = self.format_rfc822(pub_val)
                author = post.get("author_name") or post.get("author") or self.site_name

                lines.append("    <item>")
                lines.append(f"      <title>{escape(title)}</title>")
                lines.append(f"      <link>{escape(item_url)}</link>")
                # Use CDATA for description to safely encapsulate formatted content
                clean_desc = excerpt.replace("]]>", "]]&gt;")
                lines.append(
                    f"      <description><![CDATA[{clean_desc}]]></description>"
                )
                lines.append(f"      <pubDate>{escape(pub_date)}</pubDate>")
                lines.append(
                    f'      <guid isPermaLink="true">{escape(item_url)}</guid>'
                )
                lines.append(f"      <author>{escape(str(author))}</author>")

                tags = post.get("tags", [])
                for tag in tags:
                    tag_name = tag["name"] if isinstance(tag, dict) else str(tag)
                    lines.append(f"      <category>{escape(tag_name)}</category>")

                lines.append("    </item>")

        lines.append("  </channel>")
        lines.append("</rss>")
        return "\n".join(lines)

    def generate_atom(
        self,
        posts: Optional[List[Dict[str, Any]]] = None,
        feed_url: Optional[str] = None,
    ) -> str:
        """Generate Atom 1.0 compliant XML feed string."""
        resolved_feed_url = feed_url or f"{self.base_url}/atom.xml"
        now_iso = self.format_iso8601(datetime.now(timezone.utc))

        lines: List[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<feed xmlns="http://www.w3.org/2005/Atom">',
            f"  <title>{escape(self.site_name)}</title>",
            f"  <subtitle>{escape(self.site_description)}</subtitle>",
            f'  <link href="{escape(self.base_url)}/" rel="alternate" />',
            f'  <link href="{escape(resolved_feed_url)}" rel="self" />',
            f"  <id>{escape(self.base_url)}/</id>",
            f"  <updated>{escape(now_iso)}</updated>",
        ]

        if posts:
            for post in posts:
                if post.get("status") != "published":
                    continue

                slug = post.get("slug", "")
                if not slug:
                    continue

                item_url = f"{self.base_url}/posts/{slug.strip('/')}"
                title = post.get("title", "Untitled Post")
                excerpt = (
                    post.get("excerpt")
                    or post.get("body_markdown", "")[:300]
                    or "No description provided."
                )
                pub_val = (
                    post.get("published_at")
                    or post.get("updated_at")
                    or post.get("created_at")
                )
                updated_val = (
                    post.get("updated_at")
                    or post.get("published_at")
                    or post.get("created_at")
                )
                pub_iso = self.format_iso8601(pub_val)
                updated_iso = self.format_iso8601(updated_val)
                author = post.get("author_name") or post.get("author") or self.site_name

                lines.append("  <entry>")
                lines.append(f"    <title>{escape(title)}</title>")
                lines.append(f'    <link href="{escape(item_url)}" />')
                lines.append(f"    <id>{escape(item_url)}</id>")
                lines.append(f"    <published>{escape(pub_iso)}</published>")
                lines.append(f"    <updated>{escape(updated_iso)}</updated>")
                lines.append(f'    <summary type="text">{escape(excerpt)}</summary>')
                lines.append("    <author>")
                lines.append(f"      <name>{escape(str(author))}</name>")
                lines.append("    </author>")

                tags = post.get("tags", [])
                for tag in tags:
                    tag_name = tag["name"] if isinstance(tag, dict) else str(tag)
                    lines.append(f'    <category term="{escape(tag_name)}" />')

                lines.append("  </entry>")

        lines.append("</feed>")
        return "\n".join(lines)
