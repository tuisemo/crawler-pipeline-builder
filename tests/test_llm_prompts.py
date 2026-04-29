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


def test_generation_prompts_preserve_validated_xpath_selectors():
    from llm_client import CRAWLER_SYSTEM_PROMPT
    from prompts import CrawlerPromptGenerator

    generator_prompt = CrawlerPromptGenerator().generate_from_simple_config(
        url="https://example.com",
        item_selector='xpath=//div[@class="item"]',
        fields=[{"name": "title", "selector": 'xpath=.//h2', "type": "text"}],
        pagination_selector='xpath=//a[@rel="next"]',
        pagination_strategy="click_next",
        max_pages=2,
    )
    lowered_prompt = generator_prompt.lower()
    lowered_system = CRAWLER_SYSTEM_PROMPT.lower()

    assert "validated selectors may be css selectors or xpath selectors" in lowered_prompt
    assert "keep using xpath in a playwright-compatible form" in lowered_prompt
    assert "reuse the validated selectors" in lowered_prompt
    assert "validated xpath selectors" in lowered_system
    assert "decision hierarchy" in lowered_system
    assert "autoresearch" not in lowered_system


def test_generation_prompts_use_task_quality_gates_not_autoresearch_label():
    from backend.workflows.generation_pipeline import CRAWLER_REVIEW_SYSTEM_PROMPT
    from backend.workflows.prompting import _build_generation_prompt
    from backend.workflow_schemas import NodeData, WorkflowGraph, WorkflowNode

    graph = WorkflowGraph(
        nodes=[
            WorkflowNode(id="n1", type="open_page", data=NodeData(url="https://example.com")),
            WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
            WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": ".title", "type": "text"}])),
        ],
        edges=[],
    )

    final_prompt, _, _ = _build_generation_prompt(graph)
    lowered_prompt = final_prompt.lower()
    lowered_review = CRAWLER_REVIEW_SYSTEM_PROMPT.lower()

    assert "quality gate" in lowered_prompt
    assert "autoresearch" not in lowered_prompt
    assert "release gate" in lowered_review
    assert "autoresearch" not in lowered_review


def test_pagination_prompt_requires_concrete_next_button_not_broad_pager_selector():
    assert "single actionable next/load-more control" in PAGINATION_ANALYSIS_PROMPT
    assert "not for the whole pagination container" in PAGINATION_ANALYSIS_PROMPT
    assert "PAGINATION_CONTROL_SUMMARY" in PAGINATION_ANALYSIS_PROMPT
    assert 'return `pagination_strategy: "none"` or an empty `next_button_selector` rather than guessing a broad selector' in PAGINATION_ANALYSIS_PROMPT


def test_assist_prompts_add_evidence_and_semantic_guardrails():
    assert "Evidence Handling" in FIELD_INFERENCE_PROMPT
    assert "primary record link" in FIELD_INFERENCE_PROMPT
    assert "expected match cardinality" in SELECTOR_OPTIMIZATION_PROMPT
    assert "Evidence Priority" in PAGINATION_ANALYSIS_PROMPT
    assert "Do not confuse numbered page buttons" in PAGINATION_ANALYSIS_PROMPT
