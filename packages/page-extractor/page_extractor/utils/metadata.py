"""Metadata and archive helpers for detail extraction artifacts."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tarfile
import time
import uuid
import zipfile
from pathlib import Path

from .logging import get_logger

try:
    import rarfile
except ImportError:  # pragma: no cover - optional dependency
    rarfile = None

try:
    import py7zr
except ImportError:  # pragma: no cover - optional dependency
    py7zr = None


def generate_meta_json(
    file_path: Path,
    source_url: str,
    external_date: str | None = None,
    meta_target_extensions: set[str] | None = None,
) -> bool:
    logger = get_logger()
    meta_target_extensions = meta_target_extensions or {".pdf", ".md", ".doc", ".docx"}
    if file_path.suffix.lower() not in meta_target_extensions:
        return True
    try:
        date_str = external_date or time.strftime("%Y-%m-%d")
        meta = {
            "id": str(uuid.uuid4()),
            "rid": [],
            "data_content": [{"media_type": file_path.suffix.lstrip(".") or "unknown", "content": file_path.name}],
            "annotation": {},
            "original_time": date_str,
            "last_modified_time": date_str,
            "version": "1.0.0",
            "license": "其他",
            "source": "互联网",
            "source_details": source_url,
            "synthetic_data_indicator": 0,
        }
        meta_path = file_path.parent / f"{uuid.uuid4()}.meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True
    except Exception as exc:
        logger.warning("[Meta] Generation failed: %s", exc)
        return False


def extract_archive(archive_path: Path, extract_to: Path) -> list[Path]:
    logger = get_logger()
    extracted_files: list[Path] = []

    def is_safe_member(name: str) -> bool:
        if not name:
            return False
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or re.match(r"^[a-zA-Z]:/", normalized):
            return False
        parts = [part for part in normalized.split("/") if part and part != "."]
        return not any(part == ".." for part in parts)

    try:
        suffix = archive_path.suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(archive_path, "r") as archive:
                for member in archive.infolist():
                    if member.filename.endswith("/") or not is_safe_member(member.filename):
                        continue
                    archive.extract(member, extract_to)
                    extracted_files.append(extract_to / member.filename)
        elif suffix == ".rar" and rarfile is not None:
            with rarfile.RarFile(archive_path, "r") as archive:  # type: ignore[union-attr]
                for member in archive.infolist():
                    if member.isdir() or not is_safe_member(member.filename):
                        continue
                    archive.extract(member, path=extract_to)
                    extracted_files.append(extract_to / member.filename)
        elif suffix == ".7z" and py7zr is not None:
            with py7zr.SevenZipFile(archive_path, mode="r") as archive:  # type: ignore[union-attr]
                targets = [name for name in archive.getnames() if is_safe_member(str(name))]
                if targets:
                    archive.extract(path=extract_to, targets=targets)
                    for root, _, files in os.walk(extract_to):
                        for file_name in files:
                            extracted_files.append(Path(root) / file_name)
        elif suffix == ".tar":
            with tarfile.open(archive_path, "r:*") as archive:
                for member in archive.getmembers():
                    if not member.isfile() or not is_safe_member(member.name):
                        continue
                    archive.extract(member, extract_to)
                    extracted_files.append(extract_to / member.name)
    except Exception as exc:
        logger.warning("[Archive] Extraction failed: %s", exc)
        return []

    return extracted_files


def process_archive(
    archive_path: Path,
    source_url: str,
    date_str: str,
    meta_target_extensions: set[str] | None = None,
) -> bool:
    extracted_files = extract_archive(archive_path, archive_path.parent)
    if not extracted_files:
        return False
    success_count = 0
    for extracted in extracted_files:
        if generate_meta_json(extracted, source_url, date_str, meta_target_extensions):
            success_count += 1
    for meta_file in archive_path.parent.glob(f"{archive_path.stem}*.meta.json"):
        with contextlib.suppress(Exception):
            os.remove(meta_file)
    return success_count > 0
