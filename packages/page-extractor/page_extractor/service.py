"""详情页采集应用服务包装器 (Application service wrapper)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from page_extractor.core.pipeline import CollectorPipeline
from page_extractor.core.types import CollectorConfig, DetectorStrategy, ExtractorStrategy, PageLoadStrategy
from .types import DETAIL_CLI_VERSION, DetailCollectionRequest, DetailCollectionSummary


class DetailCollectionService:
    """详情页采集服务，作为核心运行时与 CLI 之间的适配层。"""

    @staticmethod
    def _is_valid_detail_url(url: str) -> bool:
        """检查 URL 是否为合法的 http/https 协议。"""
        if not isinstance(url, str) or not url.strip():
            return False
        parsed = urlparse(url.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def build_config(self, request: DetailCollectionRequest) -> CollectorConfig:
        """根据请求参数构建底层采集器配置。"""
        return CollectorConfig(
            output_dir=Path(request.output_root),
            detector_strategy=DetectorStrategy(request.detector_strategy),
            extractor_strategy=ExtractorStrategy(request.extractor_strategy),
            page_load_strategy=PageLoadStrategy(request.page_load_strategy),
            timeout=request.timeout,
            log_level=request.log_level,
            save_markdown=request.save_markdown,
            save_html=getattr(request, "save_html", False),
            save_pdf=request.save_pdf,
            save_meta_json=getattr(request, "save_meta_json", False),
            download_attachments=request.download_attachments,
            headless=request.headless,
            content_area_hint=getattr(request, "content_area_hint", None),
            extra_wait=getattr(request, "extra_wait", 0),
        )

    def collect(self, request: DetailCollectionRequest) -> DetailCollectionSummary:
        """执行采集任务并返回结构化摘要。"""
        # 1. 验证 URL 合法性
        if not self._is_valid_detail_url(request.url):
            return self._handle_error(request, "invalid_url", "detail_url must be a valid http/https URL")

        # 2. 调用核心 Pipeline 执行采集
        try:
            collector = CollectorPipeline(output_dir=str(Path(request.output_root)))
            config = self.build_config(request)
            result = collector.collect(request.url, config, task_id=request.task_id)
            
            # 3. 构造并保存任务摘要
            task_dir = Path(result.task_dir)
            summary = DetailCollectionSummary(
                status="success" if result.status == "success" else "failed",
                task_id=result.task_id,
                detail_url=result.url,
                task_dir=str(task_dir),
                result_summary_path=str(task_dir / "summary.json"),
                content_markdown_path=str(task_dir / "content.md") if (task_dir / "content.md").exists() else None,
                content_html_path=str(task_dir / "content.html") if (task_dir / "content.html").exists() else None,
                pdf_snapshot_path=str(task_dir / "page.pdf") if (task_dir / "page.pdf").exists() else None,
                attachments_dir=str(task_dir / "attachments") if (task_dir / "attachments").exists() else None,
                attachment_discovered_count=result.attachment_discovered_count,
                attachment_downloaded_count=result.attachment_downloaded_count,
                detail_cli_version=DETAIL_CLI_VERSION,
                error_code=None if result.status == "success" else "collection_error",
                error_message=result.error,
                started_at=result.started_at,
                completed_at=result.completed_at,
            )
            self._save_summary(summary, task_dir)
            return summary
        except Exception as exc:
            return self._handle_error(request, "collection_error", str(exc))

    def _handle_error(self, request: DetailCollectionRequest, code: str, message: str) -> DetailCollectionSummary:
        """统一处理错误情况并生成失败摘要。"""
        task_dir = Path(request.output_root).resolve() / (request.task_id or "unknown")
        task_dir.mkdir(parents=True, exist_ok=True)
        
        summary = DetailCollectionSummary(
            status="failed",
            task_id=request.task_id or "unknown",
            detail_url=request.url,
            task_dir=str(task_dir),
            result_summary_path=str(task_dir / "summary.json"),
            content_markdown_path=None,
            content_html_path=None,
            pdf_snapshot_path=None,
            attachments_dir=None,
            attachment_discovered_count=0,
            attachment_downloaded_count=0,
            detail_cli_version=DETAIL_CLI_VERSION,
            error_code=code,
            error_message=message,
            started_at="",
            completed_at="",
        )
        self._save_summary(summary, task_dir)
        return summary

    def _save_summary(self, summary: DetailCollectionSummary, task_dir: Path) -> None:
        """将摘要信息持久化到 summary.json。"""
        summary_path = task_dir / "summary.json"
        summary_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        
        # 同时保存一个简化的元数据文件，供外部监控使用
        metadata_path = task_dir / "metadata.json"
        if not metadata_path.exists():
            meta = {
                "status": summary.status,
                "task_id": summary.task_id,
                "detail_url": summary.detail_url,
                "error_code": summary.error_code,
                "detail_cli_version": DETAIL_CLI_VERSION,
            }
            metadata_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
