"""XML Sitemap 0.9 protocol generator for PulsePress blog platform."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape  # nosec B406


class SitemapGenerator:
    """Generates valid XML sitemaps adhering to the Sitemaps 0.9 protocol."""

    def __init__(self, base_url: str = "http://localhost:5000") -> None:
        self.base_url = base_url.rstrip("/")

    def format_date(self, val: Any) -> Optional[str]:
        """Format datetime into ISO 8601 W3C format (YYYY-MM-DD)."""
        if not val:
            return None
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%d")
        if isinstance(val, str):
            # If string is ISO format, take first 10 characters (YYYY-MM-DD)
            val_clean = val.strip()
            if len(val_clean) >= 10 and val_clean[4] == "-" and val_clean[7] == "-":
                return val_clean[:10]
            try:
                dt = datetime.fromisoformat(val_clean.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            except Exception:
                return None
        return None

    def calculate_post_priority(self, post: Dict[str, Any]) -> str:
        """Assign priority score based on publication recency or status."""
        pub_date = post.get("published_at") or post.get("created_at")
        if not pub_date:
            return "0.6"
        dt = None
        if isinstance(pub_date, datetime):
            dt = pub_date
        elif isinstance(pub_date, str):
            try:
                dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            except Exception:
                dt = None

        if dt:
            now = datetime.now() if dt.tzinfo is None else datetime.now(dt.tzinfo)
            days_old = (now - dt).days
            if days_old <= 30:
                return "0.9"
            if days_old <= 180:
                return "0.8"
            return "0.6"

        return "0.8"

    def generate(
        self,
        posts: Optional[List[Dict[str, Any]]] = None,
        tags: Optional[List[Dict[str, Any]]] = None,
        static_pages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Generate XML string for urlset containing homepage, posts, and tags."""
        lines: List[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]

        # 1. Homepage
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(self.base_url)}/</loc>")
        lines.append("    <changefreq>daily</changefreq>")
        lines.append("    <priority>1.0</priority>")
        lines.append("  </url>")

        # 2. Additional Static Pages
        if static_pages:
            for page in static_pages:
                path = page.get("path", "/").lstrip("/")
                url = f"{self.base_url}/{path}"
                freq = page.get("changefreq", "monthly")
                prio = page.get("priority", "0.5")
                lines.append("  <url>")
                lines.append(f"    <loc>{escape(url)}</loc>")
                lines.append(f"    <changefreq>{escape(freq)}</changefreq>")
                lines.append(f"    <priority>{escape(str(prio))}</priority>")
                lines.append("  </url>")

        # 3. Published Posts
        if posts:
            for post in posts:
                # Only include published posts
                status = post.get("status", "published")
                if status != "published":
                    continue

                slug = post.get("slug", "")
                if not slug:
                    continue

                url = f"{self.base_url}/posts/{slug.strip('/')}"
                lines.append("  <url>")
                lines.append(f"    <loc>{escape(url)}</loc>")

                lastmod_val = (
                    post.get("updated_at")
                    or post.get("published_at")
                    or post.get("created_at")
                )
                formatted_lastmod = self.format_date(lastmod_val)
                if formatted_lastmod:
                    lines.append(f"    <lastmod>{escape(formatted_lastmod)}</lastmod>")

                lines.append("    <changefreq>weekly</changefreq>")
                priority = self.calculate_post_priority(post)
                lines.append(f"    <priority>{escape(priority)}</priority>")
                lines.append("  </url>")

        # 4. Tags
        if tags:
            for tag in tags:
                slug = tag.get("slug", "")
                if not slug:
                    continue
                url = f"{self.base_url}/tags/{slug.strip('/')}"
                lines.append("  <url>")
                lines.append(f"    <loc>{escape(url)}</loc>")
                lines.append("    <changefreq>weekly</changefreq>")
                lines.append("    <priority>0.5</priority>")
                lines.append("  </url>")

        lines.append("</urlset>")
        return "\n".join(lines)
