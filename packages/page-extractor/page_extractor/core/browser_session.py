"""Playwright 浏览器会话管理工具 (Browser session management)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import TimeoutError, sync_playwright

from page_extractor.core.types import PageLoadStrategy
from page_extractor.utils.logging import get_logger


# 默认的 User-Agent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# 基础的反爬指纹混淆脚本
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
    """封装 Playwright 的完整会话资源。"""
    playwright: Any
    browser: Any
    context: Any
    page: Any


class BrowserSessionFactory:
    """浏览器会话工厂，负责资源的生命周期管理。"""
    
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
        """创建并让渡一个浏览器会话，确保在使用后正确关闭资源。"""
        playwright_inst = None
        browser = None
        context = None
        page = None
        try:
            playwright_inst = sync_playwright().start()
            browser_type = playwright_inst.chromium
            # 有头模式下通常需要少许延迟以便观察
            launch_options = {
                "headless": self.headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ],
            }
            if not self.headless:
                launch_options["slow_mo"] = 100
                
            browser = browser_type.launch(**launch_options)
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
            # 注入反爬脚本
            context.add_init_script(self.stealth_script)
            
            # --- 优化：拦截广告与追踪脚本，加速 networkidle ---
            def block_aggressively(route):
                url = route.request.url.lower()
                patterns = [
                    "google-analytics.com", "googletagmanager.com", "doubleclick.net",
                    "analysis.css.org.cn", "cnzz.com", "baidu.com/hm.js", "stat.w3.org",
                    "adservice.google", "analytics.google", "facebook.net", "twitter.com/widgets"
                ]
                if any(p in url for p in patterns):
                    route.abort()
                else:
                    route.continue_()
            
            context.route("**/*", block_aggressively)
            
            page = context.new_page()
            yield BrowserSession(playwright=playwright_inst, browser=browser, context=context, page=page)
        finally:
            # 倒序关闭资源
            for obj in [page, context, browser]:
                if obj:
                    with contextlib.suppress(Exception):
                        obj.close()
            if playwright_inst:
                with contextlib.suppress(Exception):
                    playwright_inst.stop()


class PageNavigator:
    """页面导航器，负责网页加载、等待及 Cookie 弹窗处理。"""
    
    def load(self, page, url: str, *, strategy: PageLoadStrategy, task_id: str) -> bool:
        """根据指定的策略加载页面。"""
        logger = get_logger()
        
        # 统一设置较短的导航超时
        nav_timeout = 25000 
        
        try:
            # 1. 尝试初始加载 (至少等待到 commit)
            page.goto(url, wait_until="commit", timeout=nav_timeout)
            
            # 2. 根据策略等待
            if strategy == PageLoadStrategy.NETWORK_IDLE:
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                    return True
                except TimeoutError:
                    logger.warning("[%s] networkidle 等待超时，尝试继续", task_id)
            
            # 默认确保 domcontentloaded
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            page.wait_for_timeout(1000) # 基础沉降
            return True
            
        except Exception as exc:
            logger.error("[%s] 页面加载失败: %s", task_id, exc)
            return False

    def handle_cookie_consent(self, page) -> None:
        """自动点击常见的 Cookie 同意按钮以避免遮挡正文。"""
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


