"""HTML fragment extraction for sea-data.

Extracts relevant HTML structure from pages for LLM context.
"""

import re
from dataclasses import dataclass


@dataclass
class HtmlExtractionResult:
    """Result of HTML fragment extraction."""
    html: str
    truncated: bool = False
    original_size: int = 0
    truncated_size: int = 0
    item_count: int = 0


# Patterns that might contain sensitive/personal data - to be redacted
SENSITIVE_PATTERNS = [
    (re.compile(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'), '[SSN]'),  # SSN-like
    (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '[CARD]'),  # Credit card-like
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL]'),  # Email
    (re.compile(r'\b1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}\b'), '[PHONE]'),  # Chinese phone
    (re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'), '[PHONE]'),  # US phone
]


class HtmlExtractor:
    """Extracts HTML fragments from pages for LLM context."""

    MAX_FRAGMENT_SIZE = 15 * 1024  # 15KB limit

    def __init__(self, max_size: int | None = None):
        """Initialize extractor.

        Args:
            max_size: Maximum fragment size in bytes (default 15KB)
        """
        self.max_size = max_size or self.MAX_FRAGMENT_SIZE

    def extract_item_container(self, page, item_selector: str, max_items: int = 3) -> HtmlExtractionResult:
        """Extract HTML from item containers.

        Args:
            page: Playwright page object
            item_selector: CSS selector for item containers
            max_items: Maximum number of items to extract

        Returns:
            HtmlExtractionResult with extracted HTML
        """
        try:
            items = page.query_selector_all(item_selector)
            if not items:
                return HtmlExtractionResult(html='', item_count=0)

            html_parts = []
            for item in items[:max_items]:
                try:
                    html = item.inner_html()
                    html_parts.append(self._clean_html(html))
                except Exception:
                    continue

            full_html = '\n'.join(html_parts)
            original_size = len(full_html.encode('utf-8'))

            truncated = False
            if original_size > self.max_size:
                # Truncate with marker
                truncated = True
                full_html = full_html[:self.max_size] + '\n<!-- TRUNCATED -->'
                truncated_size = len(full_html.encode('utf-8'))
            else:
                truncated_size = original_size

            return HtmlExtractionResult(
                html=full_html,
                truncated=truncated,
                original_size=original_size,
                truncated_size=truncated_size,
                item_count=len(html_parts)
            )

        except Exception as e:
            return HtmlExtractionResult(html=f'<!-- Error: {e} -->', item_count=0)

    def extract_wrapper_context(self, page, item_selector: str, max_items: int = 3) -> HtmlExtractionResult:
        """Extract parent/wrapper HTML with some context around items.

        This provides more structural context for the LLM.

        Args:
            page: Playwright page object
            item_selector: CSS selector for item containers
            max_items: Maximum number of items to show

        Returns:
            HtmlExtractionResult with wrapper HTML
        """
        try:
            items = page.query_selector_all(item_selector)
            if not items:
                return HtmlExtractionResult(html='', item_count=0)

            # Get parent container of first item
            first_item = items[0]
            try:
                parent = first_item.evaluate('el => el.parentElement.outerHTML')
            except Exception:
                parent = first_item.inner_html()

            original_size = len(parent.encode('utf-8'))
            truncated = False

            if original_size > self.max_size:
                truncated = True
                parent = parent[:self.max_size] + '\n<!-- TRUNCATED -->'
                truncated_size = len(parent.encode('utf-8'))
            else:
                truncated_size = original_size

            return HtmlExtractionResult(
                html=parent,
                truncated=truncated,
                original_size=original_size,
                truncated_size=truncated_size,
                item_count=len(items[:max_items])
            )

        except Exception as e:
            return HtmlExtractionResult(html=f'<!-- Error: {e} -->', item_count=0)

    def _clean_html(self, html: str) -> str:
        """Clean HTML for LLM context.

        - Redact potential sensitive data
        - Mark dynamic placeholders
        - Remove unnecessary attributes
        """
        # Redact sensitive patterns
        for pattern, replacement in SENSITIVE_PATTERNS:
            html = pattern.sub(replacement, html)

        # Mark dynamic attributes as placeholders
        html = re.sub(r'src="[^"]*"', 'src="[IMG_SRC]"', html)
        html = re.sub(r'href="[^"]*"', 'href="[HREF]"', html)
        html = re.sub(r'data-src="[^"]*"', 'data-src="[DATA_SRC]"', html)

        # Remove common noise attributes
        noise_attrs = ['style', 'onclick', 'onload', 'onerror', 'data-analytics', 'data-tracking']
        for attr in noise_attrs:
            html = re.sub(rf'\s+{attr}="[^"]*"', '', html)

        # Normalize whitespace
        html = re.sub(r'\s+', ' ', html)
        html = re.sub(r'>\s+<', '><', html)

        return html.strip()

    def extract_for_prompt(self, page, item_selector: str, max_items: int = 3) -> str:
        """Convenience method to get cleaned HTML for prompt.

        Args:
            page: Playwright page object
            item_selector: CSS selector for items
            max_items: Max items to include

        Returns:
            Cleaned HTML string suitable for prompt context
        """
        result = self.extract_item_container(page, item_selector, max_items)
        return result.html
