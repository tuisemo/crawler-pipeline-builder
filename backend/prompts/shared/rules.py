"""Reusable prompt rules shared across crawler generation and assist tasks."""

PLAYWRIGHT_CSS_SELECTOR_COMPATIBILITY_RULES = """3. Every selector MUST be a **standard CSS selector** compatible with `querySelector` / `querySelectorAll` and Playwright `locator()`.
4. Do NOT return Playwright-only locator expressions or helper syntax such as `get_by_role(...)`, `get_by_text(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`, or XPath selectors."""

SELECTOR_PRESERVATION_RULES = """7. Treat the deterministic execution plan as the single source of truth; do not invent control flow, persistence behavior, or selectors that conflict with it
8. Treat selectors already present in the execution plan as user-validated configuration. Preserve them whenever possible instead of replacing them
9. Validated selectors may be CSS or XPath. If XPath is already validated and Playwright-compatible, keep it rather than rewriting it as CSS
10. Do not replace a validated selector unless it is clearly invalid, incompatible with Playwright, or semantically wrong for the target element"""

PLAYWRIGHT_ELEMENT_HANDLE_RULES = """- Use `page.locator(...)` only when you are intentionally working with a Playwright `Page` or `Frame` locator
- When you already have an `ElementHandle` (for example from `query_selector(...)`, `query_selector_all(...)`, or iterating `items`), do NOT call `.locator(...)` on it
- For child lookups under an `ElementHandle`, use `query_selector(...)` / `query_selector_all(...)` on that handle instead
- For clicking next page with an `ElementHandle`, call `scroll_into_view_if_needed()` and then `click()` on that handle"""

MINIMAL_CHANGE_POLICY = """- Make the smallest safe change set that resolves the task.
- Preserve stable helpers and existing deterministic behavior unless they directly violate the prompt contract.
- Do not introduce speculative abstractions or extra features."""

LOW_CONFIDENCE_FALLBACK_POLICY = """- If evidence is insufficient, return the best structured result with lower confidence instead of fabricating certainty.
- Prefer fewer high-quality fields or selectors over many speculative ones.
- If the next control is weak or contradictory, choose `pagination_strategy: "none"` rather than guessing."""

