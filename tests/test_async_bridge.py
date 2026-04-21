import asyncio
import threading

import pytest

from backend.async_bridge import run_blocking


@pytest.mark.anyio
async def test_run_blocking_executes_callable_off_event_loop_thread():
    loop_thread_id = threading.get_ident()

    worker_thread_id = await run_blocking(threading.get_ident)

    assert worker_thread_id != loop_thread_id


@pytest.mark.anyio
async def test_run_blocking_propagates_callable_exceptions():
    def fail():
        raise RuntimeError("bridge failure")

    with pytest.raises(RuntimeError, match="bridge failure"):
        await run_blocking(fail)
