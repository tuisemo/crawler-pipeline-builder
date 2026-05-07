"""Playwright browser session helpers for detail extraction."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import TimeoutError, sync_playwright

from page_extractor.core.types import PageLoadStrategy
from page_extractor.utils.logging import get_logger


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {}, };
window.chrome.loadTimes = undefined;
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.outerHeight = window.screen.height;
window.outerWidth = window.screen.width;
"""


@dataclass
class BrowserSession:
    playwright: Any
    browser: Any
    context: Any
    page: Any


class BrowserSessionFactory:
    def __init__(
        self,
        *,
        user_agent: str,
        stealth_script: str,
        locale: str = "zh-CN",
        timezone_id: str = "Asia/Shanghai",
        headless: bool = True,
    ):
        self.user_agent = user_agent
        self.stealth_script = stealth_script
        self.locale = locale
        self.timezone_id = timezone_id
        self.headless = headless

    @contextmanager
    def create(self) -> Iterator[BrowserSession]:
        playwright_inst = None
        browser = None
        context = None
        page = None
        try:
            playwright_inst = sync_playwright().start()
            browser = playwright_inst.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            context = browser.new_context(
                user_agent=self.user_agent,
                accept_downloads=True,
                locale=self.locale,
                timezone_id=self.timezone_id,
                color_scheme="light",
                device_scale_factor=1,
                is_mobile=False,
                has_touch=False,
                bypass_csp=True,
                java_script_enabled=True,
            )
            context.add_init_script(self.stealth_script)
            page = context.new_page()
            yield BrowserSession(playwright=playwright_inst, browser=browser, context=context, page=page)
        finally:
            for obj in [page, context, browser]:
                if obj:
                    with contextlib.suppress(Exception):
                        obj.close()
            if playwright_inst:
                with contextlib.suppress(Exception):
                    playwright_inst.stop()


class PageNavigator:
    def load(self, page, url: str, *, strategy: PageLoadStrategy, task_id: str) -> bool:
        logger = get_logger()
        if strategy == PageLoadStrategy.DOM_CONTENT_LOADED:
            return self._try_load(page, url, wait_until="domcontentloaded", timeout_ms=60000, settle_ms=3000, task_id=task_id)
        if strategy == PageLoadStrategy.NETWORK_IDLE:
            return self._try_load(page, url, wait_until="networkidle", timeout_ms=120000, settle_ms=3000, task_id=task_id)
        if self._try_load(
            page,
            url,
            wait_until="networkidle",
            timeout_ms=60000,
            settle_ms=3000,
            task_id=task_id,
            suppress_error_log=True,
        ):
            return True
        logger.warning("[%s] networkidle unavailable, falling back to domcontentloaded", task_id)
        return self._try_load(page, url, wait_until="domcontentloaded", timeout_ms=60000, settle_ms=5000, task_id=task_id)

    def handle_cookie_consent(self, page) -> None:
        selectors = [
            "button:has-text('Accept')",
            "button:has-text('Accept All')",
            "button:has-text('同意')",
            "button:has-text('接受')",
            "[id*='cookie'] button",
            "[class*='cookie'] button",
            "[id*='consent'] button",
            "[class*='consent'] button",
        ]
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if button.count() > 0 and button.is_visible(timeout=800):
                    button.click(timeout=3000)
                    page.wait_for_timeout(800)
                    return
            except Exception:
                continue

    def _try_load(
        self,
        page,
        url: str,
        *,
        wait_until: str,
        timeout_ms: int,
        settle_ms: int,
        task_id: str,
        suppress_error_log: bool = False,
    ) -> bool:
        logger = get_logger()
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            page.wait_for_timeout(settle_ms)
            return True
        except TimeoutError:
            if not suppress_error_log:
                logger.error("[%s] Page load timed out with strategy: %s", task_id, wait_until)
        except Exception as exc:
            if not suppress_error_log:
                logger.error("[%s] Page load failed: %s", task_id, exc)
        return False

