"""Task prompt templates for assist capabilities."""

from backend.prompts.shared.rules import (
    LOW_CONFIDENCE_FALLBACK_POLICY,
    PLAYWRIGHT_CSS_SELECTOR_COMPATIBILITY_RULES,
)


FIELD_INFERENCE_PROMPT_TEMPLATE = f"""Analyze the HTML fragment below and extract structured field selectors for a web scraper.

HTML:
{{html_fragment}}

## Objective
Produce selectors that are executable, stable, and minimally ambiguous on the current page evidence.

## Evidence Handling
Base your decision on the strongest structural evidence first:
1. Repeating DOM structures that clearly represent records
2. Stable semantic anchors such as IDs, data attributes, list containers, cards, articles, or headings
3. Field-specific cues from tag semantics, class names, and visible text
4. Generic tags only as a last resort

## Selector Precision Rules (CRITICAL)
You MUST produce **progressively-converging** (逐级收敛) selectors that are globally unambiguous on the page:

1. **item_selector** — a CSS selector that matches ONLY the repeating list items, not any other elements.
   - Prefer a scoped path: `<ancestor> > <tag>.<stable-class>` (e.g. `ul.news-list > li`, `div.results-grid > article`).
   - If the item has a unique class, verify it is not shared by navigation, sidebar, or footer elements.
   - Do NOT return a bare tag like `li` or `div` that matches hundreds of unrelated elements.

2. **field selectors** — relative to each list item element (i.e. evaluated inside the item, not the whole document).
   - Use `:scope > ...` or a short relative path when possible (e.g. `:scope > a > .title`, `.card-body > h3.title`).
   - If the class name could appear globally (e.g. `.title`, `.date`, `.name`), prefix it with the nearest stable ancestor: `div.card-body > span.date`.
   - Avoid bare generic selectors like `p`, `span`, `div` that match many things.

{PLAYWRIGHT_CSS_SELECTOR_COMPATIBILITY_RULES}

## Field Decision Rules
- Prefer the primary record link, not navigation links, author profile links, or unrelated utility actions.
- Prefer one high-confidence selector per field rather than multiple speculative alternatives.
- Avoid assigning different field names to the same selector unless the HTML clearly supports both meanings.
- If the page evidence only supports 2 strong fields, return 2 strong fields instead of padding to 6.

## Failure Policy
{LOW_CONFIDENCE_FALLBACK_POLICY}
- Do not fabricate fields that have no visual or structural support in the HTML.

## Field Coverage
For each repeating item, extract ALL meaningful fields present:
- `title` — main heading or article name (text)
- `link` — the primary anchor URL (attr:href)
- `publish_date` — publication or update date/time (text)
- `summary` — excerpt or description if present (text)
- `image` — thumbnail image if present (attr:src or attr:data-src)
- `source` — author, category, or source tag if present (text)
- Any other domain-specific fields visible in the HTML

Snake_case field names. Aim for 3–6 fields per item.

## Self-check
- Is `item_selector` specific to repeated records instead of page-wide layout elements?
- Are field selectors item-scoped and not global broad selectors?
- Would the selector still point at the intended field if evaluated inside one item element?
- Are all selectors standard CSS selectors?"""


SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE = f"""Optimize the CSS selector below to be globally unambiguous and resilient to minor DOM changes.

Initial selector: {{initial_selector}}

Sample HTML:
{{html_fragment}}

## Objective
Return a selector with better precision/stability tradeoff than the initial selector while keeping semantic intent unchanged.

## Decision Policy
- Preserve the target meaning and expected match cardinality.
- Improve selector quality only when the improvement is evidence-backed.
- If the current selector is already the best stable choice, keep it.

## Optimization Steps
1. **Diagnose ambiguity**: count how many elements on the page the current selector could match. If more than the expected item count, it is too broad.
2. **Converge progressively**: build a scoped path by walking UP the DOM tree to the nearest stable semantic ancestor (landmark element, unique ID, or stable class), then walk DOWN to the target.
   - Good: `section.news-container > ul > li.news-item`
   - Bad: `.news-item` (naked class, may appear elsewhere)
3. **Prefer stable attributes**: IDs (if truly unique), stable class names, `data-*` attributes, or semantic HTML tags.
4. **Trim redundancy**: remove intermediate nodes that don't add disambiguation value.
5. Do not over-tighten the selector into something fragile, position-dependent, or likely to match zero elements after a small DOM change.
6. The optimized selector MUST be a standard CSS selector compatible with `querySelector` / `querySelectorAll` and Playwright `locator()`.
7. Do NOT return Playwright-only locator expressions or helper syntax such as `get_by_role(...)`, `get_by_text(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`, or XPath selectors.

## Failure Policy
- If the initial selector is already the best stable option, return it unchanged with explicit reason.
- Never trade major stability loss for superficial brevity.
- Never change the selector to target a different semantic element.
- Never output non-CSS syntax."""


PAGINATION_ANALYSIS_PROMPT_TEMPLATE = """Given HTML content containing pagination elements, analyze the pagination pattern and extract highly robust selectors.

HTML:
{html_fragment}

## Objective
Identify the concrete, single control that advances pagination and return a durable selector policy.

## Evidence Priority
Use evidence in this order:
1. Explicit next/load-more semantics such as `rel="next"`, `aria-label`, button text, title, or stable next-specific classes
2. `PAGINATION_CONTROL_SUMMARY` if present
3. Pagination container structure and relative position
4. Generic heuristics only if the earlier evidence is missing

Task:
1. Identify the pagination container and the specific "Next Page" (下一页) or "Load More" (加载更多) element.
2. Determine the exact pagination strategy:
   - 'click_next': Standard pagination with a "Next" button/link.
   - 'infinite_scroll': No button, triggers on scroll.
   - 'load_more': Explicit button to append items.
   - 'none': No pagination found.
3. Provide a ROBUST CSS selector for the single actionable next/load-more control, not for the whole pagination container and not for the whole set of page number buttons.
4. If the HTML includes a `PAGINATION_CONTROL_SUMMARY`, use it as strong evidence to distinguish:
   - the current page indicator,
   - numbered page buttons,
   - the real next/previous/load-more control.
5. For `click_next`, `next_button_selector` must target the concrete next-page control only.
   It must NOT be a selector that matches:
   - all pagination anchors or buttons,
   - all numbered page buttons,
   - the entire pagination container.
6. Only populate `page_number_selectors` with selectors for numbered page buttons. Do not put the next/load-more selector into `page_number_selectors`.
7. If there is no distinct next/load-more control, return `pagination_strategy: "none"` or an empty `next_button_selector` rather than guessing a broad selector.
8. Account for multi-language text variations (Next/Load More, 下一页/加载更多).
9. Every selector you return MUST be a standard CSS selector that can be executed directly in Playwright via
   `page.query_selector(...)`, `page.query_selector_all(...)`, `locator(...)`, and in DOM APIs like
   `document.querySelector(...)` / `querySelectorAll(...)`.
10. Do NOT return Playwright-only locator expressions or helper syntax such as `get_by_role(...)`,
   `get_by_text(...)`, `locator(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`, or XPath selectors.
11. Prefer semantic next-button selectors such as `.next`, `.pagination-next`, `a[rel="next"]`, `[aria-label*="next" i]`, or other stable attributes before considering generic position-based selectors.
12. If evidence for the next control is weak or contradictory, choose `pagination_strategy: "none"` rather than guessing.
13. Do not confuse numbered page buttons, current-page indicators, previous buttons, or disabled controls with the real next/load-more action.
14. Reject selectors that match multiple pagination anchors such as `div.kq-pager > a` when only one of those anchors is the real next-page control.

Output format:
```json
{{
  "pagination_strategy": "click_next|infinite_scroll|load_more|none",
  "next_button_selector": "robust CSS selector for next button",
  "page_number_selectors": ["list of page number selectors"],
  "reason": "Explain why this selector and strategy were chosen",
  "confidence": 0.0-1.0
}}
```"""

