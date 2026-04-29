"""Prompt assembly for workflow script generation."""

from __future__ import annotations

from dataclasses import dataclass
import json

from prompts import CrawlerPromptGenerator

from ..workflow_codegen import generate_playwright_skeleton
from ..workflow_compiler import compile_graph_to_plan, execution_plan_to_dict
from ..workflow_schemas import WorkflowGraph


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


def _resolve_output_mode(plan_dict: dict) -> str:
    output = plan_dict.get("output", {})
    if isinstance(output, dict):
        mode = str(output.get("mode", "memory") or "memory").strip().lower()
        if mode == "memory":
            return "memory"
        if mode == "sqlite":
            return "sqlite"
    return "json_file"


def _build_output_strategy_prompt(plan_dict: dict) -> str:
    output = plan_dict.get("output", {})
    if not isinstance(output, dict):
        output = {}

    output_mode = _resolve_output_mode(plan_dict)
    if output_mode == "memory":
        memory_strategy = {
            "mode": "memory",
            "write_mode": output.get("write_mode", "append"),
            "dedupe_keys": output.get("dedupe_keys", []),
            "batch_size": output.get("batch_size", 50),
        }
        return (
            "## Output Strategy (In-Memory)\n"
            "```json\n"
            f"{json.dumps(memory_strategy, ensure_ascii=False, indent=2)}\n"
            "```\n"
            "Keep records in memory unless the deterministic execution plan explicitly requests JSON file or SQLite persistence.\n"
            "Do not silently add file writes, database writes, or export side effects when the mode is `memory`.\n\n"
        )

    if output_mode == "sqlite":
        sqlite_strategy = {
            "mode": "sqlite",
            "sqlite_path": output.get("sqlite_path", "output/crawler_output.db"),
            "sqlite_table": output.get("sqlite_table", "records"),
            "write_mode": output.get("write_mode", "append"),
            "dedupe_keys": output.get("dedupe_keys", []),
            "batch_size": output.get("batch_size", 50),
        }
        return (
            "## Output Strategy (SQLite)\n"
            "```json\n"
            f"{json.dumps(sqlite_strategy, ensure_ascii=False, indent=2)}\n"
            "```\n"
            "Implement local SQLite persistence with `sqlite3`.\n"
            "Keep schema creation, safe identifier handling, metadata columns, and deterministic upsert behavior.\n"
            "If dedupe keys are configured, preserve them as the primary conflict target; otherwise fall back to a record hash.\n\n"
        )

    json_strategy = {
        "mode": "json_file",
        "json_file_path": output.get("json_file_path", "crawler_output.json"),
        "write_mode": output.get("write_mode", "append"),
        "dedupe_keys": output.get("dedupe_keys", []),
    }
    return (
        "## Output Strategy (JSON File)\n"
        "```json\n"
        f"{json.dumps(json_strategy, ensure_ascii=False, indent=2)}\n"
        "```\n"
        "Implement file output as a valid local JSON document containing records.\n"
        "If `write_mode` is `upsert`, merge records deterministically using configured dedupe keys or a record hash.\n"
        "Do not silently switch this workflow to SQLite unless the execution plan explicitly requests it.\n\n"
    )


def _build_model_guardrails_prompt(plan_dict: dict) -> str:
    pagination = plan_dict.get("pagination", {})
    if not isinstance(pagination, dict):
        pagination = {}
    output = plan_dict.get("output", {})
    if not isinstance(output, dict):
        output = {}

    return (
        "## Non-Negotiable Implementation Guardrails\n"
        "- Treat the deterministic execution plan as the single source of truth for control flow, limits, field schema, and output behavior.\n"
        "- Treat every selector already present in the execution plan as user-validated input. Preserve validated selectors whenever possible instead of inventing new ones.\n"
        "- Validated selectors may be CSS or XPath. If the plan provides XPath, keep XPath in a Playwright-compatible form unless it is clearly invalid or semantically wrong.\n"
        "- Do not introduce Playwright-only locator syntax such as `get_by_role(...)`, `get_by_text(...)`, `text=...`, `:has-text(...)`, `nth=`, or `>>`.\n"
        "- Only replace a validated selector when it is clearly invalid, incompatible with Playwright execution, or points to the wrong target element.\n"
        f"- Pagination strategy is `{pagination.get('strategy', 'none')}` and pagination selector is `{pagination.get('selector', '')}`; do not invent extra pagination behavior beyond that contract.\n"
        f"- Output mode is `{output.get('mode', 'memory')}`; do not silently switch persistence strategy.\n\n"
    )


def _build_quality_gate_prompt(plan_dict: dict) -> str:
    pagination = plan_dict.get("pagination", {})
    if not isinstance(pagination, dict):
        pagination = {}
    output = plan_dict.get("output", {})
    if not isinstance(output, dict):
        output = {}

    return (
        "## Quality Gate\n"
        "Return the final script only if every check below passes. Otherwise revise before returning.\n"
        "- Check 1: control flow matches the deterministic execution plan exactly.\n"
        "- Check 2: extraction fields, field types, and selectors remain aligned with the plan schema.\n"
        "- Check 3: output persistence mode remains `{mode}`.\n"
        "- Check 4: pagination behavior remains `{strategy}` with selector `{selector}` unless the selector is clearly invalid.\n"
        "- Check 5: no Playwright API misuse (`ElementHandle.locator(...)` is forbidden).\n"
        "- Check 6: selector changes are evidence-based and minimal; preserve validated selectors when possible.\n"
        "- Check 7: avoid unnecessary complexity; prefer the simplest deterministic code path that satisfies the plan.\n\n"
    ).format(
        mode=output.get("mode", "memory"),
        strategy=pagination.get("strategy", "none"),
        selector=pagination.get("selector", ""),
    )


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


def _build_review_prompt(
    plan_dict: dict,
    editable_prompt: str,
    generated_script: str,
) -> str:
    # We summarize the intent to save tokens in the review stage, 
    # since the plan_dict already contains the deterministic goals.
    return (
        "## Review Target\n"
        "Audit the crawler draft against the execution plan and output strategy.\n\n"
        "## Decision Policy\n"
        "- Approve only if all critical contracts are satisfied.\n"
        "- Prefer specific, evidence-based findings over style commentary.\n"
        "- If uncertain, mark the issue as medium/low severity with clear rationale.\n\n"
        "## Execution Plan\n"
        "```json\n"
        f"{json.dumps(plan_dict, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        f"{_build_output_strategy_prompt(plan_dict)}"
        "## Draft Script\n"
        "```python\n"
        f"{generated_script}\n"
        "```\n\n"
        "Check for control-flow drift, pagination mistakes, extraction schema mismatches, "
        "output persistence regressions, and weak error handling.\n"
        "Return JSON only.\n"
    )


def _build_revision_prompt(
    plan_dict: dict,
    editable_prompt: str,
    current_script: str,
    review_summary: dict,
) -> str:
    return (
        "## Revision Goal\n"
        "Apply the review feedback to the crawler draft while preserving the deterministic plan and output contract.\n\n"
        "## Revision Policy\n"
        "- Make the smallest set of edits that resolves all high/medium findings.\n"
        "- Preserve stable helpers unless they directly violate requirements.\n"
        "- Do not introduce new architecture or extra features not requested.\n\n"
        "## User Intent\n"
        f"{editable_prompt}\n\n"
        "## Execution Plan\n"
        "```json\n"
        f"{json.dumps(plan_dict, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        f"{_build_output_strategy_prompt(plan_dict)}"
        "## Review Feedback\n"
        "```json\n"
        f"{json.dumps(review_summary, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "## Current Script\n"
        "```python\n"
        f"{current_script}\n"
        "```\n\n"
        "Return only the final complete Python script.\n"
    )
