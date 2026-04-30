"""Heuristic content selector detector."""

from __future__ import annotations

import re

from page_extractor.core.types import DetectorResult, DetectorStrategy
from page_extractor.detectors.base import BaseDetector


class HeuristicDetector(BaseDetector):
    DEFAULT_CANDIDATE_SELECTORS = [
        "main", "article", "#content", ".content", ".post", ".article",
        "[role='main']", "#main", ".main", ".entry-content", "#article",
        ".article-content", "#post-content", ".post-content", ".page-content",
    ]
    HIGH_CONFIDENCE_TAGS = {"main", "article"}
    MEDIUM_CONFIDENCE_TAGS = {"section", "div"}
    CONTENT_KEYWORDS = {"content", "article", "post", "entry", "main", "story", "body", "text", "news", "blog"}

    def __init__(self, min_text_length: int = 200):
        self.min_text_length = min_text_length
        self.candidate_selectors = self.DEFAULT_CANDIDATE_SELECTORS.copy()

    def detect(self, html_content: str, url: str | None = None) -> DetectorResult:
        fallback = DetectorResult(css_selector="body", confidence=0.0, text_length=0, strategy=DetectorStrategy.HEURISTIC)
        if not html_content:
            return fallback
        try:
            from lxml import html

            tree = html.fromstring(html_content)
        except Exception:
            return fallback

        best_result = None
        best_score = -1.0
        for selector in self.candidate_selectors:
            try:
                elements = tree.cssselect(selector)
            except Exception:
                continue
            for element in elements:
                score = self._score_element(element)
                if score > best_score:
                    best_score = score
                    best_result = (selector, element, score)

        if best_result is None or best_score < 30:
            dynamic = self._discover_content_elements(tree)
            if dynamic and dynamic[2] > best_score:
                best_result = dynamic

        if best_result is None:
            return fallback

        selector, element, raw_score = best_result
        text_length = len(self._extract_text(element))
        confidence = self._calculate_confidence(raw_score, text_length)
        return DetectorResult(
            css_selector=selector,
            confidence=confidence,
            text_length=text_length,
            strategy=DetectorStrategy.HEURISTIC,
            element_info={"tag": element.tag, "class": element.get("class"), "id": element.get("id")},
        )

    def is_available(self) -> bool:
        try:
            import lxml  # noqa: F401

            return True
        except Exception:
            return False

    def _score_element(self, element) -> float:
        score = 0.0
        text = self._extract_text(element)
        text_length = len(text)
        if text_length < self.min_text_length:
            return 0.0
        if text_length < 1000:
            score += 20 * (text_length / 1000)
        elif text_length <= 5000:
            score += 40
        else:
            score += 40 - min(20, (text_length - 5000) / 10000)

        p_count = len(element.cssselect("p"))
        if p_count >= 5:
            score += 25
        elif p_count >= 3:
            score += 20
        elif p_count >= 1:
            score += 10 + p_count * 3

        link_density = self._calculate_link_density(element)
        if link_density < 0.1:
            score += 20
        elif link_density < 0.3:
            score += 15
        elif link_density < 0.5:
            score += 10
        else:
            score -= 10

        tag = element.tag.lower()
        if tag in self.HIGH_CONFIDENCE_TAGS:
            score += 20
        elif tag in self.MEDIUM_CONFIDENCE_TAGS:
            score += 10

        class_attr = element.get("class", "")
        id_attr = element.get("id", "")
        class_words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9]*", class_attr.lower()))
        id_words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9]*", id_attr.lower()))
        score += min(15, len((class_words | id_words) & self.CONTENT_KEYWORDS) * 5)
        score -= len((class_words | id_words) & {"nav", "menu", "sidebar", "footer", "header", "comment", "ad"}) * 15
        return max(0.0, score)

    def _discover_content_elements(self, tree):
        candidates = []
        for element in tree.iter("div", "section"):
            score = self._score_element(element)
            if score > 30:
                candidates.append((self._generate_selector(element), element, score))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[2], reverse=True)
        return candidates[0]

    def _generate_selector(self, element) -> str:
        if element.get("id"):
            return f"#{element.get('id')}"
        classes = element.get("class")
        if classes:
            return f"{element.tag}.{'.'.join(classes.split()[:2])}"
        return element.tag

    def _calculate_link_density(self, element) -> float:
        total_text = self._extract_text(element)
        total_length = len(total_text)
        if total_length == 0:
            return 0.0
        link_text_length = sum(len(self._extract_text(link)) for link in element.cssselect("a"))
        return link_text_length / total_length

    def _extract_text(self, element) -> str:
        from lxml import html

        element_copy = html.fromstring(html.tostring(element))
        for tag in ["script", "style", "nav", "header", "footer", "aside"]:
            for el in element_copy.cssselect(tag):
                el.drop_tree()
        return re.sub(r"\s+", " ", element_copy.text_content()).strip()

    def _calculate_confidence(self, raw_score: float, text_length: int) -> float:
        if text_length < self.min_text_length:
            return 0.0
        normalized = min(1.0, raw_score / 100)
        if text_length < 1000:
            normalized *= 0.6
        elif text_length < 2000:
            normalized *= 0.8
        return round(normalized, 2)

