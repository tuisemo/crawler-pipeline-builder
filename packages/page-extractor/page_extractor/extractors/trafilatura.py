"""Trafilatura-based content extraction with fallback."""

from __future__ import annotations

import importlib.util
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from page_extractor.core.types import ExtractorResult, ExtractorStrategy
from page_extractor.extractors.base import BaseExtractor


class TrafilaturaExtractor(BaseExtractor):
    def extract(self, html_content: str, url: str | None = None) -> ExtractorResult:
        if self.is_available():
            try:
                from trafilatura import extract

                markdown = extract(
                    html_content,
                    url=url,
                    output_format="markdown",
                    favor_precision=False,
                    favor_recall=True,
                    include_links=True,
                    include_images=True,
                    include_formatting=True,
                    include_tables=True,
                ) or ""
                return ExtractorResult(markdown=self._fix_relative_urls(markdown, url or ""), strategy=ExtractorStrategy.TRAFILATURA)
            except Exception:
                pass
        return ExtractorResult(markdown=self._basic_extract(html_content, url), strategy=ExtractorStrategy.BASIC)

    def is_available(self) -> bool:
        return importlib.util.find_spec("trafilatura") is not None

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

    def _basic_extract(self, html_content: str, url: str | None) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
        container = soup.find("article") or soup.find("main") or soup.body or soup
        parts = []
        for node in container.find_all(["h1", "h2", "h3", "p", "li"]):
            text = node.get_text(" ", strip=True)
            if text:
                parts.append(text)
        lines = []
        if title:
            lines.append(f"# {title}")
            lines.append("")
        if url:
            lines.append(f"Source: {url}")
            lines.append("")
        lines.append("\n\n".join(parts[:200]).strip() or "(empty content)")
        lines.append("")
        return "\n".join(lines)

