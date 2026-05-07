"""Application service wrapper for the detail extraction runtime."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from page_extractor.core.pipeline import CollectorPipeline
from page_extractor.core.types import CollectorConfig, DetectorStrategy, ExtractorStrategy, PageLoadStrategy
from .types import DETAIL_CLI_VERSION, DetailCollectionRequest, DetailCollectionSummary


class DetailCollectionService:
    """Application service over the detail extraction runtime."""

    @staticmethod
    def _is_valid_detail_url(url: str) -> bool:
        if not isinstance(url, str) or not url.strip():
            return False
        parsed = urlparse(url.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def build_config(self, request: DetailCollectionRequest) -> CollectorConfig:
        detector_strategy = DetectorStrategy(request.detector_strategy)
        extractor_strategy = ExtractorStrategy(request.extractor_strategy)
        page_load_strategy = PageLoadStrategy(request.page_load_strategy)
        return CollectorConfig(
            output_dir=Path(request.output_root),
            detector_strategy=detector_strategy,
            extractor_strategy=extractor_strategy,
            page_load_strategy=page_load_strategy,
            timeout=request.timeout,
            log_level=request.log_level,
            save_markdown=request.save_markdown,
            save_html=getattr(request, "save_html", False),
            save_pdf=request.save_pdf,
            download_attachments=request.download_attachments,
            content_area_hint=getattr(request, "content_area_hint", None),
            extra_wait=getattr(request, "extra_wait", 0),
        )

    def collect(self, request: DetailCollectionRequest) -> DetailCollectionSummary:
        if not self._is_valid_detail_url(request.url):
            task_dir = Path(request.output_root).resolve() / request.task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            summary_path = task_dir / "summary.json"
            metadata_path = task_dir / "metadata.json"
            summary = DetailCollectionSummary(
                status="failed",
                task_id=request.task_id,
                detail_url=request.url,
                task_dir=str(task_dir),
                result_summary_path=str(summary_path),
                content_markdown_path=None,
                content_html_path=None,
                pdf_snapshot_path=None,
                attachments_dir=None,
                attachment_discovered_count=0,
                attachment_downloaded_count=0,
                detail_cli_version=DETAIL_CLI_VERSION,
                error_code="invalid_url",
                error_message="detail_url must be a valid http/https URL",
                started_at="",
                completed_at="",
            )
            summary_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            metadata_path.write_text(
                json.dumps(
                    {
                        "status": summary.status,
                        "task_id": summary.task_id,
                        "detail_url": summary.detail_url,
                        "error_code": summary.error_code,
                        "error_message": summary.error_message,
                        "detail_cli_version": DETAIL_CLI_VERSION,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return summary
        collector = CollectorPipeline(output_dir=str(Path(request.output_root)))
        config = self.build_config(request)
        result = collector.collect(request.url, config, task_id=request.task_id)

        task_dir = Path(result.task_dir)
        summary_path = task_dir / "summary.json"
        markdown_path = task_dir / "content.md"
        pdf_path = task_dir / "page.pdf"
        attachments_dir = task_dir / "attachments"

        summary = DetailCollectionSummary(
            status="success" if result.status == "success" else "failed",
            task_id=result.task_id,
            detail_url=result.url,
            task_dir=str(task_dir),
            result_summary_path=str(summary_path),
            content_markdown_path=str(markdown_path) if markdown_path.exists() else None,
            content_html_path=str(task_dir / "content.html") if (task_dir / "content.html").exists() else None,
            pdf_snapshot_path=str(pdf_path) if pdf_path.exists() else None,
            attachments_dir=str(attachments_dir) if attachments_dir.exists() else None,
            attachment_discovered_count=result.attachment_discovered_count,
            attachment_downloaded_count=result.attachment_downloaded_count,
            detail_cli_version=DETAIL_CLI_VERSION,
            error_code=None if result.status == "success" else "collection_error",
            error_message=result.error,
            started_at=result.started_at,
            completed_at=result.completed_at,
        )
        summary_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return summary
