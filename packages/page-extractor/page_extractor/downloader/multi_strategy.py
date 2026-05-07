"""Multi-strategy attachment downloader."""

from __future__ import annotations

import contextlib
import os
import time
import warnings
from urllib.parse import urlparse

import requests

from page_extractor.downloader.browser_pool import get_browser_pool
from page_extractor.utils.logging import get_logger
from page_extractor.utils.tls import insecure_request_warning, ssl_verify_enabled


logger = get_logger()

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _exponential_backoff(attempt: int, base: float = 1.0, max_delay: float = 30.0) -> float:
    return min(base * (2**attempt), max_delay)


def download_file(
    *,
    url: str,
    save_path: str,
    cookies: list | None = None,
    context=None,
    referer_url: str | None = None,
    max_retries: int = 3,
    timeout: int = 200,
    max_file_size: int = 500 * 1024 * 1024,
    task_id: str | None = None,
) -> bool:
    success, error = _download_via_requests(url, save_path, cookies, max_retries, timeout, max_file_size)
    if success:
        return True
    if context is not None:
        success, error = _download_via_playwright_api(url, save_path, context, max_retries, max_file_size)
        if success:
            return True
    success, error = _download_via_playwright_page(url, save_path, referer_url, max_retries, max_file_size)
    return success


def _download_via_requests(
    url: str,
    save_path: str,
    cookies: list | None,
    max_retries: int,
    timeout: int,
    max_file_size: int,
) -> tuple[bool, str | None]:
    if os.path.exists(save_path):
        os.remove(save_path)
    last_error = None
    for attempt in range(max_retries):
        session = requests.Session()
        try:
            request_cookies = {item.get("name", ""): item.get("value", "") for item in cookies or [] if item.get("name")}
            headers = {
                "User-Agent": DEFAULT_UA,
                "Referer": url,
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            with warnings.catch_warnings():
                if not ssl_verify_enabled():
                    warnings.simplefilter("ignore", insecure_request_warning())
                response = session.get(
                    url,
                    headers=headers,
                    cookies=request_cookies,
                    stream=True,
                    timeout=timeout,
                    verify=ssl_verify_enabled(),
                )
            response.raise_for_status()
            downloaded_size = 0
            with open(save_path, "wb") as target:
                for chunk in response.iter_content(8192):
                    downloaded_size += len(chunk)
                    if downloaded_size > max_file_size:
                        os.remove(save_path)
                        raise RuntimeError(f"File exceeds size limit {max_file_size} bytes")
                    target.write(chunk)
            return (True, None)
        except Exception as exc:
            last_error = str(exc)
            if attempt < max_retries - 1:
                time.sleep(_exponential_backoff(attempt))
        finally:
            session.close()
    if os.path.exists(save_path):
        os.remove(save_path)
    return (False, last_error)


def _download_via_playwright_api(
    url: str,
    save_path: str,
    context,
    max_retries: int,
    max_file_size: int,
) -> tuple[bool, str | None]:
    if os.path.exists(save_path):
        os.remove(save_path)
    last_error = None
    for attempt in range(max_retries):
        try:
            response = context.request.get(url, timeout=300000)
            if 200 <= response.status < 300:
                body = response.body()
                if len(body) > max_file_size:
                    raise RuntimeError(f"File exceeds size limit {max_file_size} bytes")
                with open(save_path, "wb") as target:
                    target.write(body)
                return (True, None)
            last_error = f"HTTP {response.status}"
        except Exception as exc:
            last_error = str(exc)
            if attempt < max_retries - 1:
                time.sleep(_exponential_backoff(attempt))
    if os.path.exists(save_path):
        os.remove(save_path)
    return (False, last_error)


def _download_via_playwright_page(
    url: str,
    save_path: str,
    referer_url: str | None,
    max_retries: int,
    max_file_size: int,
) -> tuple[bool, str | None]:
    if os.path.exists(save_path):
        os.remove(save_path)
    pool = get_browser_pool()
    last_error = None
    for attempt in range(max_retries):
        pooled_browser = None
        pooled_context = None
        page = None
        try:
            pooled_browser = pool.acquire_browser()
            pooled_context = pool.acquire_context(pooled_browser)
            page = pooled_context.context.new_page()
            download_started = False
            download_obj = None

            def on_download(download):
                nonlocal download_started, download_obj
                download_started = True
                download_obj = download

            page.on("download", on_download)
            pre_url = referer_url
            if not pre_url:
                parsed = urlparse(url)
                pre_url = f"{parsed.scheme}://{parsed.netloc}"
            with contextlib.suppress(Exception):
                page.goto(pre_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(2500)
            waited = 0.0
            while not download_started and waited < 30:
                page.wait_for_timeout(500)
                waited += 0.5
            if download_obj:
                download_obj.save_as(save_path)
                if os.path.exists(save_path) and os.path.getsize(save_path) > max_file_size:
                    os.remove(save_path)
                    raise RuntimeError(f"File exceeds size limit {max_file_size} bytes")
                return (True, None)
            last_error = "Download not triggered"
        except Exception as exc:
            last_error = str(exc)
            if attempt < max_retries - 1:
                time.sleep(_exponential_backoff(attempt))
        finally:
            if page:
                with contextlib.suppress(Exception):
                    page.close()
            if pooled_context is not None and pooled_browser is not None:
                pool.release_context(pooled_browser, pooled_context)
            if pooled_browser is not None:
                pool.release_browser(pooled_browser)
    if os.path.exists(save_path):
        os.remove(save_path)
    return (False, last_error)

