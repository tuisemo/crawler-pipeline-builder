"""Pagination prompt assembly and deterministic recovery helpers."""

from __future__ import annotations

import re
from typing import Any


PAGINATION_ANALYSIS_SYSTEM_RULES = """## Selection Goal
Identify the single actionable control that advances to the next page or loads more content.

## Pagination Analysis Rules

1. Determine the pagination strategy:
   - 'click_next': standard Next button/link.
   - 'infinite_scroll': no button, triggers on scroll.
   - 'load_more': explicit button to append items.
   - 'none': no pagination found.

2. **Selector Precision (CRITICAL — progressively-converging / 逐级收敛)**:
   - The `next_button_selector` MUST be globally unambiguous and STABLE across different pages.
   - **STABILITY RULE**: Avoid using selectors that contain current page numbers, specific IDs, or href/src values that change when navigating (e.g., avoid `a[href*="p=2"]`, `li:nth-child(5)`, or `#page-link-24`).
   - Start from the closest stable ancestor of the next-page control (e.g. `nav.pagination`, `div.pager`, `ul.page-list`), then walk DOWN to the exact control element.
   - **ATTR-BASED PREFERENCE**: If no unique class exists, prefer stable semantic attributes (`rel`, `aria-label`, `data-*`) over positional selectors.
   - Good examples:
       `nav.pagination > a.next`
       `div.kq-pager > a[rel="next"]`
       `ul.page-list > li.next > a`
       `.news-pager a[aria-label*="next" i]`
       `.pagination a[aria-label*="next" i]`
   - Bad examples (STABILITY ISSUES):
       `a[href*="p=2"]` (Will only work for the second page)
       `.pager > a:nth-child(3)` (Index might change)
       `a.next` (Too broad, might match elsewhere)
       `div.kq-pager > a` (Matches page-number buttons and next button together)
   - If the element has a `rel="next"` attribute, `aria-label` containing "next", or its text is exactly "下一页"/"next", use those attributes for a specific selector.
   - For `page_number_selectors`, also use ancestor-scoped paths: `nav.pagination > a.page-num`.

3. Only populate 'page_number_selectors' with numbered page button selectors (not the next control).
4. If evidence is weak, return 'none' with an empty selector and explain in 'reason'.
5. If a PAGINATION_CONTROL_SUMMARY is provided, read the `class`, `parent_tag`, and `parent_class` fields to build the ancestor-scoped path.
6. Account for Chinese text: 下一页 (next), 加载更多 (load more), 上一页 (previous).
7. All selectors in output must be standard CSS selectors (no Playwright text locators, no XPath).
"""


_PAGINATION_SUMMARY_RE = re.compile(
    r"<!--\s*PAGINATION_CONTROL_SUMMARY\s*-->\s*([\s\S]*?)(?:<!--\s*[A-Z_]+\s*-->|$)",
    re.IGNORECASE,
)
_PAGINATION_SUMMARY_HEADING_RE = re.compile(
    r"###\s*Pagination Control Summary\s*([\s\S]*?)(?:\n## |\n### |\Z)",
    re.IGNORECASE,
)
_NEXT_TEXT_RE = re.compile(r"^(下一页|下页|next(?:\s+page)?(?:\s*[›»→>]+)?|>|›|»|加载更多|load more|more)$", re.IGNORECASE)
_LOW_SIGNAL_REASON_RE = re.compile(
    r"(no raw model output|using default|using defaults|empty values|insufficient context|unable to determine|not enough information|no pagination found)",
    re.IGNORECASE,
)
_PARTIAL_JSON_STRING_FIELD_RE = {
    "pagination_strategy": re.compile(r'"pagination_strategy"\s*:\s*"((?:\\.|[^"\\])*)'),
    "next_button_selector": re.compile(r'"next_button_selector"\s*:\s*"((?:\\.|[^"\\])*)'),
    "item_selector": re.compile(r'"item_selector"\s*:\s*"((?:\\.|[^"\\])*)'),
    "reason": re.compile(r'"reason"\s*:\s*"((?:\\.|[^"\\])*)'),
}
_PARTIAL_JSON_CONFIDENCE_RE = re.compile(r'"confidence"\s*:\s*(-?\d+(?:\.\d+)?)')
_PARTIAL_QUOTED_STRING_RE = re.compile(r'"((?:\\.|[^"\\])*)"')
_PARTIAL_PAGE_SELECTOR_START_RE = re.compile(r'"page_number_selectors"\s*:\s*\[', re.DOTALL)


def _decode_partial_json_string(value: str) -> str:
    try:
        decoded = bytes(value, "utf-8").decode("unicode_escape")
    except Exception:
        decoded = value
    return decoded.replace("\\'", "'")


def _extract_html_section(section_name: str, html_fragment: str) -> str:
    pattern = re.compile(
        rf"<!--\s*{re.escape(section_name)}\s*-->\s*([\s\S]*?)(?:<!--\s*[A-Z_]+\s*-->|$)",
        re.IGNORECASE,
    )
    match = pattern.search(html_fragment or "")
    return match.group(1).strip() if match else ""


def build_pagination_analysis_user_prompt(html_fragment: str) -> str:
    item_samples = _extract_html_section("ITEM_SAMPLES", html_fragment)
    pagination_html = _extract_html_section("PAGINATION", html_fragment)
    control_summary = _extract_html_section("PAGINATION_CONTROL_SUMMARY", html_fragment)

    evidence_sections = ["## Evidence Package"]

    if item_samples:
        evidence_sections.extend([
            "### Item Samples",
            item_samples,
            "",
        ])
    if pagination_html:
        evidence_sections.extend([
            "### Pagination HTML Candidate",
            pagination_html,
            "",
        ])
    if control_summary:
        evidence_sections.extend([
            "### Pagination Control Summary",
            control_summary,
            "",
        ])
    if not any((item_samples, pagination_html, control_summary)):
        evidence_sections.extend([
            "### Raw HTML Fragment",
            html_fragment,
            "",
        ])

    return "\n".join(evidence_sections).strip()


def has_pagination_evidence(user_prompt: str) -> bool:
    lowered = (user_prompt or "").lower()
    return (
        "pagination_control_summary" in lowered
        or "<!-- pagination -->" in lowered
        or "下一页" in user_prompt
        or "load more" in lowered
        or "kq-pager" in lowered
        or "pagination" in lowered
    )


def is_semantically_empty_pagination_result(task_name: str, normalized: dict[str, Any]) -> bool:
    if task_name != "analyze_pagination":
        return False
    page_number_selectors = normalized.get("page_number_selectors")
    reason = str(normalized.get("reason") or "").strip()
    confidence = normalized.get("confidence")
    confidence_value = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    return (
        normalized.get("pagination_strategy") == "none"
        and not str(normalized.get("next_button_selector") or "").strip()
        and (not isinstance(page_number_selectors, list) or len(page_number_selectors) == 0)
        and not str(normalized.get("item_selector") or "").strip()
        and confidence_value <= 0.1
        and (not reason or _LOW_SIGNAL_REASON_RE.search(reason) is not None)
    )


def _parse_pagination_summary_lines(user_prompt: str) -> list[dict[str, str]]:
    summary_text = ""
    match = _PAGINATION_SUMMARY_RE.search(user_prompt or "")
    if match:
        summary_text = match.group(1)
    else:
        heading_match = _PAGINATION_SUMMARY_HEADING_RE.search(user_prompt or "")
        if heading_match:
            summary_text = heading_match.group(1)
    if not summary_text:
        return []

    lines: list[dict[str, str]] = []
    for raw_line in summary_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        data: dict[str, str] = {}
        for part in [segment.strip() for segment in line.split("|")]:
            if not part or part.startswith("["):
                continue
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            data[key.strip()] = value.strip()
        if data:
            lines.append(data)
    return lines


def _stable_class_tokens(class_name: str) -> list[str]:
    tokens = []
    for token in re.split(r"\s+", class_name.strip()):
        cleaned = token.strip()
        if not cleaned or any(ch.isdigit() for ch in cleaned) or len(cleaned) > 40:
            continue
        if re.match(r"^[a-zA-Z_-][a-zA-Z0-9_-]*$", cleaned):
            tokens.append(cleaned)
    return tokens[:2]


def _build_selector_from_control_hint(control: dict[str, str]) -> str:
    tag = control.get("tag", "")
    if tag == "<unknown>":
        tag = ""
    rel = control.get("rel", "")
    if rel.lower() == "next":
        return f'{tag or "a"}[rel="next"]'

    class_tokens = _stable_class_tokens(control.get("class", ""))
    if class_tokens and any(re.search(r"(next|more|load)", token, re.IGNORECASE) for token in class_tokens):
        prefix = tag or ""
        return f'{prefix}.{".".join(class_tokens)}'

    parent_tag = control.get("parent_tag", "")
    parent_class_tokens = _stable_class_tokens(control.get("parent_class", ""))
    if parent_class_tokens and any(re.search(r"(next|more|load|pager|pagination)", token, re.IGNORECASE) for token in parent_class_tokens):
        parent_prefix = parent_tag or ""
        child_tag = tag or "a"
        return f'{parent_prefix}.{".".join(parent_class_tokens)} > {child_tag}'.lstrip()

    aria_label = control.get("aria_label", "")
    if aria_label and _NEXT_TEXT_RE.search(aria_label):
        return f'{tag or ""}[aria-label="{aria_label}"]'.lstrip()

    text = control.get("text", "")
    if class_tokens and _NEXT_TEXT_RE.search(text):
        prefix = tag or ""
        return f'{prefix}.{".".join(class_tokens)}'

    return ""


def recover_pagination_from_summary(user_prompt: str) -> dict[str, Any] | None:
    controls = _parse_pagination_summary_lines(user_prompt)
    if not controls:
        return None

    next_control = next((control for control in controls if control.get("role_hint") == "next_candidate"), None)
    if next_control is None:
        next_control = next((control for control in controls if _NEXT_TEXT_RE.search(control.get("text", ""))), None)
    if next_control is None:
        return None

    selector = _build_selector_from_control_hint(next_control)
    page_number_selectors: list[str] = []
    for control in controls:
        if control.get("role_hint") not in {"page_number", "current_page"}:
            continue
        class_tokens = _stable_class_tokens(control.get("class", ""))
        tag = control.get("tag", "")
        if class_tokens:
            page_number_selectors.append(f'{tag or ""}.{".".join(class_tokens)}'.lstrip())

    page_number_selectors = [selector_text for selector_text in dict.fromkeys(page_number_selectors) if selector_text and selector_text != selector]
    if not selector and not page_number_selectors:
        return None

    return {
        "pagination_strategy": "load_more" if re.search(r"(加载更多|load more|more)", next_control.get("text", ""), re.IGNORECASE) else "click_next",
        "next_button_selector": selector,
        "page_number_selectors": page_number_selectors,
        "item_selector": "",
        "confidence": 0.56 if selector else 0.42,
        "reason": "Recovered from pagination control summary because the model returned a semantically empty analysis.",
    }


def recover_partial_pagination_json(raw_output: str) -> dict[str, Any] | None:
    if not raw_output:
        return None

    recovered: dict[str, Any] = {
        "pagination_strategy": "none",
        "next_button_selector": "",
        "page_number_selectors": [],
        "item_selector": "",
        "confidence": None,
        "reason": "Recovered from truncated JSON output.",
    }
    found_signal = False

    for field_name, pattern in _PARTIAL_JSON_STRING_FIELD_RE.items():
        match = pattern.search(raw_output)
        if not match:
            continue
        raw_val = match.group(1)
        value = _decode_partial_json_string(raw_val)
        recovered[field_name] = value
        if field_name != "reason" and value:
            found_signal = True

    confidence_match = _PARTIAL_JSON_CONFIDENCE_RE.search(raw_output)
    if confidence_match:
        try:
            recovered["confidence"] = float(confidence_match.group(1))
            found_signal = True
        except ValueError:
            pass

    page_match = _PARTIAL_PAGE_SELECTOR_START_RE.search(raw_output)
    if page_match:
        raw_array_tail = raw_output[page_match.end():]
        page_values = [_decode_partial_json_string(match.group(1)) for match in _PARTIAL_QUOTED_STRING_RE.finditer(raw_array_tail)]
        if page_values:
            recovered["page_number_selectors"] = page_values
            found_signal = True

    if not found_signal:
        return None

    return recovered
