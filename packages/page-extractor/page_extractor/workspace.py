"""Workspace helpers for detail extraction tasks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DetailWorkspace:
    def __init__(self, output_root: str | Path, task_id: str):
        self.output_root = Path(output_root).resolve()
        self.task_id = task_id
        self.task_dir = self.output_root / task_id
        self.logs_dir = self.task_dir / "logs"
        self.attachments_dir = self.task_dir / "attachments"

    def ensure(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def markdown_path(self) -> Path:
        return self.task_dir / "content.md"

    @property
    def pdf_path(self) -> Path:
        return self.task_dir / "page.pdf"

    @property
    def summary_path(self) -> Path:
        return self.task_dir / "summary.json"

    @property
    def metadata_path(self) -> Path:
        return self.task_dir / "metadata.json"

    @property
    def log_path(self) -> Path:
        return self.logs_dir / "collect.log"

    def write_markdown(self, content: str) -> Path:
        self.markdown_path.write_text(content, encoding="utf-8")
        return self.markdown_path

    def write_summary(self, summary: dict[str, Any]) -> Path:
        self.summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self.summary_path

    def write_metadata(self, metadata: dict[str, Any]) -> Path:
        self.metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self.metadata_path
