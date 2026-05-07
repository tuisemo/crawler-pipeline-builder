"""任务工作空间管理工具 (Task workspace helpers)."""

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
    """管理单次采集任务的文件输出与目录结构。"""
    output_dir: Path
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    date_str: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    save_meta_json: bool = False
    task_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        """初始化任务目录。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.task_dir = self.output_dir / self.task_id
        self.task_dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_path(self) -> Path:
        """返回任务日志文件的路径。"""
        logs_dir = self.task_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir / "collect.log"

    def create_result(self, url: str) -> CollectorResult:
        """初始化一个采集结果对象。"""
        return CollectorResult(
            status="failed",
            task_id=self.task_id,
            url=url,
            task_dir=self.task_dir,
            started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def write_markdown(self, markdown: str, source_url: str) -> Path:
        """写入正文 Markdown 并生成元数据。"""
        path = self.task_dir / "content.md"
        path.write_text(markdown or "", encoding="utf-8")
        if self.save_meta_json:
            generate_meta_json(path, source_url, self.date_str)
        return path

    def write_html(self, html_content: str, source_url: str) -> Path:
        """写入限定范围后的 HTML 快照并生成元数据。"""
        path = self.task_dir / "content.html"
        path.write_text(html_content or "", encoding="utf-8")
        if self.save_meta_json:
            generate_meta_json(path, source_url, self.date_str)
        return path

    def write_pdf_metadata(self, pdf_path: Path, source_url: str) -> None:
        """为生成的 PDF 文件补充元数据。"""
        if self.save_meta_json:
            generate_meta_json(pdf_path, source_url, self.date_str)

    def attachments_dir(self) -> Path:
        """创建并返回附件存放目录。"""
        path = self.task_dir / "attachments"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_result_metadata(self, result: CollectorResult) -> None:
        """将完整的任务执行结果保存为 metadata.json。"""
        path = self.task_dir / "metadata.json"
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

