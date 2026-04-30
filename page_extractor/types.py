"""Runtime types for the detail extractor CLI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DETAIL_CLI_VERSION = "0.1.0"


@dataclass(slots=True)
class DetailCollectionRequest:
    url: str
    task_id: str
    output_root: str | Path
    timeout: int = 180
    detector_strategy: str = "auto"
    extractor_strategy: str = "auto"
    page_load_strategy: str = "smart"
    save_markdown: bool = True
    save_pdf: bool = False
    download_attachments: bool = False
    log_level: str = "INFO"
    format: str = "json"


@dataclass(slots=True)
class DetailCollectionSummary:
    status: str
    task_id: str
    detail_url: str
    task_dir: str
    result_summary_path: str
    content_markdown_path: str | None
    pdf_snapshot_path: str | None
    attachments_dir: str | None
    attachment_discovered_count: int
    attachment_downloaded_count: int
    detail_cli_version: str
    error_code: str | None
    error_message: str | None
    started_at: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
