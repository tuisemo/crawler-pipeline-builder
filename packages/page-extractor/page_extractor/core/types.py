"""Core types for detail extraction runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class PageLoadStrategy(StrEnum):
    NETWORK_IDLE = "networkidle"
    DOM_CONTENT_LOADED = "domcontentloaded"
    SMART = "smart"


class DetectorStrategy(StrEnum):
    HEURISTIC = "heuristic"
    READABILITY = "readability"
    BROAD = "broad"
    AUTO = "auto"


class ExtractorStrategy(StrEnum):
    TRAFILATURA = "trafilatura"
    READABILITY_LXML = "readability_lxml"
    BASIC = "basic"
    AUTO = "auto"


@dataclass
class CollectorConfig:
    output_dir: Path
    detector_strategy: DetectorStrategy = DetectorStrategy.AUTO
    extractor_strategy: ExtractorStrategy = ExtractorStrategy.AUTO
    page_load_strategy: PageLoadStrategy = PageLoadStrategy.SMART
    timeout: int = 180
    log_level: str = "INFO"
    save_markdown: bool = True
    save_html: bool = False
    save_pdf: bool = False
    save_meta_json: bool = False
    download_attachments: bool = False
    headless: bool = True  # 是否使用无头模式
    content_area_hint: str | None = None
    extra_wait: float = 0
    attachment_extensions: frozenset[str] = field(default_factory=lambda: frozenset({
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".rar", ".7z", ".tar", ".gz",
        ".csv", ".txt", ".rtf", ".odt", ".ods",
    }))
    max_file_size: int = 500 * 1024 * 1024
    download_timeout: int = 200
    max_concurrent_downloads: int = 3
    pdf_margin: str = "10mm"
    pdf_format: str = "A4"


@dataclass
class DetectorResult:
    content_area: str
    confidence: float
    text_length: int
    strategy: DetectorStrategy
    element_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractorResult:
    markdown: str
    strategy: ExtractorStrategy


@dataclass
class CollectorResult:
    status: str
    task_id: str
    url: str
    task_dir: Path
    artifacts: list[str] = field(default_factory=list)
    content_area: str | None = None
    content_area_confidence: float = 0.0
    detector_strategy: DetectorStrategy = DetectorStrategy.HEURISTIC
    markdown_length: int = 0
    extractor_strategy: ExtractorStrategy = ExtractorStrategy.TRAFILATURA
    attachment_count: int = 0
    attachment_discovered_count: int = 0
    attachment_downloaded_count: int = 0
    error: str | None = None
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "task_id": self.task_id,
            "url": self.url,
            "task_dir": str(self.task_dir),
            "artifacts": self.artifacts,
            "content_area": self.content_area,
            "content_area_confidence": self.content_area_confidence,
            "detector_strategy": self.detector_strategy.value,
            "markdown_length": self.markdown_length,
            "extractor_strategy": self.extractor_strategy.value,
            "attachment_count": self.attachment_count,
            "attachment_discovered_count": self.attachment_discovered_count,
            "attachment_downloaded_count": self.attachment_downloaded_count,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
