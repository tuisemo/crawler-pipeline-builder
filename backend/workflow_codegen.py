"""Deterministic workflow code generator (ExecutionPlan -> Python script)."""

from __future__ import annotations

import json
import textwrap
from typing import Any


def _json_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def generate_playwright_skeleton(plan: dict[str, Any]) -> str:
    """Generate a deterministic Playwright Python crawler skeleton."""
    entry_url = plan.get("entry_url", "")
    item_selector = plan.get("item_selector", "")
    field_specs = plan.get("field_specs", [])
    pagination = plan.get("pagination", {}) or {}
    limits = plan.get("limits", {}) or {}

    max_items = int(limits.get("max_items", 50))
    max_pages = int(limits.get("max_pages", 10))
    pagination_selector = str(pagination.get("selector", "") or "")
    pagination_strategy = str(pagination.get("strategy", "click_next") or "click_next")

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

import json
import re
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
OUTPUT_FILE = "crawler_output.json"


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

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        context.close()
        browser.close()
    return records


if __name__ == "__main__":
    output = run()
    print(f"Extracted {{len(output)}} records -> {{OUTPUT_FILE}}")
"""
    return textwrap.dedent(script).strip() + "\n"
