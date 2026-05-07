from __future__ import annotations

import asyncio
import time
from concurrent.futures import Future as CFFuture


class ExtPageSession:
    def __init__(self, conn, tab_id: int, url: str | None = None):
        self.id = f"ext-{tab_id}"
        self._conn = conn
        self.tab_id = tab_id
        self.url = url or "about:blank"
        self.created_at = time.time()
        self.last_used = time.time()
        self._closed = False

    def touch(self):
        self.last_used = time.time()

    def is_alive(self) -> bool:
        return not self._closed

    def close(self):
        self._closed = True

    def _sync(self, method: str, params: dict, *, timeout: float = 30.0) -> dict:
        future: CFFuture = asyncio.run_coroutine_threadsafe(
            self._conn.send(method, params, self.tab_id, timeout),
            self._conn._loop,
        )
        result = future.result(timeout=timeout + 2)
        self.touch()
        return result.get("result", {})

    def _exec(self, fn: str, args: list, *, timeout: float = 30.0) -> dict:
        return self._sync("exec_script", {"fn": fn, "args": args}, timeout=timeout)

    def navigate(self, url: str, timeout: int = 30000):
        self.url = url
        self._sync("navigate", {"url": url}, timeout=timeout / 1000)

    def evaluate(self, js: str):
        return self._exec("__eval__", [js]).get("value")

    def query_selector_all(self, selector: str) -> list:
        return self._exec("sea_query_all", [selector]).get("elements", [])

    def highlight_selector(self, selector: str, clear_after_ms: int = 2200) -> int:
        return int(self._exec("sea_highlight", [selector, clear_after_ms]).get("highlighted_count", 0))

    def clear_highlight(self) -> None:
        self._exec("sea_clear_highlight", [])

    def auto_detect(self) -> dict:
        return self._exec("sea_auto_detect", [])

    def extract_html(self, selector: str, max_items: int = 3, include_pagination: bool = False) -> dict:
        fn = "sea_extract_html_with_pagination" if include_pagination else "sea_extract_html"
        return self._exec(fn, [selector, max_items])

    def test_selector(self, selector: str, max_samples: int = 5) -> dict:
        return self._exec("sea_query_all", [selector, max_samples])

    def extract_fields(self, item_selector: str, fields: list[dict]) -> list[dict]:
        return self._exec("sea_extract_fields", [item_selector, fields]).get("records", [])

    def click_element(self, selector: str) -> dict:
        return self._exec("sea_click_and_observe", [selector, 5000], timeout=10.0)

    def scroll_to_bottom(self) -> None:
        self._exec("sea_scroll_bottom", [])
