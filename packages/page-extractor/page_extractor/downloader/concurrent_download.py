"""Concurrent downloader for detail extraction attachments."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from page_extractor.utils.logging import get_logger


logger = get_logger()


@dataclass
class ConcurrentDownloadResult:
    total: int
    success_count: int
    failed_count: int
    results: list[tuple[bool, str, str | None]] = field(default_factory=list)
    duration_ms: float = 0.0


class ConcurrentDownloader:
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max(1, min(max_concurrent, 20))
        self._lock = threading.Lock()

    def download_many(
        self,
        tasks: list[dict[str, Any]],
        *,
        cookies: list | None = None,
        context=None,
        referer_url: str | None = None,
        max_file_size: int = 500 * 1024 * 1024,
        timeout: int = 200,
        task_id: str | None = None,
    ) -> ConcurrentDownloadResult:
        if not tasks:
            return ConcurrentDownloadResult(total=0, success_count=0, failed_count=0)
        from page_extractor.downloader.multi_strategy import download_file

        total = len(tasks)
        success_count = 0
        failed_count = 0
        results: list[tuple[bool, str, str | None]] = []
        start = time.time()

        def run_task(task: dict[str, Any]) -> tuple[bool, str, str | None]:
            try:
                success = download_file(
                    url=task["url"],
                    save_path=task["save_path"],
                    cookies=cookies,
                    context=context,
                    referer_url=referer_url,
                    timeout=timeout,
                    max_file_size=max_file_size,
                    task_id=task_id,
                )
                return (success, task["save_path"], None if success else "download_file returned False")
            except Exception as exc:
                return (False, task["save_path"], str(exc))

        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            futures = [executor.submit(run_task, task) for task in tasks]
            for future in as_completed(futures):
                success, save_path, error = future.result()
                results.append((success, save_path, error))
                with self._lock:
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1

        return ConcurrentDownloadResult(
            total=total,
            success_count=success_count,
            failed_count=failed_count,
            results=results,
            duration_ms=(time.time() - start) * 1000,
        )

