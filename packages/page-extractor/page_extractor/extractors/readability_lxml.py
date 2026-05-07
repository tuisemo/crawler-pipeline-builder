"""Readability-lxml based content extractor.

Uses Mozilla's Readability algorithm to extract the main article content
from a full page.  This is the primary extractor for detail pages because
the algorithm is purpose-built for identifying the "reader view" content
and handles non-standard class names, sidebars, and navigation gracefully.
"""

from __future__ import annotations

import importlib.util
import re
from urllib.parse import urljoin

from page_extractor.core.types import ExtractorResult, ExtractorStrategy
from page_extractor.extractors.base import BaseExtractor


class ReadabilityLxmlExtractor(BaseExtractor):
    """Extract content using readability-lxml (Mozilla Readability port)."""

    def extract(self, html_content: str, url: str | None = None) -> ExtractorResult:
        if not self.is_available():
            return ExtractorResult(markdown="", strategy=ExtractorStrategy.READABILITY_LXML)
        try:
            from readability import Document

            doc = Document(html_content, url=url)
            article_html = doc.summary(html_partial=True)
            title = doc.title() or ""
            markdown = self._html_to_markdown(article_html, title, url)
            return ExtractorResult(
                markdown=self._fix_relative_urls(markdown, url or ""),
                strategy=ExtractorStrategy.READABILITY_LXML,
            )
        except Exception:
            return ExtractorResult(markdown="", strategy=ExtractorStrategy.READABILITY_LXML)

    def is_available(self) -> bool:
        return importlib.util.find_spec("readability") is not None

    # ------------------------------------------------------------------
    # HTML → Markdown conversion (kept simple; trafilatura/bs4 handle the
    # heavy lifting for well-formed HTML).
    # ------------------------------------------------------------------

    def _html_to_markdown(self, html_str: str, title: str, url: str | None) -> str:
        from bs4 import BeautifulSoup, NavigableString, Tag

        soup = BeautifulSoup(html_str, "html.parser")
        lines: list[str] = []

        if title:
            lines.append(f"# {title}")
            lines.append("")

        self._walk(soup, lines, depth=0)
        text = "\n".join(lines).strip()
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _walk(self, node, lines: list[str], depth: int) -> None:
        from bs4 import NavigableString, Tag

        if isinstance(node, NavigableString):
            t = str(node).strip()
            if t:
                lines.append(t)
            return

        if not isinstance(node, Tag):
            return

        tag = node.name.lower()

        if tag in ("script", "style", "noscript"):
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text = node.get_text(" ", strip=True)
            if text:
                lines.append("")
                lines.append(f"{'#' * level} {text}")
                lines.append("")
            return

        if tag == "p":
            text = node.get_text(" ", strip=True)
            if text:
                lines.append("")
                lines.append(text)
            return

        if tag in ("ul", "ol"):
            lines.append("")
            for i, li in enumerate(node.find_all("li", recursive=False)):
                prefix = f"{i + 1}. " if tag == "ol" else "- "
                text = li.get_text(" ", strip=True)
                if text:
                    lines.append(f"{prefix}{text}")
            lines.append("")
            return

        if tag == "table":
            lines.append("")
            rows = node.find_all("tr")
            for row in rows:
                cells = row.find_all(["th", "td"])
                cell_texts = [c.get_text(" ", strip=True) for c in cells]
                lines.append("| " + " | ".join(cell_texts) + " |")
            lines.append("")
            return

        if tag == "img":
            src = node.get("src", "") or node.get("data-src", "")
            alt = node.get("alt", "")
            if src:
                lines.append(f"![{alt}]({src})")
            return

        if tag == "br":
            lines.append("")
            return

        if tag == "hr":
            lines.append("\n---\n")
            return

        if tag in ("b", "strong"):
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(f"**{text}**")
            return

        if tag in ("i", "em"):
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(f"*{text}*")
            return

        if tag == "a":
            text = node.get_text(" ", strip=True)
            href = node.get("href", "")
            if text and href:
                lines.append(f"[{text}]({href})")
            elif text:
                lines.append(text)
            return

        for child in node.children:
            self._walk(child, lines, depth + 1)

    # ------------------------------------------------------------------

    def _fix_relative_urls(self, markdown: str, base_url: str) -> str:
        if not markdown or not base_url:
            return markdown

        def fix_image(match: re.Match[str]) -> str:
            alt = match.group(1) or ""
            src = match.group(2) or ""
            if src and not src.startswith(("http://", "https://", "data:", "blob:")):
                src = urljoin(base_url, src)
            return f"![{alt}]({src})"

        return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', fix_image, markdown)
