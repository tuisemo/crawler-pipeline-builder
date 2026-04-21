"""Helpers for running blocking backend work from async FastAPI routes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_blocking(func: Callable[[], T]) -> T:
    """Run synchronous browser work off the active event loop thread."""
    return await asyncio.to_thread(func)
