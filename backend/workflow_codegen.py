"""Deterministic workflow code generator (ExecutionPlan -> Python script)."""

from __future__ import annotations

import json
import textwrap
from typing import Any

from .output_defaults import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_JSON_OUTPUT_PATH,
    DEFAULT_OUTPUT_MODE,
    DEFAULT_SQLITE_OUTPUT_PATH,
    DEFAULT_SQLITE_TABLE,
    DEFAULT_WRITE_MODE,
)


def _json_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def generate_playwright_skeleton(plan: dict[str, Any]) -> str:
    """Generate a deterministic Playwright Python crawler skeleton."""
    entry_url = plan.get("entry_url", "")
    item_selector = plan.get("item_selector", "")
    field_specs = plan.get("field_specs", [])
    pagination = plan.get("pagination", {}) or {}
    output = plan.get("output", {}) or {}
    limits = plan.get("limits", {}) or {}

    max_items = int(limits.get("max_items", 50))
    max_pages = int(limits.get("max_pages", 10))
    pagination_selector = str(pagination.get("selector", "") or "")
    pagination_strategy = str(pagination.get("strategy", "click_next") or "click_next")
    output_mode = str(output.get("mode", DEFAULT_OUTPUT_MODE) or DEFAULT_OUTPUT_MODE)
    json_file_path = str(output.get("json_file_path", DEFAULT_JSON_OUTPUT_PATH) or DEFAULT_JSON_OUTPUT_PATH)
    sqlite_path = str(output.get("sqlite_path", DEFAULT_SQLITE_OUTPUT_PATH) or DEFAULT_SQLITE_OUTPUT_PATH)
    sqlite_table = str(output.get("sqlite_table", DEFAULT_SQLITE_TABLE) or DEFAULT_SQLITE_TABLE)
    write_mode = str(output.get("write_mode", DEFAULT_WRITE_MODE) or DEFAULT_WRITE_MODE)
    dedupe_keys = output.get("dedupe_keys", [])
    if not isinstance(dedupe_keys, list):
        dedupe_keys = []
    batch_size = int(output.get("batch_size", DEFAULT_BATCH_SIZE) or DEFAULT_BATCH_SIZE)

    field_specs_literal = _json_literal(field_specs)
    normalization_rules = {
        str(field.get("name")): str(field.get("clean_data_type"))
        for field in field_specs
        if isinstance(field, dict)
        and isinstance(field.get("name"), str)
        and isinstance(field.get("clean_data_type"), str)
        and field.get("name")
        and field.get("clean_data_type")
    }
    normalization_rules_literal = _json_literal(normalization_rules)

    script = f"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


ENTRY_URL = {entry_url!r}
ITEM_SELECTOR = {item_selector!r}
FIELD_SPECS = {field_specs_literal}
NORMALIZATION_RULES = {normalization_rules_literal}
MAX_ITEMS = {max_items}
MAX_PAGES = {max_pages}
PAGINATION_SELECTOR = {pagination_selector!r}
PAGINATION_STRATEGY = {pagination_strategy!r}
OUTPUT_MODE = {output_mode!r}
OUTPUT_JSON_FILE = {json_file_path!r}
OUTPUT_SQLITE_PATH = {sqlite_path!r}
OUTPUT_SQLITE_TABLE = {sqlite_table!r}
WRITE_MODE = {write_mode!r}
DEDUPE_KEYS = {_json_literal(dedupe_keys)}
OUTPUT_BATCH_SIZE = {batch_size}
LAST_PERSIST_INFO: dict[str, Any] = {{}}


def normalize_value(value: Any, data_type: str | None, page_url: str) -> Any:
    if value is None or not data_type:
        return value
    normalized_type = str(data_type).strip().lower()
    text = str(value).strip()
    if not text:
        return value

    if normalized_type == "price":
        numbers = re.sub(r"[^0-9.,-]", "", text).replace(",", "")
        try:
            return float(numbers) if "." in numbers else int(numbers)
        except Exception:
            return text
    if normalized_type == "count":
        compact = text.lower().replace(",", "")
        multiplier = 1
        if "万" in compact:
            multiplier = 10000
            compact = compact.replace("万", "")
        elif compact.endswith("k"):
            multiplier = 1000
            compact = compact[:-1]
        elif compact.endswith("m"):
            multiplier = 1000000
            compact = compact[:-1]
        digits = re.sub(r"[^0-9.]", "", compact)
        try:
            return int(float(digits) * multiplier)
        except Exception:
            return text
    if normalized_type == "phone":
        digits = re.sub(r"\\D", "", text)
        return digits or text
    if normalized_type == "email":
        return text.lower()
    if normalized_type == "url":
        return urljoin(page_url, text)
    if normalized_type == "bool":
        lowered = text.lower()
        if lowered in ("true", "1", "yes", "y", "是"):
            return True
        if lowered in ("false", "0", "no", "n", "否"):
            return False
        return text
    if normalized_type == "rating":
        digits = re.findall(r"[0-9]+(?:\\.[0-9]+)?", text)
        if not digits:
            return text
        try:
            rating = float(digits[0])
            return max(0.0, min(5.0, rating))
        except Exception:
            return text
    return text


def extract_record(item, page_url: str) -> dict[str, Any]:
    record: dict[str, Any] = {{}}
    for field in FIELD_SPECS:
        name = field.get("name", "")
        selector = field.get("selector", "")
        ext_type = field.get("type", "text")
        if not name or not selector:
            continue

        try:
            elements = item.query_selector_all(selector)
        except Exception:
            elements = []
        if not elements:
            record[name] = None
            continue

        first = elements[0]
        value = None
        if ext_type == "text":
            try:
                value = (first.inner_text() or "").strip()
            except Exception:
                value = None
        elif ext_type.startswith("attr:"):
            parts = ext_type.split(":")
            attr_name = parts[1] if len(parts) > 1 else ""
            is_abs = "abs" in parts[2:]
            raw = first.get_attribute(attr_name) if attr_name else None
            value = urljoin(page_url, raw) if raw and is_abs else raw
        elif ext_type == "html":
            try:
                value = first.inner_html()
            except Exception:
                value = None
        else:
            # Extend here for additional extraction types.
            value = None
        record[name] = normalize_value(value, NORMALIZATION_RULES.get(name), page_url)
    return record


def resolve_output_path(relative_path: str) -> Path:
    path = Path(relative_path or {DEFAULT_JSON_OUTPUT_PATH!r})
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_identity_key(record: dict[str, Any]) -> str:
    if DEDUPE_KEYS and all(key in record and record.get(key) is not None for key in DEDUPE_KEYS):
        payload = {{key: record.get(key) for key in DEDUPE_KEYS}}
        return f"dedupe:{{json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)}}"
    return f"hash:{{record_hash(record)}}"


def merge_records(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {{}}
    for record in [*existing, *incoming]:
        key = record_identity_key(record)
        if key in index_by_key:
            merged[index_by_key[key]] = record
        else:
            index_by_key[key] = len(merged)
            merged.append(record)
    return merged


def load_existing_json_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("JSON output file must contain an array of records")
    return [item for item in parsed if isinstance(item, dict)]


def persist_json_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    output_path = resolve_output_path(OUTPUT_JSON_FILE)
    existing = load_existing_json_records(output_path)
    if WRITE_MODE == "upsert":
        merged = merge_records(existing, records)
    else:
        merged = [*existing, *records]
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    return {{
        "mode": "json_file",
        "target": str(output_path),
        "stored_count": len(merged),
    }}


def normalize_sqlite_table(name: str) -> str:
    candidate = str(name or "records").strip() or "records"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError("OUTPUT_SQLITE_TABLE must use letters, numbers, and underscores only")
    return candidate


def quote_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid SQLite identifier: {{name}}")
    return f'"{{name}}"'


def infer_sqlite_affinity(values: list[Any]) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            return "INTEGER"
        if isinstance(value, int):
            return "INTEGER"
        if isinstance(value, float):
            return "REAL"
        return "TEXT"
    return "TEXT"


def encode_sqlite_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def chunk_records(records: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    chunk_size = size if size > 0 else len(records) or 1
    return [records[index:index + chunk_size] for index in range(0, len(records), chunk_size)]


def ensure_sqlite_schema(conn: sqlite3.Connection, table_name: str, records: list[dict[str, Any]]) -> list[str]:
    user_columns = sorted({{key for record in records for key in record.keys() if isinstance(key, str) and key}})
    user_columns = sorted(set(user_columns) | set(DEDUPE_KEYS))
    metadata_columns = {{
        "identity_key": "TEXT PRIMARY KEY",
        "run_id": "TEXT",
        "source_url": "TEXT",
        "created_at": "TEXT",
        "record_hash": "TEXT",
    }}

    existing = {{
        str(row[1])
        for row in conn.execute(f'PRAGMA table_info({{quote_ident(table_name)}})').fetchall()
    }}
    if not existing:
        column_defs = []
        for column in user_columns:
            values = [record.get(column) for record in records]
            column_defs.append(f'{{quote_ident(column)}} {{infer_sqlite_affinity(values)}}')
        for column, affinity in metadata_columns.items():
            column_defs.append(f'{{quote_ident(column)}} {{affinity}}')
        conn.execute(f'CREATE TABLE IF NOT EXISTS {{quote_ident(table_name)}} ({{", ".join(column_defs)}})')
        existing = {{
            str(row[1])
            for row in conn.execute(f'PRAGMA table_info({{quote_ident(table_name)}})').fetchall()
        }}

    for column in user_columns:
        if column in existing:
            continue
        values = [record.get(column) for record in records]
        conn.execute(f'ALTER TABLE {{quote_ident(table_name)}} ADD COLUMN {{quote_ident(column)}} {{infer_sqlite_affinity(values)}}')
    for column, affinity in metadata_columns.items():
        if column not in existing:
            conn.execute(f'ALTER TABLE {{quote_ident(table_name)}} ADD COLUMN {{quote_ident(column)}} {{affinity}}')

    # Primary key already acts as unique index for identity_key
    conn.commit()
    return user_columns


def persist_sqlite_records(records: list[dict[str, Any]], source_url: str) -> dict[str, Any]:
    output_path = resolve_output_path(OUTPUT_SQLITE_PATH)
    table_name = normalize_sqlite_table(OUTPUT_SQLITE_TABLE)
    with sqlite3.connect(output_path) as conn:
        user_columns = ensure_sqlite_schema(conn, table_name, records)
        metadata_columns = ["identity_key", "run_id", "source_url", "created_at", "record_hash"]
        all_columns = [*user_columns, *metadata_columns]
        placeholders = ", ".join("?" for _ in all_columns)
        insert_sql = (
            f'INSERT INTO {{quote_ident(table_name)}} '
            f'({{", ".join(quote_ident(column) for column in all_columns)}}) '
            f'VALUES ({{placeholders}})'
        )
        if WRITE_MODE == "upsert":
            conflict_columns = ["identity_key"]
            update_columns = [column for column in all_columns if column not in conflict_columns]
            if update_columns:
                insert_sql += (
                    f' ON CONFLICT ({{", ".join(quote_ident(column) for column in conflict_columns)}}) DO UPDATE SET '
                    + ", ".join(f'{{quote_ident(column)}} = excluded.{{quote_ident(column)}}' for column in update_columns)
                )
            else:
                insert_sql += (
                    f' ON CONFLICT ({{", ".join(quote_ident(column) for column in conflict_columns)}}) DO NOTHING'
                )

        created_at = datetime.now(timezone.utc).isoformat()
        for chunk in chunk_records(records, OUTPUT_BATCH_SIZE):
            rows = []
            for record in chunk:
                row = [encode_sqlite_value(record.get(column)) for column in user_columns]
                row.extend([
                    record_identity_key(record),
                    "standalone-run" if "run_id" in metadata_columns else None, # Placeholder for standalone run
                    source_url or None,
                    created_at,
                    record_hash(record),
                ])
                rows.append(tuple(row))
            with conn:
                conn.executemany(insert_sql, rows)
        stored_count = conn.execute(f'SELECT COUNT(*) FROM {{quote_ident(table_name)}}').fetchone()[0]
    return {{
        "mode": "sqlite",
        "target": str(output_path),
        "stored_count": int(stored_count),
        "table": table_name,
    }}


def persist_records(records: list[dict[str, Any]], source_url: str) -> dict[str, Any]:
    mode = OUTPUT_MODE if OUTPUT_MODE in {{"json_file", "sqlite"}} else "json_file"
    if mode == "sqlite":
        return persist_sqlite_records(records, source_url)
    return persist_json_records(records)


def click_next_page(page) -> bool:
    if not PAGINATION_SELECTOR:
        return False
    next_buttons = page.query_selector_all(PAGINATION_SELECTOR)
    if not next_buttons:
        return False
    next_button = next_buttons[0]
    try:
        next_button.scroll_into_view_if_needed(timeout=3000)
        next_button.click(timeout=5000)
        page.wait_for_timeout(1200)
        return True
    except Exception:
        return False


def run() -> list[dict[str, Any]]:
    global LAST_PERSIST_INFO
    if not ENTRY_URL:
        raise ValueError("ENTRY_URL is required")
    if not ITEM_SELECTOR:
        raise ValueError("ITEM_SELECTOR is required")

    records: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        try:
            page.goto(ENTRY_URL, wait_until="domcontentloaded", timeout=30000)
        except PlaywrightTimeoutError:
            page.goto(ENTRY_URL, wait_until="load", timeout=45000)

        for page_idx in range(MAX_PAGES):
            items = page.query_selector_all(ITEM_SELECTOR)
            for item in items:
                records.append(extract_record(item, page.url))
                if len(records) >= MAX_ITEMS:
                    break
            if len(records) >= MAX_ITEMS:
                break

            if PAGINATION_STRATEGY == "click_next":
                if not click_next_page(page):
                    break
            else:
                # Extend here for load_more / infinite_scroll.
                break

        # Standalone scripts always persist an artifact, even when the graph used memory-only emit_record mode.
        LAST_PERSIST_INFO = persist_records(records, page.url)

        context.close()
        browser.close()
    return records


if __name__ == "__main__":
    output = run()
    target = LAST_PERSIST_INFO.get("target", OUTPUT_JSON_FILE)
    mode = LAST_PERSIST_INFO.get("mode", OUTPUT_MODE)
    print(f"Extracted {{len(output)}} records -> {{target}} ({{mode}})")
"""
    return textwrap.dedent(script).strip() + "\n"
