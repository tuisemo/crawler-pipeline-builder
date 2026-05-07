"""Base extractor interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from page_extractor.core.types import ExtractorResult


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, html_content: str, url: str | None = None) -> ExtractorResult:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

