"""Detail extraction pipeline adapted into the current project."""

from __future__ import annotations

import mimetypes
import os
import re
import warnings
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import requests

from page_extractor.core.attachments import AttachmentService
from page_extractor.core.browser_session import (
    DEFAULT_STEALTH_SCRIPT,
    DEFAULT_USER_AGENT,
    BrowserSessionFactory,
    PageNavigator,
)
from page_extractor.core.types import (
    CollectorConfig,
    CollectorResult,
    DetectorResult,
    DetectorStrategy,
    ExtractorResult,
    ExtractorStrategy,
)
from page_extractor.core.workspace import CollectionWorkspace
from page_extractor.detectors.heuristic import HeuristicDetector
from page_extractor.detectors.readability import ReadabilityDetector
from page_extractor.downloader.multi_strategy import download_file
from page_extractor.extractors.trafilatura import TrafilaturaExtractor
from page_extractor.snapshot.pdf import snapshot_element
from page_extractor.utils import generate_meta_json, process_archive, sanitize_filename, setup_logging
from page_extractor.utils.logging import get_logger
from page_extractor.utils.tls import insecure_request_warning, ssl_verify_enabled


class CollectorPipeline:
    def __init__(self, output_dir: str = "./output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = CollectorConfig(output_dir=self.output_dir)
        self._page_navigator = PageNavigator()
        self._attachment_service = AttachmentService(self.config)
        self._browser_factory = BrowserSessionFactory(user_agent=DEFAULT_USER_AGENT, stealth_script=DEFAULT_STEALTH_SCRIPT)
        self._detectors = {
            DetectorStrategy.HEURISTIC: HeuristicDetector(),
            DetectorStrategy.READABILITY: ReadabilityDetector(),
        }
        self._extractors = {
            ExtractorStrategy.TRAFILATURA: TrafilaturaExtractor(),
            ExtractorStrategy.BASIC: TrafilaturaExtractor(),
        }

    def collect(self, url: str, config: CollectorConfig | None = None, *, task_id: str | None = None) -> CollectorResult:
        logger = get_logger()
        if config:
            self.config = config
            self._attachment_service.update_config(config)
        workspace = CollectionWorkspace(output_dir=self.output_dir, task_id=task_id or uuid4().hex)
        setup_logging(log_level=self.config.log_level, log_file=workspace.log_path)
        result = workspace.create_result(url)
        task_id = workspace.task_id
        logger.info("[%s] Starting detail collection: %s", task_id, url)
        logger.info("[%s] Output directory: %s", task_id, workspace.task_dir)

        if self._check_direct_download(url, workspace.task_dir, workspace.date_str, task_id):
            result.status = "success"
            result.artifacts.append("(direct file download)")
            result.completed_at = self._now()
            workspace.save_result_metadata(result)
            return result

        try:
            with self._browser_factory.create() as browser_session:
                self._collect_browser_artifacts(
                    url=url,
                    workspace=workspace,
                    result=result,
                    page=browser_session.page,
                    context=browser_session.context,
                )
            result.status = "success"
            result.completed_at = self._now()
            workspace.save_result_metadata(result)
            logger.info("[%s] Detail collection complete", task_id)
        except Exception as exc:
            logger.exception("[%s] Detail collection failed: %s", task_id, exc)
            result.error = str(exc)
            result.completed_at = self._now()
            workspace.save_result_metadata(result)
        return result

    def _collect_browser_artifacts(self, *, url: str, workspace: CollectionWorkspace, result: CollectorResult, page, context) -> None:
        logger = get_logger()
        task_id = workspace.task_id
        self._page_navigator.load(page, url, strategy=self.config.page_load_strategy, task_id=task_id)
        self._page_navigator.handle_cookie_consent(page)
        try:
            page.wait_for_function("() => document.readyState === 'complete'", timeout=30000)
        except Exception as exc:
            logger.warning("[%s] Page render wait timeout: %s", task_id, exc)

        html_content = page.content()
        detector_result = self._detect_selector(html_content, url)
        selector = detector_result.css_selector
        result.selector = selector
        result.selector_confidence = detector_result.confidence
        result.detector_strategy = detector_result.strategy

        extraction_input = self._build_extraction_input(html_content=html_content, selector=selector, task_id=task_id)
        extractor_result = self._extract_content(extraction_input, url)
        markdown = extractor_result.markdown
        if self.config.save_markdown:
            workspace.write_markdown(markdown, url)
            result.artifacts.append("content.md")
        result.markdown_length = len(markdown) if markdown else 0
        result.extractor_strategy = extractor_result.strategy

        if self.config.save_pdf:
            pdf_path = workspace.task_dir / "page.pdf"
            if snapshot_element(page, selector, str(pdf_path), pdf_format=self.config.pdf_format, pdf_margin=self.config.pdf_margin):
                result.artifacts.append("page.pdf")
                workspace.write_pdf_metadata(pdf_path, url)

        attachments = self._attachment_service.extract_links(page, selector)
        downloaded_count = 0
        if self.config.download_attachments:
            workspace.attachments_dir()
            downloaded_count = self._attachment_service.download(
                attachments=attachments,
                context=context,
                workspace=workspace,
                referer_url=url,
            )
            if attachments:
                result.artifacts.append(f"attachments/ ({downloaded_count} files)")
        result.attachment_discovered_count = len(attachments) if attachments else 0
        result.attachment_downloaded_count = downloaded_count
        result.attachment_count = downloaded_count

    def _detect_selector(self, html_content: str, url: str) -> DetectorResult:
        if self.config.detector_strategy == DetectorStrategy.READABILITY and self._detectors[DetectorStrategy.READABILITY].is_available():
            return self._detectors[DetectorStrategy.READABILITY].detect(html_content, url)
        if self._detectors[DetectorStrategy.READABILITY].is_available():
            readability = self._detectors[DetectorStrategy.READABILITY].detect(html_content, url)
            if readability.confidence >= 0.3:
                return readability
        return self._detectors[DetectorStrategy.HEURISTIC].detect(html_content, url)

    def _extract_content(self, html_content: str, url: str) -> ExtractorResult:
        extractor = self._extractors[ExtractorStrategy.TRAFILATURA]
        result = extractor.extract(html_content, url)
        if result.markdown:
            return result
        return self._extractors[ExtractorStrategy.BASIC].extract(html_content, url)

    def _build_extraction_input(self, *, html_content: str, selector: str | None, task_id: str) -> str:
        logger = get_logger()
        if not selector:
            return html_content
        try:
            from lxml import html

            document = html.fromstring(html_content)
            matches = document.cssselect(selector)
            if not matches:
                return html_content
            scoped = html.tostring(matches[0], encoding="unicode")
            return scoped if scoped.strip() else html_content
        except Exception as exc:
            logger.warning("[%s] Failed to scope extraction input: %s", task_id, exc)
            return html_content

    def _check_direct_download(self, url: str, task_dir: Path, date_str: str, task_id: str) -> bool:
        logger = get_logger()
        try:
            request_kwargs = {"timeout": 15, "allow_redirects": True, "verify": ssl_verify_enabled()}
            with warnings.catch_warnings():
                if not request_kwargs["verify"]:
                    warnings.simplefilter("ignore", insecure_request_warning())
                response = requests.head(url, **request_kwargs)
            content_type = response.headers.get("Content-Type", "").lower()
            content_disposition = response.headers.get("Content-Disposition", "")
            is_file = False
            if ("text/html" not in content_type and "application/xhtml" not in content_type) and any(
                marker in content_type
                for marker in [
                    "application/pdf",
                    "application/msword",
                    "application/vnd",
                    "application/zip",
                    "application/x-rar",
                    "application/x-7z",
                    "application/octet-stream",
                ]
            ):
                is_file = True
            if "attachment" in content_disposition:
                is_file = True
            if not is_file:
                return False
            filename = None
            if "filename=" in content_disposition:
                match = re.search(r'filename="?([^";]+)"?', content_disposition)
                if match:
                    filename = match.group(1)
            if not filename:
                filename = unquote(os.path.basename(urlparse(url).path)) or "download"
                if not os.path.splitext(filename)[1]:
                    filename += mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".file"
            save_path = task_dir / sanitize_filename(filename)
            logger.info("[%s] Detected file download: %s", task_id, filename)
            if download_file(url=url, save_path=str(save_path), timeout=self.config.download_timeout, max_file_size=self.config.max_file_size):
                if save_path.suffix.lower() in {".zip", ".rar", ".7z", ".tar"}:
                    process_archive(save_path, url, date_str)
                else:
                    generate_meta_json(save_path, url, date_str)
                return True
        except Exception as exc:
            logger.debug("[%s] Direct link check exception: %s", task_id, exc)
        return False

    def _now(self) -> str:
        import time

        return time.strftime("%Y-%m-%d %H:%M:%S")

