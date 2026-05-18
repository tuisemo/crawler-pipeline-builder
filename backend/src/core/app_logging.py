"""Application logging helpers for runtime diagnostics and agent forensics."""

from __future__ import annotations

import json
import datetime as dt
import logging
import threading
from pathlib import Path
from typing import Any


SERVER_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = SERVER_ROOT / "logs"
OUTPUT_DIR = SERVER_ROOT / "output"

_CONFIGURED = False
_CONFIGURE_LOCK = threading.Lock()


def _build_daily_log_path(prefix: str, extension: str, current_date: dt.date | None = None) -> Path:
    day = current_date or dt.date.today()
    return LOG_DIR / f"{prefix}-{day.isoformat()}.{extension}"


class DailyNamedFileHandler(logging.Handler):
    """A lightweight file handler that switches output files when the local date changes."""

    def __init__(self, prefix: str, extension: str, level: int = logging.NOTSET, encoding: str = "utf-8"):
        super().__init__(level=level)
        self.prefix = prefix
        self.extension = extension
        self.encoding = encoding
        self._current_date: dt.date | None = None
        self._stream = None
        self.baseFilename = ""

    def _ensure_stream(self) -> None:
        today = dt.date.today()
        if self._current_date == today and self._stream is not None:
            return

        if self._stream is not None:
            self._stream.close()
            self._stream = None

        path = _build_daily_log_path(self.prefix, self.extension, today)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = open(path, "a", encoding=self.encoding)
        self._current_date = today
        self.baseFilename = str(path)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_stream()
            if self._stream is None:
                return
            message = self.format(record)
            self._stream.write(f"{message}\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
        finally:
            super().close()


def serialize_for_log(value: Any, max_chars: int = 50000, max_depth: int = 20, _depth: int = 0) -> Any:
    """Convert nested values to JSON-safe log payloads with bounded text fields."""
    if _depth >= max_depth:
        return repr(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        overflow = len(value) - max_chars
        return f"{value[:max_chars]}\n...[truncated {overflow} chars]"
    if isinstance(value, dict):
        return {str(key): serialize_for_log(item, max_chars=max_chars, max_depth=max_depth, _depth=_depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialize_for_log(item, max_chars=max_chars, max_depth=max_depth, _depth=_depth + 1) for item in value]
    return serialize_for_log(str(value), max_chars=max_chars, max_depth=max_depth, _depth=_depth + 1)


def configure_logging() -> None:
    """Configure app + audit loggers once per process."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    with _CONFIGURE_LOCK:
        if _CONFIGURED:
            return

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        standard_formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        app_log_path = str(_build_daily_log_path("app", "log"))
        if not any(isinstance(handler, DailyNamedFileHandler) and getattr(handler, "baseFilename", "") == app_log_path for handler in root_logger.handlers):
            file_handler = DailyNamedFileHandler("app", "log", encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(standard_formatter)
            root_logger.addHandler(file_handler)

        if not any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(standard_formatter)
            root_logger.addHandler(console_handler)

        audit_logger = logging.getLogger("crawler_workflow.audit")
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False
        audit_log_path = str(_build_daily_log_path("audit", "jsonl"))
        if not any(isinstance(handler, DailyNamedFileHandler) and getattr(handler, "baseFilename", "") == audit_log_path for handler in audit_logger.handlers):
            audit_handler = DailyNamedFileHandler("audit", "jsonl", encoding="utf-8")
            audit_handler.setLevel(logging.INFO)
            audit_handler.setFormatter(logging.Formatter("%(message)s"))
            audit_logger.addHandler(audit_handler)

        _CONFIGURED = True


def audit_event(event_type: str, **payload: Any) -> None:
    """Write a structured audit event as JSONL."""
    configure_logging()
    record = {
        "event_type": event_type,
        **{key: serialize_for_log(value) for key, value in payload.items()},
    }
    logging.getLogger("crawler_workflow.audit").info(json.dumps(record, ensure_ascii=False))
