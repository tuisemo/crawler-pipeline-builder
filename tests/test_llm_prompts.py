from llm_client import (
    FIELD_INFERENCE_PROMPT,
    PAGINATION_ANALYSIS_PROMPT,
    SELECTOR_OPTIMIZATION_PROMPT,
)


def test_selector_prompts_require_playwright_compatible_css_selectors():
    prompts = [
        FIELD_INFERENCE_PROMPT,
        SELECTOR_OPTIMIZATION_PROMPT,
        PAGINATION_ANALYSIS_PROMPT,
    ]

    for prompt in prompts:
        assert "standard CSS selector" in prompt
        assert "Playwright" in prompt
        assert "querySelectorAll" in prompt
        assert "Do NOT return Playwright-only locator expressions" in prompt
        assert "XPath selectors" in prompt
        assert ":has-text(...)" in prompt
        assert "text=" in prompt
