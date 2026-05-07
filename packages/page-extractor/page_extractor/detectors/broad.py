"""Content-area detector using structural scoring algorithms.

Finds the main content container on a page using purely algorithmic
scoring based on text density, heading structure, paragraph count,
link density, and content-to-tag ratio.  No keyword matching.

Returns an XPath expression that uniquely identifies the detected
content area.  The same XPath is used for markdown extraction, PDF
snapshot, and attachment discovery -- a single source of truth.
"""

from __future__ import annotations

import re

from page_extractor.core.types import DetectorResult, DetectorStrategy
from page_extractor.detectors.base import BaseDetector

# Minimum raw text length to be considered a content candidate.
MIN_TEXT = 150


class BroadDetector(BaseDetector):
    """Detect the main content area algorithmically."""

    def is_available(self) -> bool:
        try:
            import lxml  # noqa: F401
            return True
        except Exception:
            return False

    def detect(self, html_content: str, url: str | None = None) -> DetectorResult:
        fallback = DetectorResult(
            content_area="/html/body", confidence=0.0, text_length=0,
            strategy=DetectorStrategy.BROAD,
        )
        if not html_content:
            return fallback
        try:
            from lxml import html, etree
            tree = html.fromstring(html_content)
            doc = etree.ElementTree(tree)
        except Exception:
            return fallback

        candidates: list[tuple[object, float, int]] = []
        for element in tree.iter("div", "section", "article", "main"):
            text = self._text(element)
            text_len = len(text)
            if text_len < MIN_TEXT:
                continue
            score = self._score(element, text_len)
            candidates.append((element, score, text_len))

        if not candidates:
            return fallback

        scored = [(e, s, t) for e, s, t in candidates if s > 0]
        if not scored:
            scored = candidates

        scored.sort(key=lambda item: item[2], reverse=True)
        best_el, best_score, best_len = scored[0]

        xpath = doc.getpath(best_el)
        confidence = min(0.9, best_score / 80 + 0.2) if best_score > 0 else 0.3

        return DetectorResult(
            content_area=xpath,
            confidence=round(confidence, 2),
            text_length=best_len,
            strategy=DetectorStrategy.BROAD,
            element_info={"tag": best_el.tag, "class": best_el.get("class"), "id": best_el.get("id")},
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _text(element) -> str:
        from lxml import html as _html
        copy = _html.fromstring(_html.tostring(element))
        for tag in copy.cssselect("script, style, nav, footer, aside"):
            parent = tag.getparent()
            if parent is not None:
                parent.remove(tag)
        return re.sub(r"\s+", " ", copy.text_content() or "").strip()

    @staticmethod
    def _score(element, text_len: int) -> float:
        """Purely structural scoring -- no keyword matching."""
        score = 0.0
        # Text length reward
        if text_len >= 2000:
            score += 30
        elif text_len >= 800:
            score += 20
        elif text_len >= 300:
            score += 10

        # Headings inside the element
        h_count = len(element.cssselect("h1, h2, h3, h4, h5, h6"))
        score += min(20, h_count * 7)

        # Paragraphs
        p_count = len(element.cssselect("p"))
        score += min(15, p_count * 3)

        # Images
        img_count = len(element.cssselect("img"))
        score += min(10, img_count * 3)

        # Tables
        table_count = len(element.cssselect("table"))
        score += min(10, table_count * 5)

        # Content-to-tag ratio (higher = more text per tag = more content-like)
        tag_count = len(list(element.iter()))
        if tag_count > 0:
            ratio = text_len / tag_count
            if ratio >= 30:
                score += 15
            elif ratio >= 15:
                score += 10

        # Link density penalty (navigation/sidebar have high link density)
        link_text = sum(len(lt.text_content() or "") for lt in element.cssselect("a"))
        if text_len > 0:
            ld = link_text / text_len
            if ld > 0.6:
                score -= 30
            elif ld > 0.4:
                score -= 15

        return max(0.0, score)
