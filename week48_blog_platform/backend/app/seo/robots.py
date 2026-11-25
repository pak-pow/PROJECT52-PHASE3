"""Robots.txt crawl directive generator for PulsePress blog platform."""

from typing import Dict, List, Optional


class RobotsGenerator:
    """Generates standard robots.txt files with crawl directives and sitemap links."""

    DEFAULT_DISALLOW = ["/admin", "/api/"]
    DEFAULT_ALLOW = ["/"]

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        sitemap_path: str = "/sitemap.xml",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.sitemap_path = (
            sitemap_path if sitemap_path.startswith("/") else f"/{sitemap_path}"
        )

    def generate(
        self,
        disallow_paths: Optional[List[str]] = None,
        allow_paths: Optional[List[str]] = None,
        crawl_delay: Optional[int] = None,
        bot_rules: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> str:
        """Generate robots.txt content."""
        lines: List[str] = []

        # Default rule for all bots
        lines.append("User-agent: *")

        disallows = (
            disallow_paths if disallow_paths is not None else self.DEFAULT_DISALLOW
        )
        allows = allow_paths if allow_paths is not None else self.DEFAULT_ALLOW

        for allow in allows:
            lines.append(f"Allow: {allow}")

        for disallow in disallows:
            lines.append(f"Disallow: {disallow}")

        if crawl_delay is not None and crawl_delay > 0:
            lines.append(f"Crawl-delay: {crawl_delay}")

        # Specific bot rules if provided
        if bot_rules:
            for bot, rules in bot_rules.items():
                lines.append("")
                lines.append(f"User-agent: {bot}")
                for allow in rules.get("allow", []):
                    lines.append(f"Allow: {allow}")
                for disallow in rules.get("disallow", []):
                    lines.append(f"Disallow: {disallow}")
                if "crawl_delay" in rules:
                    lines.append(f"Crawl-delay: {rules['crawl_delay']}")

        # Sitemap reference
        lines.append("")
        sitemap_url = f"{self.base_url}{self.sitemap_path}"
        lines.append(f"Sitemap: {sitemap_url}")

        return "\n".join(lines) + "\n"
