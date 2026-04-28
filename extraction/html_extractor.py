"""HTML fragment extraction for crawler-workflow.

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
    PAGINATION_SELECTOR_CANDIDATES = (
        '.pagination',
        '.pager',
        '.kq-pager',
        '[class*="pagination"]',
        '[class*="pager"]',
        '[class*="kq-pager"]',
        '[id*="pagination"]',
        '[id*="pager"]',
        'nav[aria-label*="page" i]',
        'nav',
    )
    PAGINATION_TEXT_RE = re.compile(r'(下一页|下页|上一页|首页|尾页|末页|next|prev|previous|load more|more|加载更多)', re.IGNORECASE)
    NEXT_CONTROL_RE = re.compile(r'^(?:下一页|下页|next(?:\s+page)?(?:\s*[›»→>]+)?|load more|more)\s*$', re.IGNORECASE)
    PREVIOUS_CONTROL_RE = re.compile(r'^(?:上一页|prev|previous|<|‹|«)\s*$', re.IGNORECASE)
    PAGE_NUMBER_RE = re.compile(r'^\d{1,3}$')
    PAGE_HREF_RE = re.compile(r'(page=|p=|index_|next)', re.IGNORECASE)

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

            total_items = len(items)
            full_html = self._collect_item_html(items, max_items=max_items)
            return self._finalize_result(full_html, total_items)

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

            total_items = len(items)
            # Get parent container of first item
            first_item = items[0]
            try:
                parent = first_item.evaluate('el => el.parentElement.outerHTML')
            except Exception:
                parent = first_item.inner_html()

            return self._finalize_result(parent, total_items)

        except Exception as e:
            return HtmlExtractionResult(html=f'<!-- Error: {e} -->', item_count=0)

    def extract_pagination_context(self, page, item_selector: str, max_items: int = 3) -> HtmlExtractionResult:
        """Extract item samples plus the most likely pagination container."""
        try:
            items = page.query_selector_all(item_selector)
            if not items:
                return HtmlExtractionResult(html='', item_count=0)

            total_items = len(items)
            sections = []

            item_html = self._collect_item_html(items, max_items=max_items, use_outer_html=True)
            if item_html:
                sections.append(f'<!-- ITEM_SAMPLES -->\n{item_html}')

            pagination_html, pagination_summary = self._find_local_pagination_bundle(items[0]) if items else ("", "")
            pagination_node = None
            if not pagination_html:
                pagination_html, pagination_node = self._find_pagination_html(page)
            if pagination_html:
                sections.append(f'<!-- PAGINATION -->\n{pagination_html}')
            if pagination_summary:
                sections.append(f'<!-- PAGINATION_CONTROL_SUMMARY -->\n{pagination_summary}')
            elif pagination_node is not None:
                pagination_summary = self._summarize_pagination_controls(pagination_node)
                if pagination_summary:
                    sections.append(f'<!-- PAGINATION_CONTROL_SUMMARY -->\n{pagination_summary}')

            full_html = '\n'.join(section for section in sections if section).strip()
            return self._finalize_result(full_html, total_items)
        except Exception as e:
            return HtmlExtractionResult(html=f'<!-- Error: {e} -->', item_count=0)

    def _collect_item_html(self, items, max_items: int, use_outer_html: bool = False) -> str:
        html_parts = []
        for item in items[:max_items]:
            try:
                if use_outer_html:
                    html = item.evaluate('el => el.outerHTML')
                else:
                    html = item.inner_html()
                html_parts.append(self._clean_html(html))
            except Exception:
                continue
        return '\n'.join(html_parts)

    def _finalize_result(self, html: str, item_count: int) -> HtmlExtractionResult:
        original_size = len(html.encode('utf-8'))
        truncated = False

        if original_size > self.max_size:
            truncated = True
            html = html[:self.max_size] + '\n<!-- TRUNCATED -->'
            truncated_size = len(html.encode('utf-8'))
        else:
            truncated_size = original_size

        return HtmlExtractionResult(
            html=html,
            truncated=truncated,
            original_size=original_size,
            truncated_size=truncated_size,
            item_count=item_count,
        )

    def _find_local_pagination_bundle(self, item) -> tuple[str, str]:
        try:
            result = item.evaluate(
                """(el, selectors) => {
                    const TEXT_RE = /(下一页|下页|上一页|首页|尾页|末页|next|prev|previous|load more|more|加载更多)/i;
                    const NEXT_RE = /^(?:下一页|下页|next(?:\\s+page)?(?:\\s*[›»→>]+)?|load more|more)\\s*$/i;
                    const PREV_RE = /^(?:上一页|prev|previous|<|‹|«)\\s*$/i;
                    const PAGE_NUMBER_RE = /^\\d{1,3}$/;

                    function cleanText(node) {
                        return (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
                    }

                    function summarize(node) {
                        const controls = [];
                        const rawControls = node.matches('a, button, [role=\"button\"], span')
                            ? [node, ...Array.from(node.querySelectorAll('a, button, [role=\"button\"], span')).filter(child => child !== node)]
                            : Array.from(node.querySelectorAll('a, button, [role=\"button\"], span'));
                        rawControls.slice(0, 20).forEach((control, index) => {
                            const text = cleanText(control);
                            const role = control.getAttribute('aria-current')
                                ? 'current_page'
                                : NEXT_RE.test(text)
                                    ? 'next_candidate'
                                    : PREV_RE.test(text)
                                        ? 'previous_candidate'
                                        : PAGE_NUMBER_RE.test(text)
                                            ? 'page_number'
                                            : 'nav_control';
                            const parent = control.parentElement;
                            const parts = [
                                `[${index + 1}]`,
                                `tag=${(control.tagName || '').toLowerCase() || '<unknown>'}`,
                                `text=${text || '<empty>'}`,
                                `role_hint=${role}`,
                            ];
                            const attrs = [
                                ['href', control.getAttribute('href') || ''],
                                ['rel', control.getAttribute('rel') || ''],
                                ['aria_label', control.getAttribute('aria-label') || ''],
                                ['aria_current', control.getAttribute('aria-current') || ''],
                                ['class', control.getAttribute('class') || ''],
                                ['parent_tag', parent ? (parent.tagName || '').toLowerCase() : ''],
                                ['parent_class', parent ? (parent.getAttribute('class') || '') : ''],
                            ];
                            attrs.forEach(([key, value]) => {
                                if (value) parts.push(`${key}=${value}`);
                            });
                            controls.push(parts.join(' | '));
                        });
                        return controls.join('\\n');
                    }

                    function scoreNode(node) {
                        const text = cleanText(node);
                        const attrs = `${node.id || ''} ${node.className || ''}`.toLowerCase();
                        const controls = Array.from(node.querySelectorAll('a, button, [role=\"button\"], span')).slice(0, 30);
                        let score = 0;
                        if (TEXT_RE.test(text)) score += 8;
                        if (/(page|pager|pagination|more)/.test(attrs)) score += 6;
                        controls.forEach(control => {
                            const ctlText = cleanText(control);
                            if (PAGE_NUMBER_RE.test(ctlText)) score += 2;
                            if (NEXT_RE.test(ctlText)) score += 6;
                            const href = (control.getAttribute('href') || '').toLowerCase();
                            if (/(page=|p=|page\\/|list)/.test(href)) score += 2;
                        });
                        return score;
                    }

                    const seen = new Set();
                    const candidates = [];
                    let current = el.parentElement;
                    let depth = 0;
                    while (current && depth < 6) {
                        const roots = [current];
                        let sibling = current.nextElementSibling;
                        let siblingDepth = 0;
                        while (sibling && siblingDepth < 4) {
                            roots.push(sibling);
                            sibling = sibling.nextElementSibling;
                            siblingDepth += 1;
                        }
                        for (const root of roots) {
                            for (const selector of selectors) {
                                root.querySelectorAll(selector).forEach(node => {
                                    if (seen.has(node)) return;
                                    seen.add(node);
                                    const score = scoreNode(node);
                                    if (score >= 8) {
                                        candidates.push({ node, score });
                                    }
                                });
                            }
                        }
                        current = current.parentElement;
                        depth += 1;
                    }

                    candidates.sort((a, b) => b.score - a.score);
                    const best = candidates[0];
                    if (!best) {
                        return { html: '', summary: '' };
                    }
                    return {
                        html: best.node.outerHTML || '',
                        summary: summarize(best.node),
                    };
                }""",
                list(self.PAGINATION_SELECTOR_CANDIDATES),
            )
        except Exception:
            return '', ''

        if not isinstance(result, dict):
            return '', ''
        return self._clean_html(result.get('html') or ''), (result.get('summary') or '').strip()

    def _find_pagination_html(self, page) -> tuple[str, object | None]:
        best_html = ''
        best_score = 0
        best_node = None
        seen_keys: set[str] = set()

        for selector in self.PAGINATION_SELECTOR_CANDIDATES:
            try:
                candidates = page.query_selector_all(selector)
            except Exception:
                continue

            for node in candidates:
                try:
                    raw_html = node.evaluate('el => el.outerHTML')
                    if not raw_html:
                        continue

                    dedupe_key = raw_html[:400]
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)

                    text = node.inner_text().strip()
                    controls = self._collect_control_nodes(node)
                    if len(controls) < 2 and not any(self._is_next_like_control(control) for control in controls):
                        continue

                    score = 0
                    if self.PAGINATION_TEXT_RE.search(text):
                        score += 8
                    class_id = f"{node.get_attribute('id') or ''} {node.get_attribute('class') or ''}"
                    if re.search(r'(page|pagination|pager|fy|fenye)', class_id, re.IGNORECASE):
                        score += 4

                    for control in controls[:20]:
                        try:
                            control_text = control.inner_text().strip()
                        except Exception:
                            control_text = ''
                        if self.PAGE_NUMBER_RE.match(control_text):
                            score += 2
                        href = control.get_attribute('href') or ''
                        if self.PAGE_HREF_RE.search(href):
                            score += 2

                    if score > best_score:
                        best_score = score
                        best_html = self._clean_html(raw_html)
                        best_node = node
                except Exception:
                    continue

        if best_html:
            return best_html, best_node

        prioritized_controls = (
            'a.morelink',
            'a[rel="next"]',
            'a[aria-label*="next" i]',
            'button[aria-label*="next" i]',
            '.next a',
            'li.next a',
            '.pager .next a',
            '.pagination .next a',
        )

        for selector in prioritized_controls:
            try:
                next_links = page.query_selector_all(selector)
            except Exception:
                continue
            if next_links:
                node = next_links[0]
                return self._clean_html(self._build_pagination_context_html(node)), node

        try:
            next_links = page.query_selector_all('a, button, [role="button"]')
        except Exception:
            return '', None

        for node in next_links:
            try:
                text = node.inner_text().strip()
                href = node.get_attribute('href') or ''
                if not self.NEXT_CONTROL_RE.match(text):
                    continue
                if not (self.PAGE_HREF_RE.search(href) or self._has_paginationish_ancestor(node)):
                    continue
                return self._clean_html(self._build_pagination_context_html(node)), node
            except Exception:
                continue
        return '', None

    def _summarize_pagination_controls(self, node) -> str:
        controls = []
        try:
            raw_controls = self._collect_control_nodes(node)
        except Exception:
            return ''

        for index, control in enumerate(raw_controls[:20], start=1):
            try:
                text = control.inner_text().strip()
            except Exception:
                text = ''
            href = ''
            aria_label = ''
            rel = ''
            class_name = ''
            aria_current = ''
            disabled = ''
            try:
                href = control.get_attribute('href') or ''
            except Exception:
                pass
            tag_name = ''
            try:
                tag_name = control.evaluate('el => (el.tagName || "").toLowerCase()')
            except Exception:
                pass
            try:
                aria_label = control.get_attribute('aria-label') or ''
            except Exception:
                pass
            try:
                rel = control.get_attribute('rel') or ''
            except Exception:
                pass
            try:
                class_name = control.get_attribute('class') or ''
            except Exception:
                pass
            try:
                aria_current = control.get_attribute('aria-current') or ''
            except Exception:
                pass
            try:
                disabled = control.get_attribute('disabled') or ''
            except Exception:
                pass
            parent_tag = ''
            parent_class = ''
            try:
                parent_tag = control.evaluate('el => (el.parentElement && el.parentElement.tagName || "").toLowerCase()')
            except Exception:
                pass
            try:
                parent_class = control.evaluate('el => (el.parentElement && el.parentElement.getAttribute("class")) || ""')
            except Exception:
                pass

            role = "page_number" if self.PAGE_NUMBER_RE.match(text) else "nav_control"
            if self.NEXT_CONTROL_RE.match(text):
                role = "next_candidate"
            elif self.PREVIOUS_CONTROL_RE.match(text):
                role = "previous_candidate"
            elif aria_current:
                role = "current_page"

            summary_parts = [
                f"[{index}]",
                f"tag={tag_name or '<unknown>'}",
                f"text={text or '<empty>'}",
                f"role_hint={role}",
            ]
            if href:
                summary_parts.append(f"href={href}")
            if rel:
                summary_parts.append(f"rel={rel}")
            if aria_label:
                summary_parts.append(f"aria_label={aria_label}")
            if aria_current:
                summary_parts.append(f"aria_current={aria_current}")
            if disabled:
                summary_parts.append(f"disabled={disabled}")
            if class_name:
                summary_parts.append(f"class={class_name}")
            if parent_tag:
                summary_parts.append(f"parent_tag={parent_tag}")
            if parent_class:
                summary_parts.append(f"parent_class={parent_class}")
            controls.append(" | ".join(summary_parts))

        return "\n".join(controls).strip()

    def _collect_control_nodes(self, node) -> list[object]:
        controls: list[object] = []
        try:
            tag_name = node.evaluate('el => (el.tagName || "").toLowerCase()')
        except Exception:
            tag_name = ''
        if tag_name in {"a", "button", "span"}:
            controls.append(node)
        try:
            descendants = node.query_selector_all('a, button, [role="button"], span')
        except Exception:
            descendants = []
        controls.extend(descendants)
        return controls

    def _is_next_like_control(self, control) -> bool:
        try:
            text = control.inner_text().strip()
        except Exception:
            text = ''
        return bool(self.NEXT_CONTROL_RE.match(text))

    def _has_paginationish_ancestor(self, node) -> bool:
        try:
            return bool(node.evaluate(
                """el => {
                    let current = el.parentElement;
                    while (current) {
                        const attrs = `${current.id || ''} ${current.className || ''}`.toLowerCase();
                        if (/(page|pager|pagination|next|more)/.test(attrs)) {
                            return true;
                        }
                        current = current.parentElement;
                    }
                    return false;
                }"""
            ))
        except Exception:
            return False

    def _build_pagination_context_html(self, node) -> str:
        try:
            return node.evaluate(
                """el => {
                    let current = el;
                    while (current) {
                        const attrs = `${current.id || ''} ${current.className || ''}`.toLowerCase();
                        if (/(page|pager|pagination)/.test(attrs)) {
                            return current.outerHTML;
                        }
                        current = current.parentElement;
                    }
                    return (el.parentElement && el.parentElement.outerHTML) || el.outerHTML;
                }"""
            )
        except Exception:
            try:
                return node.evaluate('el => (el.parentElement && el.parentElement.outerHTML) || el.outerHTML')
            except Exception:
                return ''

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
