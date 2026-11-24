"""Markdown rendering engine with Pygments syntax highlighting and TOC extraction."""

import json
import math
import re
from typing import Any, Dict, List, Optional

import markdown
from app.services.slug_service import generate_slug
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension


class MarkdownEngine:
    """Production-grade Markdown processor for technical blog publications."""

    def __init__(self, wpm: int = 200):
        """Initialize renderer with reading speed settings."""
        self.wpm = max(50, wpm)

    def render(self, md_text: str) -> str:
        """Convert Markdown source into syntax-highlighted HTML."""
        if not md_text:
            return ""

        md = markdown.Markdown(
            extensions=[
                FencedCodeExtension(),
                CodeHiliteExtension(
                    css_class="highlight",
                    use_pygments=True,
                    guess_lang=False,
                ),
                TableExtension(),
                TocExtension(permalink=False, slugify=generate_slug),
                "nl2br",
                "sane_lists",
            ]
        )
        return md.convert(md_text)

    def extract_toc(self, md_text: str) -> List[Dict[str, Any]]:
        """Extract structured headings hierarchy from Markdown source."""
        if not md_text:
            return []

        md = markdown.Markdown(
            extensions=[TocExtension(permalink=False, slugify=generate_slug)]
        )
        md.convert(md_text)
        tokens = getattr(md, "toc_tokens", [])

        flat_toc: List[Dict[str, Any]] = []

        def _flatten(node_list: List[Dict[str, Any]]) -> None:
            for node in node_list:
                flat_toc.append(
                    {
                        "level": node.get("level", 2),
                        "title": node.get("name", ""),
                        "anchor": node.get("id", ""),
                    }
                )
                children = node.get("children", [])
                if children:
                    _flatten(children)

        _flatten(tokens)
        return flat_toc

    def estimate_reading_time(
        self, md_text: str, custom_wpm: Optional[int] = None
    ) -> int:
        """Estimate reading duration in minutes based on words and code density."""
        if not md_text:
            return 1

        wpm = custom_wpm or self.wpm

        # Extract fenced code blocks and count code lines
        code_blocks = re.findall(r"```[\s\S]*?```", md_text)
        code_line_count = 0
        for block in code_blocks:
            code_line_count += len(block.strip().split("\n"))

        # Strip code blocks to count prose words
        prose = re.sub(r"```[\s\S]*?```", " ", md_text)
        words = re.findall(r"\b\w+\b", prose)
        prose_word_count = len(words)

        # Weight code lines at ~2.5 words per line (equivalent to 80-100 WPM)
        equivalent_words = prose_word_count + int(code_line_count * 2.5)

        minutes = math.ceil(equivalent_words / wpm)
        return max(1, minutes)

    def extract_excerpt(self, md_text: str, max_chars: int = 160) -> str:
        """Extract a clean textual summary from the first Markdown paragraph."""
        if not md_text:
            return ""

        # Remove code blocks
        clean = re.sub(r"```[\s\S]*?```", " ", md_text)
        # Remove headings
        clean = re.sub(r"^#+\s+.*$", " ", clean, flags=re.MULTILINE)
        # Remove images
        clean = re.sub(r"!\[.*?\]\(.*?\)", " ", clean)
        # Replace links with text
        clean = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", clean)
        # Remove bold, italics, strikethrough, backticks
        clean = re.sub(r"[*_~`]", "", clean)

        # Extract first non-empty paragraph
        paragraphs = [p.strip() for p in clean.split("\n\n") if p.strip()]
        if not paragraphs:
            return ""

        first_para = " ".join(paragraphs[0].split())

        if len(first_para) <= max_chars:
            return first_para

        # Truncate at word boundary
        truncated = first_para[:max_chars].rstrip()
        last_space = truncated.rfind(" ")
        if last_space > max_chars // 2:
            return truncated[:last_space] + "..."
        return truncated + "..."

    def process(self, md_text: str, custom_wpm: Optional[int] = None) -> Dict[str, Any]:
        """Bundle rendering, TOC extraction, reading time, and excerpt."""
        html = self.render(md_text)
        toc = self.extract_toc(md_text)
        time_mins = self.estimate_reading_time(md_text, custom_wpm=custom_wpm)
        excerpt = self.extract_excerpt(md_text)

        return {
            "body_html": html,
            "toc": toc,
            "toc_json": json.dumps(toc),
            "reading_time_minutes": time_mins,
            "excerpt": excerpt,
        }
