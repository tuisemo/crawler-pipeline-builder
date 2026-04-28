"""Record sink helpers for optional durable workflow output."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .output_defaults import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_JSON_OUTPUT_PATH,
    DEFAULT_OUTPUT_MODE,
    DEFAULT_SQLITE_OUTPUT_PATH,
    DEFAULT_SQLITE_TABLE,
    DEFAULT_WRITE_MODE,
)


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_OUTPUT_MODES = {"memory", "json_file", "sqlite"}
SUPPORTED_WRITE_MODES = {"append", "upsert"}
SQLITE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RecordSinkError(RuntimeError):
    """Raised when a configured durable record sink cannot be used."""


def emit_records(node_data: Any, records: list[dict[str, Any]], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist records using the configured sink and return sink metadata."""
    context = context or {}
    mode = normalize_output_mode(getattr(node_data, "output_mode", None))
    if mode == "memory":
        return {"output_mode": "memory", "written_count": len(records)}

    write_mode = normalize_write_mode(getattr(node_data, "write_mode", None))
    dedupe_keys = normalize_dedupe_keys(getattr(node_data, "dedupe_keys", None))
    batch_size = normalize_batch_size(getattr(node_data, "batch_size", None))

    if mode == "json_file":
        output_path = resolve_output_path(
            getattr(node_data, "json_file_path", None),
            default_relative_path=DEFAULT_JSON_OUTPUT_PATH,
        )
        return write_json_records(
            records,
            output_path=output_path,
            write_mode=write_mode,
            dedupe_keys=dedupe_keys,
        )

    output_path = resolve_output_path(
        getattr(node_data, "sqlite_path", None),
        default_relative_path=DEFAULT_SQLITE_OUTPUT_PATH,
    )
    table_name = normalize_sqlite_table(getattr(node_data, "sqlite_table", None))
    return write_sqlite_records(
        records,
        output_path=output_path,
        table_name=table_name,
        write_mode=write_mode,
        dedupe_keys=dedupe_keys,
        batch_size=batch_size,
        source_url=str(context.get("page_url") or ""),
        run_id=str(context.get("run_id") or ""),
    )


def normalize_output_mode(value: Any) -> str:
    mode = str(value or DEFAULT_OUTPUT_MODE).strip().lower()
    return mode if mode in SUPPORTED_OUTPUT_MODES else DEFAULT_OUTPUT_MODE


def normalize_write_mode(value: Any) -> str:
    mode = str(value or DEFAULT_WRITE_MODE).strip().lower()
    return mode if mode in SUPPORTED_WRITE_MODES else DEFAULT_WRITE_MODE


def normalize_dedupe_keys(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []

    normalized: list[str] = []
    seen = set()
    for raw in raw_values:
        if not isinstance(raw, str):
            continue
        key = raw.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def normalize_batch_size(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_BATCH_SIZE
    return parsed if parsed > 0 else DEFAULT_BATCH_SIZE


def normalize_sqlite_table(value: Any) -> str:
    name = str(value or DEFAULT_SQLITE_TABLE).strip()
    if not SQLITE_IDENTIFIER_RE.fullmatch(name):
        raise RecordSinkError("sqlite_table must be a valid SQLite identifier using letters, numbers, and underscores only.")
    return name


def resolve_output_path(raw_path: Any, default_relative_path: str) -> Path:
    value = str(raw_path or "").strip() or default_relative_path
    target = (WORKSPACE_ROOT / value).resolve()
    try:
        target.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise RecordSinkError("Output path resolves outside the project workspace.") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_json_records(
    records: list[dict[str, Any]],
    *,
    output_path: Path,
    write_mode: str,
    dedupe_keys: list[str],
) -> dict[str, Any]:
    existing = load_json_records(output_path)
    if write_mode == "upsert":
        merged = merge_records(existing, records, dedupe_keys)
    else:
        merged = [*existing, *records]

    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "output_mode": "json_file",
        "output_path": str(output_path),
        "write_mode": write_mode,
        "written_count": len(records),
        "stored_count": len(merged),
    }


def load_json_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise RecordSinkError("JSON output file must contain a top-level array of records.")
    return [item for item in parsed if isinstance(item, dict)]


def merge_records(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], dedupe_keys: list[str]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}

    for record in existing:
        key = record_identity_key(record, dedupe_keys)
        if key in index_by_key:
            merged[index_by_key[key]] = record
        else:
            index_by_key[key] = len(merged)
            merged.append(record)

    for record in incoming:
        key = record_identity_key(record, dedupe_keys)
        if key in index_by_key:
            merged[index_by_key[key]] = record
        else:
            index_by_key[key] = len(merged)
            merged.append(record)
    return merged


def record_identity_key(record: dict[str, Any], dedupe_keys: list[str]) -> str:
    if dedupe_keys and all(key in record and record.get(key) is not None for key in dedupe_keys):
        payload = {key: record.get(key) for key in dedupe_keys}
        return f"dedupe:{json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)}"
    return f"hash:{record_hash(record)}"


def record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_sqlite_records(
    records: list[dict[str, Any]],
    *,
    output_path: Path,
    table_name: str,
    write_mode: str,
    dedupe_keys: list[str],
    batch_size: int,
    source_url: str,
    run_id: str,
) -> dict[str, Any]:
    if not records:
        return {
            "output_mode": "sqlite",
            "output_path": str(output_path),
            "sqlite_table": table_name,
            "write_mode": write_mode,
            "written_count": 0,
            "stored_count": 0,
        }

    user_columns = sorted({key for record in records for key in record.keys() if isinstance(key, str) and key})
    all_user_columns = sorted(set(user_columns) | set(dedupe_keys))

    with sqlite3.connect(output_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_sqlite_schema(
            conn,
            table_name=table_name,
            user_columns=all_user_columns,
            sample_records=records,
            write_mode=write_mode,
            dedupe_keys=dedupe_keys,
        )

        for chunk in chunk_records(records, batch_size):
            persist_sqlite_chunk(
                conn,
                table_name=table_name,
                user_columns=all_user_columns,
                records=chunk,
                write_mode=write_mode,
                dedupe_keys=dedupe_keys,
                source_url=source_url,
                run_id=run_id,
            )
        stored_count = count_sqlite_rows(conn, table_name)

    return {
        "output_mode": "sqlite",
        "output_path": str(output_path),
        "sqlite_table": table_name,
        "write_mode": write_mode,
        "written_count": len(records),
        "stored_count": stored_count,
    }


def ensure_sqlite_schema(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    user_columns: list[str],
    sample_records: list[dict[str, Any]],
    write_mode: str,
    dedupe_keys: list[str],
) -> None:
    metadata_columns = {
        "identity_key": "TEXT PRIMARY KEY",
        "run_id": "TEXT",
        "source_url": "TEXT",
        "created_at": "TEXT",
        "record_hash": "TEXT",
    }
    column_types = {column: infer_sqlite_affinity(column, sample_records) for column in user_columns}
    existing = get_existing_columns(conn, table_name)

    if not existing:
        column_defs = [f'{quote_ident(column)} {affinity}' for column, affinity in column_types.items()]
        column_defs.extend(f'{quote_ident(column)} {affinity}' for column, affinity in metadata_columns.items())
        conn.execute(f'CREATE TABLE IF NOT EXISTS {quote_ident(table_name)} ({", ".join(column_defs)})')
        existing = get_existing_columns(conn, table_name)

    for column, affinity in {**column_types, **metadata_columns}.items():
        if column in existing:
            continue
        conn.execute(f'ALTER TABLE {quote_ident(table_name)} ADD COLUMN {quote_ident(column)} {affinity}')

    # Primary key already acts as unique index for identity_key
    conn.commit()


def get_existing_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f'PRAGMA table_info({quote_ident(table_name)})').fetchall()
    except sqlite3.OperationalError:
        return set()
    return {str(row[1]) for row in rows}


def infer_sqlite_affinity(column: str, sample_records: list[dict[str, Any]]) -> str:
    for record in sample_records:
        value = record.get(column)
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


def persist_sqlite_chunk(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    user_columns: list[str],
    records: list[dict[str, Any]],
    write_mode: str,
    dedupe_keys: list[str],
    source_url: str,
    run_id: str,
) -> None:
    metadata_columns = ["identity_key", "run_id", "source_url", "created_at", "record_hash"]
    all_columns = [*user_columns, *metadata_columns]
    placeholders = ", ".join("?" for _ in all_columns)
    columns_sql = ", ".join(quote_ident(column) for column in all_columns)

    sql = f'INSERT INTO {quote_ident(table_name)} ({columns_sql}) VALUES ({placeholders})'
    if write_mode == "upsert":
        conflict_columns = ["_sea_identity_key"]
        update_columns = [column for column in all_columns if column not in conflict_columns]
        if update_columns:
            updates_sql = ", ".join(f'{quote_ident(column)} = excluded.{quote_ident(column)}' for column in update_columns)
            sql += f' ON CONFLICT ({", ".join(quote_ident(column) for column in conflict_columns)}) DO UPDATE SET {updates_sql}'
        else:
            sql += f' ON CONFLICT ({", ".join(quote_ident(column) for column in conflict_columns)}) DO NOTHING'

    created_at = datetime.now(timezone.utc).isoformat()
    values: list[tuple[Any, ...]] = []
    for record in records:
        row = [encode_sqlite_value(record.get(column)) for column in user_columns]
        row.extend([
            record_identity_key(record, dedupe_keys),
            run_id or None,
            source_url or None,
            created_at,
            record_hash(record),
        ])
        values.append(tuple(row))

    with conn:
        conn.executemany(sql, values)


def encode_sqlite_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def count_sqlite_rows(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f'SELECT COUNT(*) FROM {quote_ident(table_name)}').fetchone()
    return int(row[0]) if row else 0


def quote_ident(identifier: str) -> str:
    if not SQLITE_IDENTIFIER_RE.fullmatch(identifier):
        raise RecordSinkError(f"Invalid SQLite identifier: {identifier}")
    return f'"{identifier}"'


def chunk_records(records: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    if batch_size <= 0:
        return [records]
    return [records[index:index + batch_size] for index in range(0, len(records), batch_size)]
