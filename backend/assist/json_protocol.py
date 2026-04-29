"""JSON protocol helpers for assist LLM tasks."""

from __future__ import annotations

import json
import re
from typing import Any


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


ASSIST_JSON_SYSTEM_PROMPT = """You are a web scraping analysis API.

Return exactly one valid JSON object and nothing else.

## Objective
Produce the most accurate structured JSON answer that is directly machine-consumable.

## Hard requirements
- Do not include markdown code fences.
- Do not include any prose before or after the JSON object.
- Do not include comments, ellipses, placeholders, or trailing commas.
- Use double quotes for every JSON key and every string value.
- If you are uncertain, still return the best possible JSON object with empty strings, empty arrays, nulls, or low confidence values instead of natural language.
- Every selector must remain a standard CSS selector.

## Failure policy
- Never emit partially structured text.
- Never return a list or scalar; always return one JSON object.
- When evidence is weak, prefer explicit uncertainty (empty value + low confidence) over fabricated precision.
"""


JSON_REPAIR_SYSTEM_PROMPT = """You are a JSON repair utility for a web scraping analysis API.

Return exactly one valid JSON object and nothing else.

## Rules
- Preserve the original meaning as much as possible.
- Remove any prose, markdown fences, comments, and trailing commas.
- If a key required by the response contract is missing, add it with an empty string, empty array, null, or a low-confidence default.
- Do not invent new explanatory prose.
- Keep selector syntax compatible with standard CSS selectors.
"""


def _extract_balanced_json_object(raw: str) -> str | None:
    start = raw.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(raw)):
        char = raw[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return raw[start:index + 1]
    return None


def _extract_json_payload(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None

    stripped = raw.strip()
    for candidate in (stripped, *_JSON_BLOCK_RE.findall(stripped)):
        try:
            parsed = json.loads(candidate.strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    object_match = _JSON_OBJECT_RE.search(stripped)
    if object_match:
        try:
            parsed = json.loads(object_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    balanced_object = _extract_balanced_json_object(stripped)
    if balanced_object:
        try:
            parsed = json.loads(balanced_object)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None

    return None


def _build_json_task_system_prompt(response_contract: str, system_suffix: str = "") -> str:
    base = f"{ASSIST_JSON_SYSTEM_PROMPT}\n\n{response_contract}".strip()
    if system_suffix:
        return f"{base}\n\n{system_suffix}".strip()
    return base


def _build_json_repair_prompt(response_contract: str, raw_output: str) -> str:
    return (
        "Repair the following model output into one valid JSON object that matches the response contract.\n\n"
        "## Response Contract\n"
        f"{response_contract}\n\n"
        "## Raw Model Output\n"
        f"{raw_output}"
    ).strip()
