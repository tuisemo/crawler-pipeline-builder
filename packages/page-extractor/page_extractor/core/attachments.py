"""Attachment discovery and download orchestration."""

from __future__ import annotations

import os
import re
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from page_extractor.core.types import CollectorConfig
from page_extractor.core.workspace import CollectionWorkspace
from page_extractor.downloader.concurrent_download import ConcurrentDownloader
from page_extractor.utils import (
    detect_attachment,
    extract_filename_from_get_headers,
    extract_filename_from_headers,
    generate_meta_json,
    is_attachment_by_keywords,
    is_attachment_content_type,
    is_ignored_extension,
    process_archive,
    safe_decode_text,
    sanitize_filename,
)
from page_extractor.utils.logging import get_logger
from page_extractor.utils.tls import insecure_request_warning, ssl_verify_enabled


ARCHIVE_EXTENSIONS = frozenset({".zip", ".rar", ".7z", ".tar"})


@dataclass(frozen=True, slots=True)
class PreparedAttachment:
    source_url: str
    save_path: Path


class AttachmentService:
    def __init__(self, config: CollectorConfig):
        self.config = config

    def update_config(self, config: CollectorConfig) -> None:
        self.config = config

    def extract_links(self, page, content_area: str) -> list[dict]:
        logger = get_logger()
        try:
            links_data = page.evaluate(
                """
                (selector) => {
                    let mainContent = null;
                    if (selector.startsWith('/') || selector.startsWith('(')) {
                        try { mainContent = document.evaluate(selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; } catch(e) {}
                    } else {
                        try { mainContent = document.querySelector(selector); } catch(e) {}
                    }
                    const results = [];

                    const excludeSelectors = [
                        'header', 'footer', 'nav', 'aside',
                        '.header', '.footer', '.nav', '.navbar',
                        '.sidebar', '.menu', '.advertisement',
                        '[role="banner"]', '[role="navigation"]',
                        '[role="complementary"]', '[role="contentinfo"]'
                    ];

                    function isInExcludedArea(el) {
                        for (const sel of excludeSelectors) {
                            if (el.closest(sel)) return true;
                        }
                        return false;
                    }

                    function pushLinks(element) {
                        element.querySelectorAll('a[href]').forEach(a => {
                            if (isInExcludedArea(a)) return;
                            const href = a.href;
                            if (href && !href.startsWith('javascript:') && !href.startsWith('#')) {
                                results.push({
                                    url: href,
                                    text: (a.textContent || '').trim().substring(0, 100),
                                    filename: a.getAttribute('download') || '',
                                });
                            }
                        });
                    }

                    if (mainContent) {
                        pushLinks(mainContent);
                        let parent = mainContent.parentElement;
                        for (let i = 0; i < 2 && parent; i++) {
                            pushLinks(parent);
                            parent = parent.parentElement;
                        }
                    }

                    return results;
                }
                """,
                content_area,
            )
        except Exception as exc:
            logger.warning("[Attachment] JS link extraction failed: %s", exc)
            return []

        attachments = []
        seen = set()
        for link in links_data or []:
            link_url = link.get("url", "")
            if not link_url or link_url in seen:
                continue
            parsed = urlparse(link_url)
            ext = os.path.splitext(parsed.path.lower())[1]
            if is_ignored_extension(ext):
                continue
            is_attachment = detect_attachment(
                url=link_url,
                text=link.get("text", ""),
                filename_attr=link.get("filename", ""),
            )
            if not is_attachment and is_attachment_by_keywords(link_url.lower(), link.get("text", "").lower()):
                try:
                    with warnings.catch_warnings():
                        if not ssl_verify_enabled():
                            warnings.simplefilter("ignore", insecure_request_warning())
                        response = requests.head(link_url, timeout=5, allow_redirects=True, verify=ssl_verify_enabled())
                    is_attachment = is_attachment_content_type(response.headers.get("Content-Type", ""))
                except Exception:
                    pass
            if not is_attachment:
                continue
            seen.add(link_url)
            filename = link.get("filename", "") or unquote(os.path.basename(parsed.path)) or "attachment.pdf"
            attachments.append({"url": link_url, "filename": filename, "text": safe_decode_text(link.get("text", ""))})
        logger.info("[Attachment] Found %s attachment links", len(attachments))
        return attachments

    def download(
        self,
        *,
        attachments: list[dict],
        context,
        workspace: CollectionWorkspace,
        referer_url: str,
    ) -> int:
        logger = get_logger()
        task_id = workspace.task_id
        if not attachments:
            return 0
        attachments_dir = workspace.attachments_dir()
        cookies = context.cookies(referer_url)
        download_tasks, prepared = self.prepare_downloads(attachments=attachments, attachments_dir=attachments_dir)
        if not download_tasks:
            return 0
        downloader = ConcurrentDownloader(max_concurrent=self.config.max_concurrent_downloads)
        result = downloader.download_many(
            tasks=download_tasks,
            cookies=cookies,
            context=context,
            referer_url=referer_url,
            max_file_size=self.config.max_file_size,
            timeout=self.config.download_timeout,
            task_id=task_id,
        )
        success_count = 0
        for index, (success, _, _) in enumerate(result.results):
            if not success:
                continue
            prepared_attachment = prepared[index]
            if prepared_attachment.save_path.suffix.lower() in ARCHIVE_EXTENSIONS:
                process_archive(prepared_attachment.save_path, prepared_attachment.source_url, workspace.date_str, save_meta_json=workspace.save_meta_json)
            elif workspace.save_meta_json:
                generate_meta_json(prepared_attachment.save_path, prepared_attachment.source_url, workspace.date_str)
            success_count += 1
        logger.info("[%s] Attachment download complete: %s/%s", task_id, success_count, len(download_tasks))
        return success_count

    def prepare_downloads(self, *, attachments: list[dict], attachments_dir: Path) -> tuple[list[dict[str, str]], list[PreparedAttachment]]:
        logger = get_logger()
        tasks: list[dict[str, str]] = []
        prepared: list[PreparedAttachment] = []
        for attachment in attachments:
            attachment_url = attachment["url"]
            filename_ext = os.path.splitext(attachment.get("filename", ""))[1].lower()
            url_ext = os.path.splitext(urlparse(attachment_url).path)[1].lower()
            attachment_ext = filename_ext or url_ext
            is_valid = attachment_ext in self.config.attachment_extensions
            if not is_valid:
                try:
                    with warnings.catch_warnings():
                        if not ssl_verify_enabled():
                            warnings.simplefilter("ignore", insecure_request_warning())
                        response = requests.head(attachment_url, timeout=10, allow_redirects=True, verify=ssl_verify_enabled())
                    is_valid = is_attachment_content_type(response.headers.get("Content-Type", ""))
                except Exception:
                    is_valid = True
            if not is_valid:
                continue
            filename = sanitize_filename(self.resolve_filename(attachment, attachment_url))
            save_path = attachments_dir / filename
            if save_path.exists():
                base, ext = os.path.splitext(filename)
                save_path = attachments_dir / f"{base}_{uuid.uuid4().hex[:4]}{ext}"
            tasks.append({"url": attachment_url, "save_path": str(save_path)})
            prepared.append(PreparedAttachment(source_url=attachment_url, save_path=save_path))
        return tasks, prepared

    def resolve_filename(self, attachment: dict, attachment_url: str) -> str:
        cd_filename = extract_filename_from_headers(attachment_url)
        if cd_filename:
            return safe_decode_text(cd_filename)
        cd_filename = extract_filename_from_get_headers(attachment_url)
        if cd_filename:
            return safe_decode_text(cd_filename)
        filename_attr = attachment.get("filename", "")
        if filename_attr and not filename_attr.endswith(".ext"):
            return safe_decode_text(filename_attr)
        url_filename = unquote(os.path.basename(urlparse(attachment_url).path))
        if url_filename and os.path.splitext(url_filename)[1]:
            return safe_decode_text(url_filename)
        text = safe_decode_text(attachment.get("text", ""))
        if text:
            return f"{sanitize_filename(text)[:100] or 'download'}.file"
        return f"download_{uuid.uuid4().hex[:6]}.file"

