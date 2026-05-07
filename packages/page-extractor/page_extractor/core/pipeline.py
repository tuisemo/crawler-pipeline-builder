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
    def __init__(self, output_dir: str = "./output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = CollectorConfig(output_dir=self.output_dir)
        self._page_navigator = PageNavigator()
        self._attachment_service = AttachmentService(self.config)
        self._browser_factory = BrowserSessionFactory(user_agent=DEFAULT_USER_AGENT, stealth_script=DEFAULT_STEALTH_SCRIPT)
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

        # --- Enhanced JS rendering: scroll + wait for content ---
        self._enhance_js_rendering(page, task_id)

        html_content = page.content()

        # --- Detect content area (single source of truth) ---
        det = self._detect_content_area(html_content, url)
        content_area = det.content_area
        result.content_area = content_area
        result.content_area_confidence = det.confidence
        result.detector_strategy = det.strategy

        # --- Scope HTML to content area, then extract ---
        cleaned = self._preprocess_html(html_content)
        scoped = self._scope_html(cleaned, content_area)
        extractor_result = self._extract_content(scoped, url, fallback_html=cleaned)
        markdown = extractor_result.markdown
        if self.config.save_markdown:
            workspace.write_markdown(markdown, url)
            result.artifacts.append("content.md")
        result.markdown_length = len(markdown) if markdown else 0
        result.extractor_strategy = extractor_result.strategy

        # --- Save scoped HTML ---
        if self.config.save_html and scoped:
            formatted = self._format_html(scoped)
            workspace.write_html(formatted, url)
            result.artifacts.append("content.html")

        # --- PDF snapshot using the same content area locator ---
        if self.config.save_pdf:
            pdf_path = workspace.task_dir / "page.pdf"
            if snapshot_element(page, content_area, str(pdf_path), pdf_format=self.config.pdf_format, pdf_margin=self.config.pdf_margin):
                result.artifacts.append("page.pdf")
                workspace.write_pdf_metadata(pdf_path, url)

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
        result.attachment_count = downloaded_count

    # ------------------------------------------------------------------
    # JS rendering enhancement
    # ------------------------------------------------------------------

    def _enhance_js_rendering(self, page, task_id: str) -> None:
        """Scroll the page and wait for JS-rendered content to appear.

        Strategy:
        1. Scroll top→bottom in viewport-sized steps to trigger lazy loaders.
        2. Wait for DOM to stabilise (MutationObserver: no mutations for 2s).
        3. If content is still short, repeat scroll + DOM-stable wait.
        4. If extra_wait > 0, do additional scroll cycles with pauses.
        5. Scroll back to top for clean PDF snapshot.
        """
        logger = get_logger()
        extra = self.config.extra_wait

        # Pass 1: scroll + wait for DOM stability
        self._scroll_page(page, task_id)
        self._wait_for_dom_stable(page, task_id, idle_ms=2000, timeout_ms=10000)

        # Pass 2: if content is thin, scroll again with longer wait
        text_len = self._page_text_length(page)
        if text_len < 500:
            logger.info("[%s] Content thin (%d chars), second scroll pass", task_id, text_len)
            self._scroll_page(page, task_id)
            self._wait_for_dom_stable(page, task_id, idle_ms=3000, timeout_ms=15000)
            self._wait_for_content_elements(page, task_id, timeout_ms=8000)

        # Extra wait: user-requested additional settle time
        if extra > 0:
            logger.info("[%s] Extra wait: %.1fs with scrolling", task_id, extra)
            elapsed = 0.0
            step = min(3.0, extra)
            while elapsed < extra:
                self._scroll_page(page, task_id)
                page.wait_for_timeout(int(step * 1000))
                elapsed += step
            self._wait_for_dom_stable(page, task_id, idle_ms=2000, timeout_ms=5000)

        # Scroll back to top for clean snapshot / PDF
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)

    @staticmethod
    def _scroll_page(page, task_id: str) -> None:
        """Scroll the page from top to bottom in viewport-sized steps.

        Each step scrolls one viewport height, then waits briefly for
        lazy loaders to fire.  After reaching the bottom, scrolls back
        to top.
        """
        logger = get_logger()
        try:
            total_height = page.evaluate(
                "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
            )
            viewport_height = page.evaluate("() => window.innerHeight")
            if total_height <= viewport_height:
                return
            pos = 0
            while pos < total_height:
                pos += viewport_height
                page.evaluate(f"window.scrollTo(0, {pos})")
                page.wait_for_timeout(600)
                # Re-check height (dynamic content may have extended the page)
                try:
                    total_height = page.evaluate(
                        "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
                    )
                except Exception:
                    break
            logger.debug("[%s] Scroll pass complete (%d px)", task_id, total_height)
        except Exception as exc:
            logger.debug("[%s] Scroll failed: %s", task_id, exc)

    @staticmethod
    def _wait_for_content_elements(page, task_id: str, *, timeout_ms: int = 8000) -> None:
        """Wait until the DOM contains enough content-rich elements.

        Content-rich = at least 3 paragraphs OR at least 2 headings with
        visible text, OR the body has substantial visible text (SPA/div layouts).
        """
        logger = get_logger()
        js = """
        () => {
            const ps = document.querySelectorAll('p');
            let pLen = 0;
            for (const p of ps) { if ((p.innerText || '').trim().length >= 30) pLen++; }
            const hs = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
            let hLen = 0;
            for (const h of hs) { if ((h.innerText || '').trim().length >= 4) hLen++; }
            const articles = document.querySelectorAll('article, section, [role="main"]');
            const bodyText = (document.body.innerText || '').trim().length;
            return pLen >= 3 || hLen >= 2 || articles.length >= 2 || bodyText >= 800;
        }
        """
        try:
            page.wait_for_function(js, timeout=timeout_ms)
        except Exception:
            logger.debug("[%s] Content-element wait timed out (%d ms)", task_id, timeout_ms)

    @staticmethod
    def _wait_for_dom_stable(page, task_id: str, *, idle_ms: int = 2000, timeout_ms: int = 10000) -> None:
        """Wait until the DOM stops changing (MutationObserver-based).

        Injects a MutationObserver that tracks node additions/removals.
        Returns once no mutations have been observed for *idle_ms*
        milliseconds, or when *timeout_ms* is exceeded.
        """
        logger = get_logger()
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
            outcome = page.evaluate(js)
            if outcome == "already_running":
                page.wait_for_timeout(idle_ms)
            else:
                logger.debug("[%s] DOM stable: %s (idle=%dms, timeout=%dms)", task_id, outcome, idle_ms, timeout_ms)
        except Exception as exc:
            logger.debug("[%s] DOM stable wait failed: %s", task_id, exc)

    @staticmethod
    def _format_html(html_content: str) -> str:
        """Format HTML with pretty-print indentation."""
        try:
            from lxml import html, etree
            tree = html.fromstring(html_content)
            return etree.tostring(tree, encoding="unicode", pretty_print=True)
        except Exception:
            return html_content

    @staticmethod
    def _page_text_length(page) -> int:
        """Return the visible text length of the current page."""
        try:
            return page.evaluate(
                "() => (document.body.innerText || '').trim().length"
            )
        except Exception:
            return 0

    def _detect_content_area(self, html_content: str, url: str) -> DetectorResult:
        """Detect the main content area locator (xpath or CSS selector)."""
        if self.config.content_area_hint:
            return DetectorResult(
                content_area=self.config.content_area_hint, confidence=1.0,
                text_length=0, strategy=DetectorStrategy.BROAD,
                element_info={"hint": True},
            )
        if self.config.detector_strategy != DetectorStrategy.AUTO:
            det = self._detectors.get(self.config.detector_strategy)
            if det and det.is_available():
                return det.detect(html_content, url)
        broad = self._detectors[DetectorStrategy.BROAD]
        if broad.is_available():
            result = broad.detect(html_content, url)
            if result.confidence >= 0.2:
                return result
        readability = self._detectors[DetectorStrategy.READABILITY]
        if readability.is_available():
            r = readability.detect(html_content, url)
            if r.confidence >= 0.3:
                return r
        return self._detectors[DetectorStrategy.HEURISTIC].detect(html_content, url)

    def _extract_content(self, html_content: str, url: str, fallback_html: str | None = None) -> ExtractorResult:
        results = self._try_extractors(html_content, url)
        if results:
            merged = self._merge_extraction_results(results) if len(results) > 1 else results[0]
            cleaned = self._postprocess_markdown(merged.markdown, url)
            if len(cleaned.strip()) >= 80:
                return ExtractorResult(markdown=cleaned, strategy=merged.strategy)
        if fallback_html and fallback_html != html_content:
            results = self._try_extractors(fallback_html, url)
            if results:
                merged = self._merge_extraction_results(results) if len(results) > 1 else results[0]
                cleaned = self._postprocess_markdown(merged.markdown, url)
                return ExtractorResult(markdown=cleaned, strategy=merged.strategy)
        return self._extractors[ExtractorStrategy.BASIC].extract(html_content, url)

    def _try_extractors(self, html_content: str, url: str) -> list[ExtractorResult]:
        results: list[ExtractorResult] = []
        readability_ext = self._extractors[ExtractorStrategy.READABILITY_LXML]
        if readability_ext.is_available():
            r = readability_ext.extract(html_content, url)
            if r.markdown and len(r.markdown.strip()) >= 40:
                results.append(r)
        trafilatura_ext = self._extractors[ExtractorStrategy.TRAFILATURA]
        r2 = trafilatura_ext.extract(html_content, url)
        if r2.markdown and len(r2.markdown.strip()) >= 40:
            results.append(r2)
        return results


    @staticmethod
    def _merge_extraction_results(results: list[ExtractorResult]) -> ExtractorResult:
        """Merge complementary extraction results with aggressive normalized dedup."""
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

    @staticmethod
    def _preprocess_html(html_content: str) -> str:
        """Strip truly invasive noise from the DOM before extraction.

        Only removes elements that distort content extraction:
        - iframes (inquiry forms, ads, embedded apps)
        - elements with display:none or visibility:hidden

        Structural labels, modals, and dividers are handled by
        _postprocess_markdown instead, so the DOM stays intact for
        trafilatura and readability-lxml to analyse.
        """
        try:
            from lxml import html
            tree = html.fromstring(html_content)
        except Exception:
            return html_content

        removed = 0
        for element in list(tree.iter()):
            if element.tag in ("script", "style", "noscript"):
                continue
            if element.tag == "iframe":
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)
                    removed += 1
                continue
            style = (element.get("style") or "").lower().replace(" ", "")
            if "display:none" in style or "visibility:hidden" in style:
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)
                    removed += 1
                continue

        if removed:
            return html.tostring(tree, encoding="unicode")
        return html_content


    @staticmethod
    def _postprocess_markdown(markdown: str, url: str) -> str:
        """Algorithmic formatting cleanup -- no keyword filtering.

        Only structural and formatting normalisation:
        - title suffix removal (generic pattern)
        - decoration image removal (.gif / .ico)
        - colon spacing normalisation in bold spans
        - separator collapsing
        - short trailing duplicate-block removal (title similarity)
        """
        if not markdown:
            return markdown

        lines = markdown.split("\n")

        # --- Title suffix removal (structural pattern) ---
        if lines and lines[0].startswith("# "):
            title = lines[0]
            title = re.sub(r"\s+[\-\u2013]\s*\S+(\s+[\-\u2013]\s*\S+)*$", "", title)
            title = re.sub(r"_[\u4e00-\u9fff][\u4e00-\u9fff\w]{2,}$", "", title)
            title = re.sub(r"\s*\|\s*[\u4e00-\u9fff]{2,}$", "", title)
            lines[0] = title

        text = "\n".join(lines)

        # --- Remove decoration images (.gif, .ico) ---
        text = re.sub(r"!\[([^\]]*)\]\([^)]*(?:\.gif|\.ico)[^)]*\)", "", text)

        # --- Normalise colon spacing in bold spans ---
        text = re.sub(r"\*\*(\S+)\s*:\s*\*\s*\*\s*", r"**\1:** ", text)

        # --- Collapse excessive separators ---
        text = re.sub(r"(\n---\n){2,}", "\n---\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # --- Remove short trailing blocks that duplicate the main title ---
        parts = text.split("\n---\n")
        if len(parts) >= 2:
            last = parts[-1].strip()
            if len(last) < 300:
                main_title = ""
                for ln in parts[0].split("\n"):
                    if ln.startswith("# "):
                        main_title = re.sub(r"^#+\s*", "", ln).strip()
                        break
                last_title = ""
                if last.startswith("# "):
                    last_title = re.sub(r"^#+\s*", "", last.split("\n")[0]).strip()
                check = last_title or last.split("\n")[0].strip()
                if main_title and check:
                    a = re.sub(r"[\s_\-|,.;:!?]+", "", main_title).lower()
                    b = re.sub(r"[\s_\-|,.;:!?]+", "", check).lower()
                    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
                        text = parts[0].strip()

        return text.strip()

    @staticmethod
    def _scope_html(html_content: str, xpath: str) -> str:
        """Scope full page HTML to the element matched by *xpath*."""
        try:
            from lxml import html
            tree = html.fromstring(html_content)
            elements = tree.xpath(xpath)
            if not elements:
                return html_content
            return html.tostring(elements[0], encoding="unicode")
        except Exception:
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

