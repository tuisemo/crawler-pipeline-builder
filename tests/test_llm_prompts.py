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


def test_pagination_prompt_requires_concrete_next_button_not_broad_pager_selector():
    assert "single actionable next/load-more control" in PAGINATION_ANALYSIS_PROMPT
    assert "not for the whole pagination container" in PAGINATION_ANALYSIS_PROMPT
    assert "PAGINATION_CONTROL_SUMMARY" in PAGINATION_ANALYSIS_PROMPT
    assert 'return `pagination_strategy: "none"` or an empty `next_button_selector` rather than guessing a broad selector' in PAGINATION_ANALYSIS_PROMPT
