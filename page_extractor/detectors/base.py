"""Detector interfaces for detail extraction."""

from __future__ import annotations

from abc import ABC, abstractmethod

from page_extractor.core.types import DetectorResult


class BaseDetector(ABC):
    @abstractmethod
    def detect(self, html_content: str, url: str | None = None) -> DetectorResult:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

