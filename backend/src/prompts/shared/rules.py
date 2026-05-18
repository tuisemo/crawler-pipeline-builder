"""Reusable prompt rules shared across crawler generation and assist tasks."""

PLAYWRIGHT_CSS_SELECTOR_COMPATIBILITY_RULES = """3. Every selector MUST be either a **standard CSS selector** or an **XPath expression**.
   - Playwright natively supports XPath via `page.query_selector("xpath=//...")` / `page.locator("xpath=//...")`.
   - The runtime auto-detects XPath when the selector starts with `//` or `.//` and adds the `xpath=` prefix.
4. Do NOT return Playwright-only locator helper syntax such as `get_by_role(...)`, `get_by_text(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`.
5. Do NOT use jQuery/Sizzle pseudo-classes such as `:contains('...')`, `:first`, `:last`, `:eq(...)`. These are NOT standard CSS and will throw `SyntaxError` in `document.querySelector()` / `querySelectorAll()`.
   - **Forbidden**: `.pager > a:contains('下一页')` — crashes at runtime.
6. When you need **text-content matching**, use XPath instead of CSS. Examples:
   - `//a[contains(text(), '下一页')]` — match anchor whose text contains a substring.
   - `//nav[contains(@class, 'pagination')]//a[@rel='next']` — scoped XPath with attribute matching.
   - CSS has no native text-matching pseudo-class; do NOT invent one."""

STRICT_OUTPUT_DISCIPLINE_RULES = """- Return only the requested artifact.
- Do not add surrounding commentary when the contract expects machine-consumable output.
- If evidence is weak, express uncertainty inside the allowed schema instead of writing prose outside it."""

SCRIPT_OUTPUT_LOCK = """- Return only the final complete Python script.
- Do not wrap the script in markdown fences.
- Do not add commentary before or after the script."""

JSON_OUTPUT_LOCK = """- Return JSON only.
- Do not use markdown fences.
- Do not add prose before or after the JSON object."""

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

EVIDENCE_FIRST_POLICY = """- Use the strongest structural evidence first.
- Prefer stable semantic anchors and repeatable patterns over brittle heuristics.
- If evidence conflicts, choose the more conservative interpretation."""

SMALLEST_STABLE_CHANGE_POLICY = """- Make the smallest stable improvement that increases correctness or robustness.
- If the current selector or implementation is already acceptable, keep it unchanged."""

