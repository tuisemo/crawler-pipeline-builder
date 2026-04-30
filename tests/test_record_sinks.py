from pathlib import Path
from types import SimpleNamespace
import sqlite3

from backend.runtime import record_sinks


def make_test_workspace(name: str) -> Path:
    root = Path(__file__).resolve().parent / ".tmp" / name
    if root.exists():
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        root.rmdir()
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_emit_records_writes_sqlite_with_upsert(monkeypatch):
    workspace_root = make_test_workspace("record-sinks-sqlite")
    monkeypatch.setattr(record_sinks, "WORKSPACE_ROOT", workspace_root)

    node_data = SimpleNamespace(
        output_mode="sqlite",
        sqlite_path="output/products.db",
        sqlite_table="products",
        write_mode="upsert",
        dedupe_keys=["detail_url"],
        batch_size=10,
    )

    first = [{"detail_url": "https://example.com/p/1", "title": "One", "price": 10}]
    second = [{"detail_url": "https://example.com/p/1", "title": "One updated", "price": 12}]

    record_sinks.emit_records(node_data, first, {"page_url": "https://example.com/list"})
    result = record_sinks.emit_records(node_data, second, {"page_url": "https://example.com/list"})

    assert result["output_mode"] == "sqlite"
    assert result["stored_count"] == 1

    db_path = workspace_root / "output" / "products.db"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT detail_url, title, price, _source_url FROM products").fetchone()
    assert row == ("https://example.com/p/1", "One updated", 12, "https://example.com/list")


def test_emit_records_sqlite_upsert_falls_back_to_hash_when_dedupe_key_missing(monkeypatch):
    workspace_root = make_test_workspace("record-sinks-sqlite-hash-fallback")
    monkeypatch.setattr(record_sinks, "WORKSPACE_ROOT", workspace_root)

    node_data = SimpleNamespace(
        output_mode="sqlite",
        sqlite_path="output/products.db",
        sqlite_table="products",
        write_mode="upsert",
        dedupe_keys=["detail_url"],
        batch_size=10,
    )

    duplicate = [{"title": "One", "price": 10, "detail_url": None}]

    record_sinks.emit_records(node_data, duplicate, {"page_url": "https://example.com/list"})
    result = record_sinks.emit_records(node_data, duplicate, {"page_url": "https://example.com/list"})

    assert result["output_mode"] == "sqlite"
    assert result["stored_count"] == 1

    db_path = workspace_root / "output" / "products.db"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT title, price, detail_url, _identity_key FROM products").fetchall()
    assert rows == [("One", 10, None, rows[0][3])]
    assert rows[0][3].startswith("hash:")


def test_emit_records_initializes_planned_sqlite_columns_without_rows(monkeypatch):
    workspace_root = make_test_workspace("record-sinks-sqlite-planned-columns")
    monkeypatch.setattr(record_sinks, "WORKSPACE_ROOT", workspace_root)

    node_data = SimpleNamespace(
        output_mode="sqlite",
        sqlite_path="output/products.db",
        sqlite_table="products",
        write_mode="upsert",
        dedupe_keys=["detail_url"],
        batch_size=10,
    )

    result = record_sinks.emit_records(
        node_data,
        [],
        {
            "page_url": "https://example.com/list",
            "planned_fields": ["title", "price", "detail_url"],
        },
    )

    assert result["output_mode"] == "sqlite"
    assert result["stored_count"] == 0

    db_path = workspace_root / "output" / "products.db"
    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()]

    assert columns == [
        "detail_url",
        "price",
        "title",
        "_identity_key",
        "_run_id",
        "_source_url",
        "_emitted_at",
        "_record_hash",
    ]
