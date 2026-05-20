"""Prompt assembly for workflow script generation."""

from __future__ import annotations

from dataclasses import dataclass
import json

from prompts import CrawlerPromptGenerator
from prompts.assemblers.workflow import (
    build_model_guardrails_prompt as assemble_model_guardrails_prompt,
    build_output_strategy_prompt as assemble_output_strategy_prompt,
    build_quality_gate_prompt as assemble_quality_gate_prompt,
    build_review_prompt as assemble_review_prompt,
    build_revision_prompt as assemble_revision_prompt,
)

from workflow.codegen import generate_playwright_skeleton
from workflow.compiler import compile_graph_to_plan, execution_plan_to_dict
from workflow.schemas import WorkflowGraph


@dataclass
class PromptGenerationError(Exception):
    """Raised when prompt generation fails."""

    error: str

    def __str__(self):
        return self.error


def _extract_html_fragment(graph: WorkflowGraph) -> str:
    for node in graph.nodes:
        if node.type == "extract_field" and node.data.html_fragment:
            return node.data.html_fragment
    return ""


def _build_generation_prompt(graph: WorkflowGraph, prompt_override: str | None = None) -> tuple[str, str, dict]:
    plan = compile_graph_to_plan(graph)
    if not plan.entry_url or not plan.item_selector:
        raise PromptGenerationError(
            error="URL and item_selector are required to generate prompt"
        )

    plan_dict = execution_plan_to_dict(plan)
    base_prompt = CrawlerPromptGenerator().generate_from_plan(
        plan_dict,
        html_fragment=_extract_html_fragment(graph),
    )
    editable_prompt = prompt_override.strip() if isinstance(prompt_override, str) and prompt_override.strip() else base_prompt

    strategy_prompt = _build_output_strategy_prompt(plan_dict)
    guardrails_prompt = _build_model_guardrails_prompt(plan_dict)
    quality_gate_prompt = _build_quality_gate_prompt(plan_dict)
    plan_prompt = (
        "## Execution Plan (Deterministic)\n"
        "```json\n"
        f"{json.dumps(plan_dict, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "Please preserve this execution plan's control flow and field schema.\n\n"
    )
    final_prompt = f"{plan_prompt}{strategy_prompt}{guardrails_prompt}{quality_gate_prompt}{editable_prompt}"
    return final_prompt, editable_prompt, plan_dict


def _build_skeleton_enhancement_prompt(
    graph: WorkflowGraph,
    prompt_override: str | None = None,
) -> tuple[str, str, dict, str]:
    """Build an LLM prompt that enhances the deterministic skeleton instead of free-writing."""
    final_prompt, editable_prompt, plan_dict = _build_generation_prompt(graph, prompt_override)
    skeleton_script = generate_playwright_skeleton(plan_dict)
    enhancement_prompt = (
        f"{final_prompt}"
        "## Deterministic Skeleton (Reference Base)\n"
        "Below is the exact baseline script generated from the execution plan.\n"
        "Revise and improve this script instead of writing a crawler from scratch.\n"
        "Preserve its overall control flow, extraction schema, and output contract.\n"
        "If SQLite helpers or persistence helpers are present, keep and strengthen them rather than removing them.\n"
        "Return only the final complete Python script.\n\n"
        "```python\n"
        f"{skeleton_script}\n"
        "```\n"
    )
    return enhancement_prompt, editable_prompt, plan_dict, skeleton_script


def _build_output_strategy_prompt(plan_dict: dict) -> str:
    return assemble_output_strategy_prompt(plan_dict)


def _build_model_guardrails_prompt(plan_dict: dict) -> str:
    return assemble_model_guardrails_prompt(plan_dict)


def _build_quality_gate_prompt(plan_dict: dict) -> str:
    return assemble_quality_gate_prompt(plan_dict)


def _build_review_prompt(
    plan_dict: dict,
    editable_prompt: str,
    generated_script: str,
) -> str:
    return assemble_review_prompt(plan_dict, editable_prompt, generated_script)


def _build_revision_prompt(
    plan_dict: dict,
    editable_prompt: str,
    current_script: str,
    review_summary: dict,
) -> str:
    return assemble_revision_prompt(plan_dict, editable_prompt, current_script, review_summary)
