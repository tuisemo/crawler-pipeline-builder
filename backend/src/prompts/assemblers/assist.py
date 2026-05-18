"""Assist prompt assembly helpers."""

from prompts.tasks.assist_tasks import (
    FIELD_INFERENCE_PROMPT_TEMPLATE,
    SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE,
)


def build_field_inference_prompt(html_fragment: str, user_intent: str | None = None) -> str:
    evidence_parts = [
        "## Evidence Package",
        "### HTML Fragment",
        html_fragment,
    ]
    if user_intent and user_intent.strip():
        evidence_parts.extend([
            "",
            "### User Intent",
            "The user has provided additional requirements for field extraction. "
            "MUST incorporate these requirements into your field inference result:",
            user_intent.strip(),
        ])
    evidence = "\n".join(evidence_parts).strip()
    return FIELD_INFERENCE_PROMPT_TEMPLATE.replace("{html_fragment}", evidence)


def build_selector_optimization_prompt(initial_selector: str, html_fragment: str) -> str:
    structured_html = "\n".join([
        "## Input",
        f"### Initial Selector\n{initial_selector}",
        "",
        "### HTML Fragment",
        html_fragment,
    ]).strip()
    return (
        SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE
        .replace("{initial_selector}", initial_selector)
        .replace("{html_fragment}", structured_html)
    )