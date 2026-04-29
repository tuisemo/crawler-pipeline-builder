"""Execution sandbox for generated crawler scripts.

This is a bounded subprocess sandbox: each run gets an isolated working
directory, a timeout, captured stdout/stderr, and a JSONL execution log.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from typing import Any

from backend.core.app_logging import LOG_DIR, audit_event, serialize_for_log


SANDBOX_ROOT = LOG_DIR / "script-sandbox"
MAX_CAPTURE_CHARS = 20000


@dataclass
class ScriptSandboxResult:
    success: bool
    run_id: str
    backend: str
    script_path: str
    log_path: str
    exit_code: int | None
    timed_out: bool
    duration_seconds: float
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_filename(filename: str | None) -> str:
    candidate = (filename or "generated_crawler.py").strip() or "generated_crawler.py"
    candidate = Path(candidate).name
    candidate = re.sub(r"[^a-zA-Z0-9_.-]+", "_", candidate)
    if not candidate.endswith(".py"):
        candidate = f"{candidate}.py"
    return candidate


def _tail(value: str, max_chars: int = MAX_CAPTURE_CHARS) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _write_log(log_path: Path, event_type: str, **payload: Any) -> None:
    record = {
        "timestamp": time.time(),
        "event_type": event_type,
        **{key: serialize_for_log(value) for key, value in payload.items()},
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _run_with_subprocess(script_path: Path, run_dir: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(run_dir),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
def run_generated_script_sandbox(
    script: str,
    *,
    filename: str | None = None,
    timeout_seconds: int = 60,
    metadata: dict[str, Any] | None = None,
) -> ScriptSandboxResult:
    run_id = f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    run_dir = SANDBOX_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    script_path = run_dir / _safe_filename(filename)
    log_path = run_dir / "execution.jsonl"
    script_path.write_text(script or "", encoding="utf-8")

    timeout = timeout_seconds if isinstance(timeout_seconds, int) and timeout_seconds > 0 else 60
    resolved_backend = "subprocess"
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "CRAWLER_SANDBOX_MODE": "1",
        "CRAWLER_SANDBOX_RUN_ID": run_id,
        "CRAWLER_SANDBOX_DIR": str(run_dir),
        "CRAWLER_SANDBOX_TIMEOUT_SECONDS": str(timeout),
    }

    started = time.perf_counter()
    _write_log(
        log_path,
        "sandbox_started",
        run_id=run_id,
        backend=resolved_backend,
        script_path=str(script_path),
        timeout_seconds=timeout,
        metadata=metadata or {},
    )
    audit_event(
        "script_sandbox_started",
        run_id=run_id,
        backend=resolved_backend,
        script_path=str(script_path),
        timeout_seconds=timeout,
        metadata=metadata or {},
    )

    try:
        completed = _run_with_subprocess(script_path, run_dir, env, timeout)
        duration = round(time.perf_counter() - started, 3)
        result = ScriptSandboxResult(
            success=completed.returncode == 0,
            run_id=run_id,
            backend=resolved_backend,
            script_path=str(script_path),
            log_path=str(log_path),
            exit_code=completed.returncode,
            timed_out=False,
            duration_seconds=duration,
            stdout_tail=_tail(completed.stdout or ""),
            stderr_tail=_tail(completed.stderr or ""),
            error=None if completed.returncode == 0 else f"Script exited with code {completed.returncode}",
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.perf_counter() - started, 3)
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(errors="replace")
        result = ScriptSandboxResult(
            success=False,
            run_id=run_id,
            backend=resolved_backend,
            script_path=str(script_path),
            log_path=str(log_path),
            exit_code=None,
            timed_out=True,
            duration_seconds=duration,
            stdout_tail=_tail(stdout),
            stderr_tail=_tail(stderr),
            error=f"Script sandbox timed out after {timeout} seconds",
        )
    except Exception as exc:
        duration = round(time.perf_counter() - started, 3)
        result = ScriptSandboxResult(
            success=False,
            run_id=run_id,
            backend=resolved_backend,
            script_path=str(script_path),
            log_path=str(log_path),
            exit_code=None,
            timed_out=False,
            duration_seconds=duration,
            error=str(exc),
        )

    _write_log(log_path, "sandbox_completed", result=result.to_dict())
    audit_event("script_sandbox_completed", **result.to_dict())
    return result
