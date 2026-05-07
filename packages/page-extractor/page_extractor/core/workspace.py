"""Task workspace helpers for detail extraction runtime."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from page_extractor.core.types import CollectorResult
from page_extractor.utils import generate_meta_json


@dataclass
class CollectionWorkspace:
    output_dir: Path
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    date_str: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    task_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.task_dir = self.output_dir / self.task_id
        self.task_dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_path(self) -> Path:
        logs_dir = self.task_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir / "collect.log"

    def create_result(self, url: str) -> CollectorResult:
        return CollectorResult(
            status="failed",
            task_id=self.task_id,
            url=url,
            task_dir=self.task_dir,
            started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def write_markdown(self, markdown: str, source_url: str) -> Path:
        path = self.task_dir / "content.md"
        path.write_text(markdown or "", encoding="utf-8")
        generate_meta_json(path, source_url, self.date_str)
        return path

    def write_html(self, html_content: str, source_url: str) -> Path:
        path = self.task_dir / "content.html"
        path.write_text(html_content or "", encoding="utf-8")
        generate_meta_json(path, source_url, self.date_str)
        return path

    def write_pdf_metadata(self, pdf_path: Path, source_url: str) -> None:
        generate_meta_json(pdf_path, source_url, self.date_str)

    def attachments_dir(self) -> Path:
        path = self.task_dir / "attachments"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_result_metadata(self, result: CollectorResult) -> None:
        path = self.task_dir / "metadata.json"
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

