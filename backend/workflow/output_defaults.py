"""Shared defaults for workflow output configuration."""

from __future__ import annotations


DEFAULT_OUTPUT_MODE = "memory"
DEFAULT_JSON_OUTPUT_PATH = "output/crawler_output.json"
DEFAULT_SQLITE_OUTPUT_PATH = "output/crawler_output.db"
DEFAULT_SQLITE_TABLE = "records"
DEFAULT_WRITE_MODE = "append"
DEFAULT_BATCH_SIZE = 50


def default_output_config() -> dict[str, object]:
    return {
        "mode": DEFAULT_OUTPUT_MODE,
        "json_file_path": DEFAULT_JSON_OUTPUT_PATH,
        "sqlite_path": DEFAULT_SQLITE_OUTPUT_PATH,
        "sqlite_table": DEFAULT_SQLITE_TABLE,
        "write_mode": DEFAULT_WRITE_MODE,
        "dedupe_keys": [],
        "batch_size": DEFAULT_BATCH_SIZE,
    }
