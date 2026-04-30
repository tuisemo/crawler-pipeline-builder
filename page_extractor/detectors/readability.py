"""Readability-like selector detector."""

from __future__ import annotations

import re

from page_extractor.core.types import DetectorResult, DetectorStrategy
from page_extractor.detectors.base import BaseDetector


class ReadabilityDetector(BaseDetector):
    def is_available(self) -> bool:
        try:
            import lxml  # noqa: F401

            return True
        except Exception:
            return False

    def detect(self, html_content: str, url: str | None = None) -> DetectorResult:
        if not html_content:
            return DetectorResult(css_selector="body", confidence=0.0, text_length=0, strategy=DetectorStrategy.READABILITY)
        try:
            from lxml import html

            tree = html.fromstring(html_content)
        except Exception:
            return DetectorResult(css_selector="body", confidence=0.0, text_length=0, strategy=DetectorStrategy.READABILITY)
        candidates = []
        for element in tree.iter("div", "section", "article", "main"):
            score = self._score_element(element)
            if score > 20:
                selector = self._generate_selector(element)
                text_len = len(self._get_text_content(element))
                candidates.append((selector, element, score, text_len))
        if not candidates:
            return DetectorResult(css_selector="body", confidence=0.1, text_length=0, strategy=DetectorStrategy.READABILITY)
        candidates.sort(key=lambda item: item[2], reverse=True)
        best = candidates[0]
        confidence = min(0.95, best[2] / 100 + 0.2)
        return DetectorResult(
            css_selector=best[0],
            confidence=round(confidence, 2),
            text_length=best[3],
            strategy=DetectorStrategy.READABILITY,
            element_info={"tag": best[1].tag, "class": best[1].get("class"), "id": best[1].get("id")},
        )

    def _score_element(self, element) -> float:
        score = 0.0
        text = self._get_text_content(element)
        text_length = len(text)
        if text_length < 25:
            return 0.0
        paragraphs = element.findall(".//p")
        if paragraphs:
            avg_len = text_length / max(1, len(paragraphs))
            if 10 <= avg_len <= 30:
                score += 25
            elif avg_len > 30:
                score += 15
        score += min(25, len(paragraphs) * 3)
        class_id = (element.get("class", "") + " " + element.get("id", "")).lower()
        for keyword in {"article", "body", "content", "entry", "main", "page", "post", "text", "blog", "story"}:
            if keyword in class_id:
                score += 25
        for keyword in {"comment", "footer", "hidden", "menu", "nav", "sidebar", "widget", "ad", "popup"}:
            if keyword in class_id:
                score -= 25
        score -= self._calculate_link_density(element) * 50
        score -= 5 * len(element.findall(".//table"))
        return max(0.0, score)

    def _get_text_content(self, element) -> str:
        for tag in element.iter("script", "style"):
            if tag.getparent() is not None:
                tag.getparent().remove(tag)
        return re.sub(r"\s+", " ", element.text_content() or "").strip()

    def _calculate_link_density(self, element) -> float:
        text = self._get_text_content(element)
        if not text:
            return 0.0
        link_text_length = sum(len(self._get_text_content(link)) for link in element.iter("a"))
        return link_text_length / len(text)

    def _generate_selector(self, element) -> str:
        if element.get("id"):
            return f"#{element.get('id')}"
        classes = element.get("class")
        if classes:
            return f"{element.tag}.{'.'.join(classes.split()[:2])}"
        return element.tag

