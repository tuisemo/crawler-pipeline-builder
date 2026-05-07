"""Attachment detection helpers."""

from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse


ATTACHMENT_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".csv", ".txt", ".rtf", ".odt", ".ods",
})

IGNORED_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv",
})

ATTACHMENT_KEYWORDS = [
    "download", "attachment", "file", "document",
    "下载", "附件", "文件", "文档",
]

ATTACHMENT_CONTENT_TYPES = [
    "application/pdf",
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats",
    "application/zip",
    "application/x-rar",
    "application/x-7z",
    "application/octet-stream",
]


def get_extension_from_url(url: str) -> str:
    return os.path.splitext(urlparse(url).path)[1].lower()


def get_extension_from_filename(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def is_attachment_extension(ext: str) -> bool:
    if not ext:
        return False
    if not ext.startswith("."):
        ext = "." + ext
    return ext.lower() in ATTACHMENT_EXTENSIONS


def is_ignored_extension(ext: str) -> bool:
    if not ext:
        return False
    if not ext.startswith("."):
        ext = "." + ext
    return ext.lower() in IGNORED_EXTENSIONS


def is_attachment_content_type(content_type: str) -> bool:
    if not content_type:
        return False
    lowered = content_type.lower()
    return any(item in lowered for item in ATTACHMENT_CONTENT_TYPES)


def is_attachment_by_keywords(url: str, text: str = "") -> bool:
    lowered_url = url.lower()
    lowered_text = text.lower()
    path_only = urlparse(url).path.lower()
    if "/file/download" in path_only or "/download" in path_only:
        return True
    return any(keyword in lowered_url or keyword in lowered_text for keyword in ATTACHMENT_KEYWORDS)


def safe_decode_text(text: str) -> str:
    if not text:
        return ""
    decoded_rfc5987 = _decode_rfc5987(text)
    if decoded_rfc5987 is not None:
        return decoded_rfc5987
    try:
        decoded = unquote(text)
        decoded.encode("utf-8")
        return decoded
    except Exception:
        return text


def _decode_rfc5987(text: str) -> str | None:
    if not text or "*=" not in text.lower():
        return None
    try:
        match = re.search(r"""filename\*=(?:UTF-8''|utf-8'')([^;]+)""", text, re.IGNORECASE)
        if match:
            return unquote(match.group(1))
    except Exception:
        return None
    return None


def detect_attachment(
    *,
    url: str,
    text: str = "",
    filename_attr: str = "",
    content_type: str | None = None,
) -> bool:
    if filename_attr:
        ext = get_extension_from_filename(filename_attr)
        if ext:
            if is_attachment_extension(ext):
                return True
            if is_ignored_extension(ext):
                return False

    ext = get_extension_from_url(url)
    if is_attachment_extension(ext):
        return True
    if is_ignored_extension(ext):
        return False

    if is_attachment_by_keywords(url, text):
        if content_type:
            return is_attachment_content_type(content_type)
        return True
    return False
