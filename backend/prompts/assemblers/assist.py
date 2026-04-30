"""Assist prompt assembly helpers."""

from backend.prompts.tasks.assist_tasks import (
    FIELD_INFERENCE_PROMPT_TEMPLATE,
    PAGINATION_ANALYSIS_PROMPT_TEMPLATE,
    SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE,
)


def build_field_inference_prompt(html_fragment: str) -> str:
    return FIELD_INFERENCE_PROMPT_TEMPLATE.format(html_fragment=html_fragment)


def build_selector_optimization_prompt(initial_selector: str, html_fragment: str) -> str:
    return SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE.format(
        initial_selector=initial_selector,
        html_fragment=html_fragment,
    )


def build_pagination_analysis_prompt(html_fragment: str) -> str:
    return PAGINATION_ANALYSIS_PROMPT_TEMPLATE.format(html_fragment=html_fragment)
