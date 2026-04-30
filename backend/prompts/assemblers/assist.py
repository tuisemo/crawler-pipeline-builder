"""Assist prompt assembly helpers."""

from backend.prompts.tasks.assist_tasks import (
    FIELD_INFERENCE_PROMPT_TEMPLATE,
    PAGINATION_ANALYSIS_PROMPT_TEMPLATE,
    SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE,
)


def build_field_inference_prompt(html_fragment: str) -> str:
    evidence = "\n".join([
        "## Evidence Package",
        "### HTML Fragment",
        html_fragment,
    ]).strip()
    return FIELD_INFERENCE_PROMPT_TEMPLATE.format(html_fragment=evidence)


def build_selector_optimization_prompt(initial_selector: str, html_fragment: str) -> str:
    structured_html = "\n".join([
        "## Input",
        f"### Initial Selector\n{initial_selector}",
        "",
        "### HTML Fragment",
        html_fragment,
    ]).strip()
    return SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE.format(
        initial_selector=initial_selector,
        html_fragment=structured_html,
    )


def build_pagination_analysis_prompt(html_fragment: str) -> str:
    return PAGINATION_ANALYSIS_PROMPT_TEMPLATE.format(html_fragment=html_fragment)
