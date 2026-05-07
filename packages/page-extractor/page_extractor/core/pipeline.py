"""详情页采集流水线 (Core extraction pipeline)."""

from __future__ import annotations

import mimetypes
import os
import re
import time
import warnings
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import requests
from lxml import html

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
from page_extractor.core.processor import ContentProcessor
from page_extractor.detectors.broad import BroadDetector
from page_extractor.detectors.heuristic import HeuristicDetector
from page_extractor.detectors.readability import ReadabilityDetector
from page_extractor.downloader.multi_strategy import download_file
from page_extractor.extractors.readability_lxml import ReadabilityLxmlExtractor
from page_extractor.extractors.trafilatura import TrafilaturaExtractor
from page_extractor.snapshot.pdf import snapshot_element
from page_extractor.utils import generate_meta_json, process_archive, sanitize_filename, setup_logging
from page_extractor.utils.logging import get_logger
from page_extractor.utils.tls import insecure_request_warning, ssl_verify_enabled


class CollectorPipeline:
    """主采集流水线，编排浏览器、检测器、提取器和持久化逻辑。"""

    def __init__(self, output_dir: str = "./output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = CollectorConfig(output_dir=self.output_dir)
        
        # 初始化子服务
        self._page_navigator = PageNavigator()
        self._attachment_service = AttachmentService(self.config)
        self._browser_factory = BrowserSessionFactory(
            user_agent=DEFAULT_USER_AGENT, 
            stealth_script=DEFAULT_STEALTH_SCRIPT
        )
        
        # 策略字典
        self._detectors = {
            DetectorStrategy.BROAD: BroadDetector(),
            DetectorStrategy.HEURISTIC: HeuristicDetector(),
            DetectorStrategy.READABILITY: ReadabilityDetector(),
        }
        self._extractors = {
            ExtractorStrategy.READABILITY_LXML: ReadabilityLxmlExtractor(),
            ExtractorStrategy.TRAFILATURA: TrafilaturaExtractor(),
            ExtractorStrategy.BASIC: TrafilaturaExtractor(),
        }
        self._processor = ContentProcessor()

    def collect(self, url: str, config: CollectorConfig | None = None, *, task_id: str | None = None) -> CollectorResult:
        """执行单次采集任务。"""
        logger = get_logger()
        if config:
            self.config = config
            self._attachment_service.update_config(config)
            self._browser_factory.headless = config.headless
            
        # 创建工作空间
        workspace = CollectionWorkspace(
            output_dir=self.output_dir, 
            task_id=task_id or uuid4().hex,
            save_meta_json=self.config.save_meta_json
        )
        setup_logging(log_level=self.config.log_level, log_file=workspace.log_path)
        
        result = workspace.create_result(url)
        task_id = workspace.task_id
        logger.info("[%s] 开始采集任务: %s", task_id, url)

        # 1. 预检：检查是否为直接下载链接（PDF/ZIP 等）
        if self._check_direct_download(url, workspace.task_dir, workspace.date_str, task_id):
            result.status = "success"
            result.artifacts.append("(direct file download)")
            result.completed_at = self._now()
            workspace.save_result_metadata(result)
            return result

        # 2. 浏览器环境采集
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
            logger.info("[%s] 采集任务完成", task_id)
        except Exception as exc:
            logger.exception("[%s] 采集任务失败: %s", task_id, exc)
            result.error = str(exc)
            result.completed_at = self._now()
            workspace.save_result_metadata(result)
            
        return result

    def _collect_browser_artifacts(self, *, url: str, workspace: CollectionWorkspace, result: CollectorResult, page, context) -> None:
        """在浏览器会话中执行具体的采集步骤。"""
        logger = get_logger()
        task_id = workspace.task_id
        
        # 页面加载与 Cookie 处理
        self._page_navigator.load(page, url, strategy=self.config.page_load_strategy, task_id=task_id)
        self._page_navigator.handle_cookie_consent(page)
        
        # 等待页面稳定
        try:
            page.wait_for_function("() => document.readyState === 'complete'", timeout=10000)
        except Exception:
            pass
        self._enhance_js_rendering(page, task_id)

        html_content = page.content()

        # A. 区域检测（单一事实来源）
        det = self._detect_content_area(html_content, url)
        content_area = det.content_area
        result.content_area = content_area
        result.content_area_confidence = det.confidence
        result.detector_strategy = det.strategy

        # B. 范围限定与正文提取
        cleaned = self._processor.preprocess_html(html_content)
        scoped = self._processor.scope_html(cleaned, content_area)
        
        extractor_result = self._extract_content(scoped, url, fallback_html=cleaned)
        markdown = self._processor.postprocess_markdown(extractor_result.markdown)
        
        if self.config.save_markdown:
            workspace.write_markdown(markdown, url)
            result.artifacts.append("content.md")
        
        result.markdown_length = len(markdown) if markdown else 0
        result.extractor_strategy = extractor_result.strategy

        # C. 保存 HTML 快照
        if self.config.save_html and scoped:
            formatted = self._processor.format_html(scoped)
            workspace.write_html(formatted, url)
            result.artifacts.append("content.html")

        # D. PDF 快照 (使用相同的 content_area 定位)
        if self.config.save_pdf:
            pdf_path = workspace.task_dir / "page.pdf"
            if snapshot_element(page, content_area, str(pdf_path), pdf_format=self.config.pdf_format, pdf_margin=self.config.pdf_margin):
                result.artifacts.append("page.pdf")
                workspace.write_pdf_metadata(pdf_path, url)

        # E. 附件处理
        attachments = self._attachment_service.extract_links(page, content_area)
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

    def _enhance_js_rendering(self, page, task_id: str) -> None:
        """增强 JS 渲染：滚动与 DOM 稳定性检测。"""
        logger = get_logger()
        extra = self.config.extra_wait

        # 第一轮滚动与稳定检测
        self._scroll_page(page, task_id)
        self._wait_for_dom_stable(page, task_id, idle_ms=2000, timeout_ms=10000)

        # 若内容过少，尝试第二轮深层滚动
        if self._page_text_length(page) < 500:
            logger.info("[%s] 内容过少，执行二次深度滚动", task_id)
            self._scroll_page(page, task_id)
            self._wait_for_dom_stable(page, task_id, idle_ms=3000, timeout_ms=15000)

        # 额外等待时间处理
        if extra > 0:
            logger.info("[%s] 额外等待: %.1fs", task_id, extra)
            page.wait_for_timeout(int(extra * 1000))

        # 回滚到顶部以保证快照整洁
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)

    @staticmethod
    def _scroll_page(page, task_id: str) -> None:
        """从上至下平滑滚动页面以触发延迟加载。"""
        try:
            total_height = page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
            viewport_height = page.evaluate("() => window.innerHeight")
            if total_height <= viewport_height:
                return
            
            # 优化：步长增加到 1.5 倍视口，间隔缩短至 350ms
            pos = 0
            step = int(viewport_height * 1.5)
            while pos < total_height:
                pos += step
                page.evaluate(f"window.scrollTo(0, {pos})")
                page.wait_for_timeout(350)
                # 动态内容可能会延长高度
                total_height = page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        except Exception:
            pass

    @staticmethod
    def _wait_for_dom_stable(page, task_id: str, *, idle_ms: int = 1500, timeout_ms: int = 10000) -> None:
        """基于 MutationObserver 等待 DOM 停止变动。"""
        js = f"""
        () => {{
            if (window.__pe_dom_observer) return 'already_running';
            return new Promise((resolve) => {{
                let lastChange = Date.now();
                const observer = new MutationObserver(() => {{ lastChange = Date.now(); }});
                observer.observe(document.body, {{ childList: true, subtree: true }});
                window.__pe_dom_observer = observer;
                const check = setInterval(() => {{
                    if (Date.now() - lastChange >= {idle_ms}) {{
                        clearInterval(check);
                        observer.disconnect();
                        window.__pe_dom_observer = null;
                        resolve('stable');
                    }}
                }}, 200);
                setTimeout(() => {{
                    clearInterval(check);
                    observer.disconnect();
                    window.__pe_dom_observer = null;
                    resolve('timeout');
                }}, {timeout_ms});
            }});
        }}
        """
        try:
            page.evaluate(js)
        except Exception:
            pass

    @staticmethod
    def _page_text_length(page) -> int:
        """返回当前页面可见文本长度。"""
        try:
            return page.evaluate("() => (document.body.innerText || '').trim().length")
        except Exception:
            return 0

    def _detect_content_area(self, html_content: str, url: str) -> DetectorResult:
        """检测正文区域选择器。"""
        if self.config.content_area_hint:
            return DetectorResult(
                content_area=self.config.content_area_hint, confidence=1.0,
                text_length=0, strategy=DetectorStrategy.BROAD,
                element_info={"hint": True},
            )
            
        # 按照 自动检测 -> Broad -> Readability -> Heuristic 降级
        broad = self._detectors[DetectorStrategy.BROAD]
        if broad.is_available():
            res = broad.detect(html_content, url)
            if res.confidence >= 0.2:
                return res
        
        readability = self._detectors[DetectorStrategy.READABILITY]
        if readability.is_available():
            res = readability.detect(html_content, url)
            if res.confidence >= 0.3:
                return res
                
        return self._detectors[DetectorStrategy.HEURISTIC].detect(html_content, url)

    def _extract_content(self, html_content: str, url: str, fallback_html: str | None = None) -> ExtractorResult:
        """多提取引擎运行与合并。"""
        results = self._try_extractors(html_content, url)
        if results:
            merged = self._merge_extraction_results(results) if len(results) > 1 else results[0]
            if len(merged.markdown.strip()) >= 80:
                return merged
                
        # 若限定范围内提取失败，尝试全页提取
        if fallback_html and fallback_html != html_content:
            results = self._try_extractors(fallback_html, url)
            if results:
                return self._merge_extraction_results(results) if len(results) > 1 else results[0]
                
        return self._extractors[ExtractorStrategy.BASIC].extract(html_content, url)

    def _try_extractors(self, html_content: str, url: str) -> list[ExtractorResult]:
        """尝试所有可用的提取引擎。"""
        results: list[ExtractorResult] = []
        for strat in [ExtractorStrategy.READABILITY_LXML, ExtractorStrategy.TRAFILATURA]:
            ext = self._extractors[strat]
            if ext.is_available():
                r = ext.extract(html_content, url)
                if r.markdown and len(r.markdown.strip()) >= 40:
                    results.append(r)
        return results

    @staticmethod
    def _merge_extraction_results(results: list[ExtractorResult]) -> ExtractorResult:
        """合并互补的提取结果，并进行行级别的去重。"""
        ordered = sorted(results, key=lambda r: len(r.markdown or ""), reverse=True)
        seen_keys: set[str] = set()
        merged_parts: list[str] = []
        
        for res in ordered:
            lines = [ln for ln in (res.markdown or "").splitlines() if ln.strip()]
            unique: list[str] = []
            for ln in lines:
                key = re.sub(r"[^\w\u4e00-\u9fff]", "", ln.strip().lower())
                if len(key) < 6 or key not in seen_keys:
                    seen_keys.add(key)
                    unique.append(ln)
            if unique:
                merged_parts.append("\n".join(unique))
                
        merged = "\n\n---\n\n".join(merged_parts)
        return ExtractorResult(markdown=merged, strategy=results[0].strategy)

    def _check_direct_download(self, url: str, task_dir: Path, date_str: str, task_id: str) -> bool:
        """检查 URL 是否为二进制文件直连。"""
        logger = get_logger()
        try:
            request_kwargs = {"timeout": 15, "allow_redirects": True, "verify": ssl_verify_enabled()}
            with warnings.catch_warnings():
                if not request_kwargs["verify"]:
                    warnings.simplefilter("ignore", insecure_request_warning())
                response = requests.head(url, **request_kwargs)
            
            # 若 HEAD 请求返回 405，则尝试 GET (只读头部)
            if response.status_code == 405:
                response = requests.get(url, stream=True, **request_kwargs)
                response.close()

            content_type = response.headers.get("Content-Type", "").lower()
            content_disposition = response.headers.get("Content-Disposition", "")
            
            # 判断是否为文件类型
            is_file = "attachment" in content_disposition
            if not is_file:
                file_types = [
                    "application/pdf", "application/msword", "application/vnd",
                    "application/zip", "application/x-rar", "application/x-7z",
                    "application/octet-stream"
                ]
                is_file = any(t in content_type for t in file_types)
                
            if not is_file:
                return False

            # 文件名解析
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
            logger.info("[%s] 检测到文件直连: %s", task_id, filename)
            
            if download_file(url=url, save_path=str(save_path), timeout=self.config.download_timeout, max_file_size=self.config.max_file_size):
                if save_path.suffix.lower() in {".zip", ".rar", ".7z", ".tar"}:
                    process_archive(save_path, url, date_str, save_meta_json=self.config.save_meta_json)
                elif self.config.save_meta_json:
                    generate_meta_json(save_path, url, date_str)
                return True
        except Exception:
            pass
        return False

    def _now(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

