"""Browser pool for detail extraction download fallbacks."""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from page_extractor.utils.logging import get_logger


logger = get_logger()


@dataclass
class PooledContext:
    context: Any
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    in_use: bool = False


@dataclass
class PooledBrowser:
    browser_id: str
    browser: Any
    contexts: list[PooledContext] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    in_use: bool = False
    _playwright: Any | None = field(default=None, repr=False)


class BrowserPool:
    def __init__(self, max_browsers: int = 2, max_contexts_per_browser: int = 3):
        self.max_browsers = max_browsers
        self.max_contexts_per_browser = max_contexts_per_browser
        self._browsers: list[PooledBrowser] = []
        self._pool_lock = threading.Lock()

    def _create_browser(self) -> PooledBrowser:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        pooled = PooledBrowser(browser_id=uuid.uuid4().hex[:8], browser=browser, _playwright=playwright)
        self._browsers.append(pooled)
        return pooled

    def acquire_browser(self) -> PooledBrowser:
        with self._pool_lock:
            for pooled in self._browsers:
                if not pooled.in_use:
                    pooled.in_use = True
                    pooled.last_used = time.time()
                    return pooled
            if len(self._browsers) < self.max_browsers:
                pooled = self._create_browser()
                pooled.in_use = True
                return pooled
            pooled = self._browsers[0]
            pooled.in_use = True
            return pooled

    def release_browser(self, pooled_browser: PooledBrowser) -> None:
        with self._pool_lock:
            pooled_browser.in_use = False
            pooled_browser.last_used = time.time()

    def acquire_context(self, pooled_browser: PooledBrowser) -> PooledContext:
        with self._pool_lock:
            for pooled_context in pooled_browser.contexts:
                if not pooled_context.in_use:
                    pooled_context.in_use = True
                    pooled_context.last_used = time.time()
                    return pooled_context
            context = pooled_browser.browser.new_context(accept_downloads=True)
            pooled_context = PooledContext(context=context, in_use=True)
            pooled_browser.contexts.append(pooled_context)
            return pooled_context

    def release_context(self, pooled_browser: PooledBrowser, pooled_context: PooledContext) -> None:
        with self._pool_lock:
            pooled_context.in_use = False
            pooled_context.last_used = time.time()

    def shutdown(self) -> None:
        with self._pool_lock:
            for pooled_browser in self._browsers:
                for pooled_context in pooled_browser.contexts:
                    with suppress(Exception):
                        pooled_context.context.close()
                with suppress(Exception):
                    pooled_browser.browser.close()
                if pooled_browser._playwright is not None:
                    with suppress(Exception):
                        pooled_browser._playwright.stop()
            self._browsers.clear()


_POOL: BrowserPool | None = None
_POOL_LOCK = threading.Lock()


def get_browser_pool(reset: bool = False) -> BrowserPool:
    global _POOL
    if reset:
        with _POOL_LOCK:
            if _POOL is not None:
                _POOL.shutdown()
            _POOL = None
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = BrowserPool()
    return _POOL

