"""SEO engine for metadata generation, Open Graph, Twitter Cards, and JSON-LD Schema."""

import html
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


class SEOEngine:
    """Generates canonical URLs, meta tags, and JSON-LD structured data."""

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        site_name: str = "PulsePress",
        default_description: str = "A full-featured technical blog with advanced SEO.",
        default_image: str = "/assets/images/og-default.png",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.site_name = site_name
        self.default_description = default_description
        self.default_image = default_image

    def canonical_url(self, path: str = "/") -> str:
        """Resolve a full canonical URL for a given relative or absolute path."""
        if not path:
            return self.base_url + "/"
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def post_canonical_url(self, slug: str) -> str:
        """Resolve canonical URL for a specific post slug."""
        clean_slug = slug.strip("/")
        return self.canonical_url(f"/posts/{clean_slug}")

    def generate_meta_description(
        self, text: Optional[str], max_length: int = 160
    ) -> str:
        """Extract a clean meta description stripped of markdown clamped to words."""
        if not text:
            return self.default_description

        # Strip code blocks
        clean = re.sub(r"```[\s\S]*?```", "", text)
        clean = re.sub(r"`[^`]*`", "", clean)
        # Strip HTML tags
        clean = re.sub(r"<[^>]+>", "", clean)
        # Strip markdown images and links
        clean = re.sub(r"!\[.*?\]\(.*?\)", "", clean)
        clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean)
        # Strip markdown headings, quotes, horizontal rules, lists
        clean = re.sub(r"^[#>\-\*\+\d\.]+\s*", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"[*_~`]", "", clean)
        # Collapse whitespace
        clean = " ".join(clean.split()).strip()

        if not clean:
            return self.default_description

        if len(clean) <= max_length:
            return clean

        truncated = clean[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > int(max_length * 0.6):
            truncated = truncated[:last_space]

        return truncated.rstrip(".,;:- ") + "..."

    def generate_meta_tags(
        self,
        post: Optional[Dict[str, Any]] = None,
        custom_title: Optional[str] = None,
        custom_description: Optional[str] = None,
        custom_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate structured metadata including Open Graph and Twitter Card tags."""
        if post:
            post_title = post.get("title", "Untitled Post")
            page_title = f"{post_title} | {self.site_name}"
            raw_desc = post.get("excerpt") or post.get("body_markdown") or ""
            description = self.generate_meta_description(raw_desc, max_length=160)
            slug = post.get("slug", "")
            page_url = (
                self.post_canonical_url(slug) if slug else self.canonical_url("/")
            )
            image = post.get("featured_image") or self.default_image
            if not image.startswith("http://") and not image.startswith("https://"):
                image = self.canonical_url(image)
            page_type = "article"
            published_time = post.get("published_at")
            modified_time = post.get("updated_at") or published_time
            author = post.get("author_name") or post.get("author") or self.site_name
            tags = post.get("tags", [])
        else:
            page_title = (
                f"{custom_title} | {self.site_name}" if custom_title else self.site_name
            )
            description = (
                custom_description if custom_description else self.default_description
            )
            page_url = self.canonical_url(custom_path or "/")
            image = self.canonical_url(self.default_image)
            page_type = "website"
            published_time = None
            modified_time = None
            author = self.site_name
            tags = []

        og_tags = {
            "og:title": page_title,
            "og:description": description,
            "og:type": page_type,
            "og:url": page_url,
            "og:image": image,
            "og:site_name": self.site_name,
        }

        if page_type == "article":
            if published_time:
                og_tags["article:published_time"] = str(published_time)
            if modified_time:
                og_tags["article:modified_time"] = str(modified_time)
            if author:
                og_tags["article:author"] = str(author)
            if tags:
                tag_names = [t["name"] if isinstance(t, dict) else str(t) for t in tags]
                og_tags["article:tag"] = tag_names

        twitter_tags = {
            "twitter:card": "summary_large_image",
            "twitter:title": page_title,
            "twitter:description": description,
            "twitter:image": image,
        }

        return {
            "title": page_title,
            "description": description,
            "canonical": page_url,
            "og": og_tags,
            "twitter": twitter_tags,
        }

    def generate_json_ld(
        self,
        post: Optional[Dict[str, Any]] = None,
        breadcrumbs: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Generate Schema.org compliant JSON-LD structured data."""
        if not post:
            search_url = f"{self.canonical_url('/search')}?q={{search_term}}"
            schema: Dict[str, Any] = {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": self.site_name,
                "url": self.canonical_url("/"),
                "description": self.default_description,
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": search_url,
                    "query-input": "required name=search_term",
                },
            }
            return schema

        slug = post.get("slug", "")
        canonical = self.post_canonical_url(slug) if slug else self.canonical_url("/")
        image = post.get("featured_image") or self.default_image
        if not image.startswith("http://") and not image.startswith("https://"):
            image = self.canonical_url(image)

        author_name = post.get("author_name") or post.get("author") or self.site_name
        author_bio = post.get("author_bio")
        author_data: Dict[str, Any] = {
            "@type": "Person",
            "name": author_name,
        }
        if author_bio:
            author_data["description"] = author_bio

        raw_desc = post.get("excerpt") or post.get("body_markdown") or ""
        description = self.generate_meta_description(raw_desc, max_length=200)

        tags = post.get("tags", [])
        keywords = [t["name"] if isinstance(t, dict) else str(t) for t in tags]

        date_published = post.get("published_at")
        date_modified = post.get("updated_at") or date_published

        # Format dates as ISO string if datetime
        if isinstance(date_published, datetime):
            date_published = date_published.isoformat()
        elif date_published:
            date_published = str(date_published)

        if isinstance(date_modified, datetime):
            date_modified = date_modified.isoformat()
        elif date_modified:
            date_modified = str(date_modified)

        schema = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": canonical,
            },
            "headline": post.get("title", "Untitled Post"),
            "description": description,
            "image": [image],
            "author": author_data,
            "publisher": {
                "@type": "Organization",
                "name": self.site_name,
                "logo": {
                    "@type": "ImageObject",
                    "url": self.canonical_url("/assets/images/logo.png"),
                },
            },
        }

        if date_published:
            schema["datePublished"] = date_published
        if date_modified:
            schema["dateModified"] = date_modified
        if keywords:
            schema["keywords"] = ", ".join(keywords)

        if post.get("body_markdown"):
            schema["wordCount"] = len(post["body_markdown"].split())

        if breadcrumbs:
            breadcrumb_items = []
            for idx, crumb in enumerate(breadcrumbs, start=1):
                breadcrumb_items.append(
                    {
                        "@type": "ListItem",
                        "position": idx,
                        "name": crumb["name"],
                        "item": self.canonical_url(crumb["path"]),
                    }
                )
            schema["breadcrumb"] = {
                "@type": "BreadcrumbList",
                "itemListElement": breadcrumb_items,
            }

        return schema

    def render_html_meta(
        self,
        post: Optional[Dict[str, Any]] = None,
        custom_title: Optional[str] = None,
        custom_description: Optional[str] = None,
        custom_path: Optional[str] = None,
    ) -> str:
        """Render complete HTML head tags (title, meta, og, twitter, json-ld)."""
        meta_data = self.generate_meta_tags(
            post=post,
            custom_title=custom_title,
            custom_description=custom_description,
            custom_path=custom_path,
        )
        json_ld = self.generate_json_ld(post=post)

        desc_esc = html.escape(meta_data["description"])
        can_esc = html.escape(meta_data["canonical"])
        lines: List[str] = [
            f"<title>{html.escape(meta_data['title'])}</title>",
            f'<meta name="description" content="{desc_esc}">',
            f'<link rel="canonical" href="{can_esc}">',
        ]

        # Open Graph
        for prop, val in meta_data["og"].items():
            p_esc = html.escape(prop)
            if isinstance(val, list):
                for item in val:
                    lines.append(
                        f'<meta property="{p_esc}" content="{html.escape(str(item))}">'
                    )
            elif val is not None:
                lines.append(
                    f'<meta property="{p_esc}" content="{html.escape(str(val))}">'
                )

        # Twitter
        for name, val in meta_data["twitter"].items():
            if val is not None:
                n_esc = html.escape(name)
                v_esc = html.escape(str(val))
                lines.append(f'<meta name="{n_esc}" content="{v_esc}">')

        # JSON-LD
        json_str = json.dumps(json_ld, indent=2, ensure_ascii=False)
        lines.append(f'<script type="application/ld+json">\n{json_str}\n</script>')

        return "\n".join(lines)
