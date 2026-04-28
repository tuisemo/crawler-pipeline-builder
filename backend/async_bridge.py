"""Helpers for running blocking backend work from async FastAPI routes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")

_BROWSER_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser-ops")


async def run_blocking(func: Callable[[], T]) -> T:
    """Run synchronous browser work on a dedicated single thread.

    Playwright's sync API is not safe to hop across arbitrary worker threads.
    We therefore serialize all browser-backed operations onto one long-lived
    executor thread so page/context objects keep a stable thread affinity.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_BROWSER_EXECUTOR, func)
