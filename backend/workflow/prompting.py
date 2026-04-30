"""Prompt assembly for workflow script generation."""

from __future__ import annotations

from dataclasses import dataclass
import json

from backend.prompts import CrawlerPromptGenerator
from backend.prompts.assemblers.workflow import (
    build_model_guardrails_prompt as assemble_model_guardrails_prompt,
    build_output_strategy_prompt as assemble_output_strategy_prompt,
    build_quality_gate_prompt as assemble_quality_gate_prompt,
    build_review_prompt as assemble_review_prompt,
    build_revision_prompt as assemble_revision_prompt,
)

from backend.workflow.codegen import generate_playwright_skeleton
from backend.workflow.compiler import compile_graph_to_plan, execution_plan_to_dict
from backend.workflow.schemas import WorkflowGraph


@dataclass
class PromptGenerationError(Exception):
    """Raised when prompt generation fails."""

    error: str

    def __str__(self):
        return self.error


def _extract_prompt_config(graph: WorkflowGraph) -> dict:
    config = {
        "url": "",
        "item_selector": "",
        "fields": [],
        "pagination_selector": "",
        "pagination_strategy": "none",
        "max_pages": 1,
        "html_fragment": "",
    }

    for node in graph.nodes:
        data = node.data
        if node.type == "open_page":
            config["url"] = data.url or ""
        elif node.type == "select_list":
            config["item_selector"] = data.item_selector or ""
        elif node.type == "extract_field":
            config["fields"] = data.fields or []
            if data.html_fragment:
                config["html_fragment"] = data.html_fragment
        elif node.type == "paginate":
            config["pagination_selector"] = data.pagination_selector or ""
            if data.pagination_strategy:
                config["pagination_strategy"] = data.pagination_strategy
            if data.max_pages is not None:
                config["max_pages"] = data.max_pages

    return config


def _build_generation_prompt(graph: WorkflowGraph, prompt_override: str | None = None) -> tuple[str, str, dict]:
    config = _extract_prompt_config(graph)
    if not config["url"] or not config["item_selector"]:
        raise PromptGenerationError(
            error="URL and item_selector are required to generate prompt"
        )

    plan = compile_graph_to_plan(graph)
    plan_dict = execution_plan_to_dict(plan)
    pagination = plan_dict.get("pagination", {})
    if not isinstance(pagination, dict):
        pagination = {}
    limits = plan_dict.get("limits", {})
    if not isinstance(limits, dict):
        limits = {}
    base_prompt = CrawlerPromptGenerator().generate_from_simple_config(
        url=plan_dict.get("entry_url", config["url"]),
        item_selector=plan_dict.get("item_selector", config["item_selector"]),
        fields=plan_dict.get("field_specs", []),
        pagination_selector=str(pagination.get("selector", "") or ""),
        pagination_strategy=str(pagination.get("strategy", "none") or "none"),
        max_pages=int(pagination.get("max_pages") or limits.get("max_pages") or 1),
        html_fragment=config.get("html_fragment", ""),
        output_contract=plan_dict.get("output", {}),
        execution_limits=limits,
        conditions=plan_dict.get("conditions", []),
        node_types=plan_dict.get("node_types", []),
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
    _ = editable_prompt
    return assemble_review_prompt(plan_dict, generated_script)


def _build_revision_prompt(
    plan_dict: dict,
    editable_prompt: str,
    current_script: str,
    review_summary: dict,
) -> str:
    return assemble_revision_prompt(plan_dict, editable_prompt, current_script, review_summary)
