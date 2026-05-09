"""Shared helpers for assist modules."""

from __future__ import annotations

import re


def extract_html_section(section_name: str, html_fragment: str) -> str:
    """Extract a named HTML section delimited by comment markers."""
    pattern = re.compile(
        rf"<!--\s*{re.escape(section_name)}\s*-->\s*([\s\S]*?)(?:<!--\s*[A-Z_]+\s*-->|$)",
        re.IGNORECASE,
    )
    match = pattern.search(html_fragment or "")
    return match.group(1).strip() if match else ""


def stable_class_tokens(class_name: str) -> list[str]:
    """Extract stable (non-numeric, non-generic) CSS class tokens."""
    tokens: list[str] = []
    for token in re.split(r"\s+", class_name.strip()):
        cleaned = token.strip()
        if not cleaned or any(ch.isdigit() for ch in cleaned) or len(cleaned) > 40:
            continue
        if re.match(r"^[a-zA-Z_-][a-zA-Z0-9_-]*$", cleaned):
            tokens.append(cleaned)
    return tokens[:2]
