"""File helper utilities for detail extraction."""

from __future__ import annotations

import os
import re
import warnings

import requests

from .tls import insecure_request_warning, ssl_verify_enabled


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", filename)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 200:
        name, ext = os.path.splitext(cleaned)
        cleaned = name[:190] + ext
    return cleaned or "unnamed_file"


def extract_filename_from_headers(url: str, timeout: int = 10) -> str | None:
    try:
        with warnings.catch_warnings():
            if not ssl_verify_enabled():
                warnings.simplefilter("ignore", insecure_request_warning())
            response = requests.head(url, timeout=timeout, allow_redirects=True, verify=ssl_verify_enabled())
        return _parse_content_disposition(response.headers)
    except Exception:
        return None


def extract_filename_from_get_headers(url: str, timeout: int = 10) -> str | None:
    try:
        with warnings.catch_warnings():
            if not ssl_verify_enabled():
                warnings.simplefilter("ignore", insecure_request_warning())
            response = requests.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                verify=ssl_verify_enabled(),
                stream=True,
            )
        return _parse_content_disposition(response.headers)
    except Exception:
        return None


def _parse_content_disposition(headers: dict[str, str]) -> str | None:
    content_disposition = headers.get("Content-Disposition", "")
    if not content_disposition:
        return None
    match = re.search(r"filename\*=(?:UTF-8''|utf-8'')([^;]+)", content_disposition, re.IGNORECASE)
    if match:
        from urllib.parse import unquote

        return unquote(match.group(1))
    match = re.search(r'filename="?([^";]+)"?', content_disposition)
    if match:
        from urllib.parse import unquote

        return unquote(match.group(1))
    return None
