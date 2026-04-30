"""Selector testing and validation for crawler-workflow."""

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin


SELECTOR_HIGHLIGHT_STYLE_ID = "crawler-workflow-selector-highlight-style"
SELECTOR_HIGHLIGHT_ATTR = "data-crawler-workflow-selector-highlight"
SELECTOR_HIGHLIGHT_CLEAR_FN = "__crawlerWorkflowClearSelectorHighlights"
SELECTOR_HIGHLIGHT_TIMER_KEY = "__crawlerWorkflowSelectorHighlightTimer"


@dataclass
class SelectorTestResult:
    """Result of testing a selector against a page."""
    match_count: int = 0
    sample_items: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass
class SampleItem:
    """A sample item from selector testing."""
    text: str
    html: str
    children: int
    has_image: bool
    has_link: bool


def _get_text_snippet(el, max_len: int = 80) -> str:
    """Extract text content, truncated."""
    text = ""
    try:
        if hasattr(el, "inner_text"):
            text = el.inner_text() or ""
        elif hasattr(el, "text_content"):
            text = el.text_content() or ""
    except Exception:
        text = ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + ('...' if len(text) > max_len else '')


def _normalize_extraction_type(extraction_type: str) -> str:
    """Normalize aliases from UI/prompt into tester canonical forms."""
    normalized = (extraction_type or "").strip()
    if normalized == "all(text)":
        return "all_text"
    return normalized


def _normalize_query_selector(selector: str) -> str:
    normalized = (selector or "").strip()
    if not normalized:
        return ""
    lowered = normalized.lower()
    if lowered.startswith(("xpath=", "css=")):
        return normalized
    if normalized.startswith(("//", ".//", "(//", "(/")):
        return f"xpath={normalized}"
    return normalized


def _safe_query(page, selector: str) -> list:
    """Safely query page with selector, return empty list on error."""
    try:
        return page.query_selector_all(_normalize_query_selector(selector))
    except Exception:
        return []


class SelectorTester:
    """Tests CSS selectors against Playwright pages."""

    @staticmethod
    def clear_selector_highlight(page) -> None:
        try:
            page.evaluate(
                f"""() => {{
                    const attrName = {SELECTOR_HIGHLIGHT_ATTR!r};
                    const styleId = {SELECTOR_HIGHLIGHT_STYLE_ID!r};
                    const clearFnName = {SELECTOR_HIGHLIGHT_CLEAR_FN!r};
                    const timerKey = {SELECTOR_HIGHLIGHT_TIMER_KEY!r};
                    const existingTimer = window[timerKey];
                    if (existingTimer) {{
                        clearTimeout(existingTimer);
                        window[timerKey] = null;
                    }}
                    document.querySelectorAll(`[${{attrName}}]`).forEach((node) => {{
                        node.removeAttribute(attrName);
                    }});
                    const styleNode = document.getElementById(styleId);
                    if (styleNode) {{
                        styleNode.remove();
                    }}
                    if (typeof window[clearFnName] === "function") {{
                        delete window[clearFnName];
                    }}
                }}"""
            )
        except Exception:
            pass

    @staticmethod
    def highlight_selector(page, selector: str, clear_after_ms: int = 2200) -> int:
        elements = _safe_query(page, selector)
        if not elements:
            return 0

        SelectorTester.clear_selector_highlight(page)

        try:
            page.evaluate(
                f"""() => {{
                    const attrName = {SELECTOR_HIGHLIGHT_ATTR!r};
                    const styleId = {SELECTOR_HIGHLIGHT_STYLE_ID!r};
                    const clearFnName = {SELECTOR_HIGHLIGHT_CLEAR_FN!r};
                    const timerKey = {SELECTOR_HIGHLIGHT_TIMER_KEY!r};
                    const styleNode = document.createElement("style");
                    styleNode.id = styleId;
                    styleNode.textContent = `
                        [{SELECTOR_HIGHLIGHT_ATTR}] {{
                            outline: 3px solid #ef4444 !important;
                            outline-offset: 2px !important;
                            box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.18) !important;
                            background-color: rgba(251, 191, 36, 0.18) !important;
                            transition: outline-color 120ms ease, box-shadow 120ms ease, background-color 120ms ease !important;
                        }}
                    `;
                    document.head.appendChild(styleNode);
                    window[clearFnName] = () => {{
                        const existingTimer = window[timerKey];
                        if (existingTimer) {{
                            clearTimeout(existingTimer);
                            window[timerKey] = null;
                        }}
                        document.querySelectorAll(`[${{attrName}}]`).forEach((node) => {{
                            node.removeAttribute(attrName);
                        }});
                        const currentStyleNode = document.getElementById(styleId);
                        if (currentStyleNode) {{
                            currentStyleNode.remove();
                        }}
                    }};
                }}"""
            )

            for index, element in enumerate(elements):
                try:
                    element.evaluate(
                        f"""(node) => {{
                            node.setAttribute({SELECTOR_HIGHLIGHT_ATTR!r}, "true");
                            if ({index} === 0 && typeof node.scrollIntoView === "function") {{
                                node.scrollIntoView({{ block: "center", inline: "nearest", behavior: "instant" }});
                            }}
                        }}"""
                    )
                except Exception:
                    continue

            timeout_ms = clear_after_ms if isinstance(clear_after_ms, int) and clear_after_ms > 0 else 2200
            page.evaluate(
                f"""(timeoutMs) => {{
                    const clearFnName = {SELECTOR_HIGHLIGHT_CLEAR_FN!r};
                    const timerKey = {SELECTOR_HIGHLIGHT_TIMER_KEY!r};
                    const existingTimer = window[timerKey];
                    if (existingTimer) {{
                        clearTimeout(existingTimer);
                    }}
                    if (typeof window[clearFnName] === "function") {{
                        window[timerKey] = window.setTimeout(() => window[clearFnName](), timeoutMs);
                    }}
                }}""",
                timeout_ms,
            )
        except Exception:
            pass

        return len(elements)

    @staticmethod
    def test_selector(page, selector: str, max_samples: int = 5) -> SelectorTestResult:
        """Test a CSS selector and return match information.

        Args:
            page: Playwright page object
            selector: CSS selector to test
            max_samples: Maximum number of sample items to return

        Returns:
            SelectorTestResult with match count and sample data
        """
        try:
            elements = _safe_query(page, selector)
            if not elements:
                return SelectorTestResult(match_count=0)

            samples = []
            for el in elements[:max_samples]:
                try:
                    el_text = _get_text_snippet(el)
                    el_html = el.inner_html()[:200] if hasattr(el, 'inner_html') else ''
                    children = len(el.query_selector_all('*')) if el else 0
                    has_img = len(el.query_selector_all('img')) > 0 if el else False
                    has_link = len(el.query_selector_all('a[href]')) > 0 if el else False

                    samples.append({
                        'text': el_text,
                        'html': el_html,
                        'children': children,
                        'has_image': has_img,
                        'has_link': has_link
                    })
                except Exception:
                    continue

            return SelectorTestResult(
                match_count=len(elements),
                sample_items=samples
            )

        except Exception as e:
            return SelectorTestResult(error=str(e))

    @staticmethod
    def extract_fields_from_items(page, item_selector: str, fields: list[dict]) -> list[dict]:
        """Extract data from all items matching the item selector.

        Args:
            page: Playwright page object
            item_selector: CSS selector for item containers
            fields: List of field definitions [{name, selector, type}, ...]

        Returns:
            List of extracted data records
        """
        items = _safe_query(page, item_selector)
        if not items:
            return []

        results = []
        for idx, item in enumerate(items):
            record = {'_index': idx}
            for field_def in fields:
                name = field_def.get('name', '')
                selector = field_def.get('selector', '')
                ext_type = _normalize_extraction_type(field_def.get('type', 'text'))
                page_url = getattr(page, "url", "") or ""

                if not selector:
                    record[name] = None
                    continue

                try:
                    normalized_selector = _normalize_query_selector(selector)
                    # First check if item itself matches the selector (for leaf selectors like 'a', 'img')
                    # We use evaluate() to access the JS matches method, since Python ElementHandle
                    # may not expose matches as a direct attribute
                    sub_elements = []
                    if normalized_selector and not normalized_selector.lower().startswith("xpath="):
                        try:
                            # Try JS matches via evaluate
                            matched = item.evaluate(f'(el) => el.matches("{normalized_selector}")')
                            if matched:
                                sub_elements = [item]
                        except Exception:
                            pass

                    # If no match, try querying children within the item
                    if not sub_elements:
                        if normalized_selector.startswith('.') or normalized_selector.startswith('#') or not normalized_selector.startswith(('div', 'span', 'a', 'img', 'li', 'tr', 'p', 'h')):
                            sub_sel = normalized_selector
                        else:
                            sub_sel = normalized_selector

                        sub_elements = item.query_selector_all(sub_sel) if hasattr(item, 'query_selector_all') else []
                        if not sub_elements and sub_sel.startswith(":scope"):
                            fallback_sel = re.sub(r"^:scope\s*>\s*", "", sub_sel)
                            fallback_sel = re.sub(r"^:scope\s*", "", fallback_sel).strip()
                            if fallback_sel and hasattr(item, 'query_selector_all'):
                                sub_elements = item.query_selector_all(fallback_sel)
                    if not sub_elements:
                        record[name] = None
                        continue

                    sub_el = sub_elements[0]

                    if ext_type == 'text':
                        record[name] = sub_el.inner_text().strip() if hasattr(sub_el, 'inner_text') else None
                    elif ext_type.startswith('attr:'):
                        parts = ext_type.split(':')
                        attr_name = parts[1] if len(parts) >= 2 else ''
                        is_abs = 'abs' in parts[2:]
                        raw_value = sub_el.get_attribute(attr_name) if attr_name else None
                        record[name] = urljoin(page_url, raw_value) if (raw_value and is_abs and page_url) else raw_value
                    elif ext_type in ('html', 'inner'):
                        record[name] = sub_el.inner_html() if hasattr(sub_el, 'inner_html') else None
                    elif ext_type == 'all_text':
                        values = []
                        for e in sub_elements:
                            try:
                                text_value = e.inner_text().strip()
                                if text_value:
                                    values.append(text_value)
                            except Exception:
                                pass
                        record[name] = values
                    elif ext_type.startswith('all(@'):
                        attr_name = ext_type[5:-1]
                        values = []
                        for e in sub_elements:
                            try:
                                attr_value = e.get_attribute(attr_name)
                                if attr_value:
                                    values.append(attr_value)
                            except Exception:
                                pass
                        record[name] = values
                    else:
                        record[name] = None

                except Exception:
                    record[name] = None

            results.append(record)

        return results
