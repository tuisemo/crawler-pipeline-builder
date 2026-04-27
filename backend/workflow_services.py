"""Workflow services - domain logic layer for workflow operations.

This module contains pure business logic without HTTP concerns.
HTTP protocol handling (JSONResponse construction) is handled by workflow_routes.py.
"""

import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from llm_client import get_default_client, CRAWLER_SYSTEM_PROMPT
from prompts import CrawlerPromptGenerator
from .workflow_compiler import compile_graph_to_plan, execution_plan_to_dict
from .workflow_codegen import generate_playwright_skeleton

from .workflow_schemas import (
    FromLegacyConfigRequest,
    FromLegacyConfigResponse,
    NodeData,
    OpenPageData,
    SelectListData,
    ExtractFieldData,
    PaginateData,
    FieldSchema,
    ToPromptRequest,
    ValidateWorkflowRequest,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    GenerateCrawlerRequest,
    GenerateCrawlerResponse,
    FormatScriptRequest,
    FormatScriptResponse,
    CompilePlanRequest,
    CompilePlanResponse,
    GenerateSkeletonRequest,
    GenerateSkeletonResponse,
    SaveScriptRequest,
    SaveScriptResponse,
)


# ----------------------------------------------------------------------
# Domain Exceptions - raised by service layer, caught by routes layer
# ----------------------------------------------------------------------


@dataclass
class WorkflowValidationError(Exception):
    """Raised when workflow validation fails."""
    error_code: str
    error: str

    def __str__(self):
        return f"{self.error_code}: {self.error}"


@dataclass
class WorkflowConversionError(Exception):
    """Raised when legacy config conversion fails."""
    error: str

    def __str__(self):
        return self.error


@dataclass
class PromptGenerationError(Exception):
    """Raised when prompt generation fails."""
    error: str

    def __str__(self):
        return self.error


@dataclass
class ScriptFormattingError(Exception):
    error: str

    def __str__(self):
        return self.error


@dataclass
class ScriptPersistenceError(Exception):
    error_code: str
    error: str

    def __str__(self):
        return f"{self.error_code}: {self.error}"


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_GENERATION_MAX_TOKENS = 12000
SCRIPT_REVIEW_MAX_TOKENS = 2500
SUPPORTED_GENERATION_MODES = {"lite", "pro"}


SUPPORTED_EXECUTABLE_NODE_TYPES = {
    "open_page",
    "select_list",
    "extract_field",
    "paginate",
    "emit_record",
    "loop",
    "condition",
    "end",
}


CRAWLER_REVIEW_SYSTEM_PROMPT = """You are a principal reviewer for production Playwright crawlers.

Review the provided script against the deterministic execution plan, the requested output strategy, and the user intent.
Do not rewrite the script. Return JSON only with this shape:
{
  "approve": true,
  "summary": "short review summary",
  "issues": [
    {
      "severity": "high|medium|low",
      "category": "plan|pagination|extraction|output|resilience|quality",
      "finding": "what is wrong or risky",
      "fix": "specific fix direction"
    }
  ],
  "revision_instructions": ["specific instruction 1", "specific instruction 2"]
}

Set "approve" to false when issues remain that should be fixed before returning the final script."""


CRAWLER_REVISION_SYSTEM_PROMPT = """You are an expert Python Web Scraping Engineer specializing in Playwright.

Revise the provided crawler draft using the structured review feedback.
Preserve the deterministic execution plan, stable helper functions, and the output contract.
Return only the final complete Python script."""


def _validate_field_schema(raw_field: object, index: int) -> None:
    try:
        field = FieldSchema.model_validate(raw_field)
    except Exception as e:
        raise WorkflowValidationError(
            error_code="extract_field_invalid_field",
            error=f"extract_field field[{index}] validation failed: {e}."
        ) from e

    if not field.resolved_name():
        raise WorkflowValidationError(
            error_code="extract_field_requires_field_name",
            error=f"extract_field field[{index}] requires a non-empty name or field_name."
        )
    if not field.resolved_selector():
        raise WorkflowValidationError(
            error_code="extract_field_requires_field_selector",
            error=f"extract_field field[{index}] requires a non-empty selector or css."
        )


def _validate_edge_references(graph: WorkflowGraph) -> None:
    node_ids = {node.id for node in graph.nodes}
    missing_sources = sorted({edge.source for edge in graph.edges if edge.source not in node_ids})
    if missing_sources:
        raise WorkflowValidationError(
            error_code="edge_source_missing",
            error=f"Workflow edges reference missing source nodes: {', '.join(missing_sources)}."
        )

    missing_targets = sorted({edge.target for edge in graph.edges if edge.target not in node_ids})
    if missing_targets:
        raise WorkflowValidationError(
            error_code="edge_target_missing",
            error=f"Workflow edges reference missing target nodes: {', '.join(missing_targets)}."
        )


def _validate_supported_node_types(nodes: Iterable[WorkflowNode]) -> None:
    unsupported = sorted({node.type for node in nodes if node.type not in SUPPORTED_EXECUTABLE_NODE_TYPES})
    if unsupported:
        raise WorkflowValidationError(
            error_code="unsupported_node_type",
            error=f"Workflow contains unsupported node types for execution: {', '.join(unsupported)}."
        )


def validate_node_data(node: WorkflowNode) -> None:
    """Validate required fields for a core node type.

    Raises WorkflowValidationError if a required field is missing or blank
    for any of the four core node types (open_page, select_list, extract_field, paginate).
    Unknown node types and nodes that are already optional (e.g. open_page with no url)
    are allowed to pass silently for MVP compatibility.
    """
    node_type = node.type
    data = node.data

    if node_type == "open_page":
        if not (data.url and data.url.strip()):
            raise WorkflowValidationError(
                error_code="open_page_requires_url",
                error="open_page node requires a non-empty url field."
            )
    elif node_type == "select_list":
        if not (data.item_selector and data.item_selector.strip()):
            raise WorkflowValidationError(
                error_code="select_list_requires_item_selector",
                error="select_list node requires a non-empty item_selector field."
            )
    elif node_type == "extract_field":
        raw_fields = data.fields
        if not raw_fields:
            raise WorkflowValidationError(
                error_code="extract_field_requires_fields",
                error="extract_field node requires a non-empty fields list."
            )
        if not isinstance(raw_fields, list):
            raise WorkflowValidationError(
                error_code="extract_field_requires_fields_list",
                error="extract_field node fields must be a list."
            )
        if len(raw_fields) == 0:
            raise WorkflowValidationError(
                error_code="extract_field_requires_fields",
                error="extract_field node requires at least one field."
            )
        for i, raw_field in enumerate(raw_fields):
            _validate_field_schema(raw_field, i)
    elif node_type == "paginate":
        if not (data.pagination_selector and data.pagination_selector.strip()):
            raise WorkflowValidationError(
                error_code="paginate_requires_pagination_selector",
                error="paginate node requires a non-empty pagination_selector field."
            )
    elif node_type == "loop":
        # loop.max_items is optional; use execution context limit at runtime
        # on_error defaults to "skip" in handler if not set
        pass
    elif node_type == "condition":
        if not (data.condition and data.condition.strip()):
            raise WorkflowValidationError(
                error_code="condition_requires_expression",
                error="condition node requires a non-empty condition field."
            )
    elif node_type == "end":
        # end has no required fields
        pass


def validate_graph(request: ValidateWorkflowRequest) -> dict:
    """Validate a workflow graph and return domain result.
    
    Raises WorkflowValidationError if validation fails.
    """
    graph = request.graph
    if not graph.nodes:
        raise WorkflowValidationError(
            error_code="workflow_empty",
            error="Workflow must have at least one node."
        )

    duplicate_node_ids = _find_duplicates(node.id for node in graph.nodes)
    if duplicate_node_ids:
        raise WorkflowValidationError(
            error_code="duplicate_node_ids",
            error=f"Workflow node ids must be unique: {', '.join(duplicate_node_ids)}."
        )

    duplicate_edge_ids = _find_duplicates(edge.id for edge in graph.edges)
    if duplicate_edge_ids:
        raise WorkflowValidationError(
            error_code="duplicate_edge_ids",
            error=f"Workflow edge ids must be unique: {', '.join(duplicate_edge_ids)}."
        )

    _validate_edge_references(graph)
    _validate_supported_node_types(graph.nodes)

    entry_nodes = [node for node in graph.nodes if node.type == "open_page"]
    if not entry_nodes:
        raise WorkflowValidationError(
            error_code="entry_node_missing",
            error="Workflow must have an 'open_page' entry node."
        )
    if len(entry_nodes) > 1:
        raise WorkflowValidationError(
            error_code="entry_node_multiple",
            error="Workflow can only have one 'open_page' entry node."
        )

    # Phase 1 schema hardening: validate required fields per node type.
    # This catches missing url, item_selector, fields, and pagination_selector
    # at validation time rather than deferring to runtime.
    for node in graph.nodes:
        validate_node_data(node)

    return {"success": True, "message": "Workflow is valid"}


def _find_duplicates(values) -> list[str]:
    seen = set()
    duplicates = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _normalize_script_text(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [line.rstrip().replace("\t", "    ") for line in normalized.split("\n")]
    compacted = "\n".join(normalized_lines).strip("\n")
    return f"{compacted}\n" if compacted else ""


def _resolve_workspace_path(relative_path: str) -> Path:
    candidate = (relative_path or "").strip().replace("\\", "/")
    if not candidate:
        raise ScriptPersistenceError(
            error_code="relative_path_required",
            error="A non-empty relative_path is required to save a script.",
        )
    raw_path = Path(candidate)
    if raw_path.is_absolute():
        raise ScriptPersistenceError(
            error_code="absolute_path_not_allowed",
            error="Scripts must be saved using a path relative to the project root.",
        )

    target = (WORKSPACE_ROOT / raw_path).resolve()
    try:
        target.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ScriptPersistenceError(
            error_code="path_outside_workspace",
            error="The requested relative_path resolves outside the project workspace.",
        ) from exc
    return target


def convert_legacy_config(request: FromLegacyConfigRequest) -> FromLegacyConfigResponse:
    """Convert a legacy config to a workflow DSL graph.
    
    Raises WorkflowConversionError if required fields are missing/blank.
    """
    if not request.url.strip() or not request.item_selector.strip():
        raise WorkflowConversionError(
            error="URL and item_selector are required for legacy conversion"
        )

    nodes = [
        WorkflowNode(
            id="node_1",
            type="open_page",
            data=NodeData(url=request.url),
        ),
        WorkflowNode(
            id="node_2",
            type="select_list",
            data=NodeData(item_selector=request.item_selector),
        ),
        WorkflowNode(
            id="node_3",
            type="extract_field",
            data=NodeData(fields=request.fields, html_fragment=request.html_fragment),
        ),
    ]
    edges = [
        WorkflowEdge(id="edge_1_2", source="node_1", target="node_2"),
        WorkflowEdge(id="edge_2_3", source="node_2", target="node_3"),
    ]

    if request.pagination_selector:
        nodes.append(
            WorkflowNode(
                id="node_4",
                type="paginate",
                data=NodeData(
                    pagination_selector=request.pagination_selector,
                    pagination_strategy=request.pagination_strategy,
                    max_pages=request.max_pages,
                ),
            )
        )
        edges.append(WorkflowEdge(id="edge_3_4", source="node_3", target="node_4"))

    return FromLegacyConfigResponse(
        success=True,
        graph=WorkflowGraph(nodes=nodes, edges=edges),
        warnings=[],
    )


def graph_to_prompt(request: ToPromptRequest) -> dict:
    """Convert a workflow graph to a prompt for LLM generation.
    
    Raises PromptGenerationError if required config is missing.
    """
    final_prompt, editable_prompt, plan_dict = _build_generation_prompt(request.graph)
    return {
        "success": True,
        "prompt": editable_prompt,
        "editable_prompt": editable_prompt,
        "effective_prompt": final_prompt,
        "plan": plan_dict,
    }


def compile_plan(request: CompilePlanRequest) -> CompilePlanResponse:
    """Compile a DSL workflow graph to a deterministic execution plan."""
    try:
        plan = compile_graph_to_plan(request.graph)
        return CompilePlanResponse(success=True, plan=execution_plan_to_dict(plan), warnings=[])
    except Exception as e:
        return CompilePlanResponse(success=False, error=str(e))


def generate_skeleton(request: GenerateSkeletonRequest) -> GenerateSkeletonResponse:
    """Generate deterministic crawler skeleton from workflow graph."""
    try:
        plan = compile_graph_to_plan(request.graph)
        plan_dict = execution_plan_to_dict(plan)
        if not plan.entry_url or not plan.item_selector:
            return GenerateSkeletonResponse(
                success=False,
                error="URL and item_selector are required to generate skeleton script",
            )
        script = generate_playwright_skeleton(plan_dict)
        return GenerateSkeletonResponse(
            success=True,
            script=script,
            filename="crawler_skeleton.py",
            plan=plan_dict,
            warnings=[],
        )
    except Exception as e:
        return GenerateSkeletonResponse(success=False, error=str(e))


def format_script(request: FormatScriptRequest) -> FormatScriptResponse:
    """Format generated script text for easier editing and saving."""
    content = request.content or ""
    if not content.strip():
        raise ScriptFormattingError("Script content is required for formatting.")

    normalized = _normalize_script_text(content)
    warnings: list[str] = []
    formatter = "basic"

    if request.language.strip().lower() == "python":
        try:
            import black  # type: ignore

            normalized = black.format_str(normalized, mode=black.FileMode())
            formatter = "black"
        except ImportError:
            warnings.append("Black is not installed; applied whitespace-only normalization.")
        except Exception as exc:
            warnings.append(f"Black could not format this script; kept normalized text ({exc}).")

    return FormatScriptResponse(
        success=True,
        formatted_content=normalized,
        changed=normalized != content,
        formatter=formatter,
        warnings=warnings,
    )


def save_script(request: SaveScriptRequest) -> SaveScriptResponse:
    """Persist edited script text inside the repository workspace."""
    content = request.content or ""
    if not content.strip():
        raise ScriptPersistenceError(
            error_code="script_content_required",
            error="Script content is required before saving to a project file.",
        )

    target_path = _resolve_workspace_path(request.relative_path)
    existed_before = target_path.exists()
    if existed_before and not request.overwrite:
        raise ScriptPersistenceError(
            error_code="target_exists",
            error="Target file already exists. Enable overwrite to replace it.",
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_script_text(content)
    target_path.write_text(normalized, encoding="utf-8")

    relative = target_path.relative_to(WORKSPACE_ROOT).as_posix()
    return SaveScriptResponse(
        success=True,
        relative_path=relative,
        absolute_path=str(target_path),
        bytes_written=len(normalized.encode("utf-8")),
        created=not existed_before,
        overwritten=existed_before,
    )


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
        "- Every selector used in the generated script must remain a standard CSS selector executable via Playwright `page.query_selector(...)`, `page.query_selector_all(...)`, or `locator(...)`.\n"
        "- Returned selectors must also stay compatible with `document.querySelector(...)` and `document.querySelectorAll(...)`.\n"
        "- Do not introduce Playwright-only locator syntax such as `get_by_role(...)`, `get_by_text(...)`, `text=...`, `:has-text(...)`, `nth=`, `>>`, or XPath unless the execution plan explicitly provides it.\n"
        f"- Pagination strategy is `{pagination.get('strategy', 'none')}` and pagination selector is `{pagination.get('selector', '')}`; do not invent extra pagination behavior beyond that contract.\n"
        f"- Output mode is `{output.get('mode', 'memory')}`; do not silently switch persistence strategy.\n\n"
    )


def _extract_json_object(content: str) -> dict:
    raw = (content or "").strip()
    if not raw:
        raise ValueError("empty JSON response")

    fenced_match = re.search(r"```json\s*(\{.*\})\s*```", raw, re.DOTALL)
    candidate = fenced_match.group(1) if fenced_match else raw
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(raw[start:end + 1])
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("response did not contain a JSON object")


def _review_requires_revision(review_summary: dict) -> bool:
    if review_summary.get("approve") is False:
        return True
    issues = review_summary.get("issues")
    if isinstance(issues, list) and issues:
        return True
    revision_instructions = review_summary.get("revision_instructions")
    if isinstance(revision_instructions, list) and revision_instructions:
        return True
    return False


def _merge_usage(*usages: dict | None) -> dict[str, int] | None:
    totals: dict[str, int] = {}
    for usage in usages:
        if not isinstance(usage, dict):
            continue
        for key, value in usage.items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _resolve_generation_mode(value: str | None) -> str:
    mode = str(value or "lite").strip().lower()
    return mode if mode in SUPPORTED_GENERATION_MODES else "lite"


def _append_trace(trace: list[dict[str, Any]], stage: str, status: str, **extra: Any) -> None:
    item: dict[str, Any] = {"stage": stage, "status": status}
    for key, value in extra.items():
        if value is not None:
            item[key] = value
    trace.append(item)


def _capture_length_warning(response, stage: str) -> str | None:
    if getattr(response, "finish_reason", None) == "length":
        return f"{stage} reached the model token limit; the returned content may be truncated."
    return None


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
    plan_prompt = (
        "## Execution Plan (Deterministic)\n"
        "```json\n"
        f"{json.dumps(plan_dict, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "Please preserve this execution plan's control flow and field schema.\n\n"
    )
    final_prompt = f"{plan_prompt}{strategy_prompt}{guardrails_prompt}{editable_prompt}"
    return final_prompt, editable_prompt, plan_dict


def _build_skeleton_enhancement_prompt(
    graph: WorkflowGraph,
    prompt_override: str | None = None,
) -> tuple[str, str, dict, str]:
    """Build an LLM prompt that enhances the deterministic skeleton instead of free-writing.

    This keeps `generate-crawler` aligned with the script-first production plan:
    1. compile deterministic execution plan
    2. generate trusted skeleton
    3. ask the LLM to improve that concrete scaffold
    """
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
    return (
        "## Review Target\n"
        "Audit the crawler draft against the execution plan and output strategy.\n\n"
        "## User Intent\n"
        f"{editable_prompt}\n\n"
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


def generate_crawler(request: GenerateCrawlerRequest) -> GenerateCrawlerResponse:
    """Generate a Playwright crawler script from a DSL workflow graph.

    1. Extracts configuration from the graph nodes
    2. Generates a prompt using CrawlerPromptGenerator
    3. Calls LLM to generate the crawler script
    4. Returns {success, prompt, script, filename, model, usage} or error
    """
    try:
        final_prompt, editable_prompt, plan_dict, _skeleton_script = _build_skeleton_enhancement_prompt(
            request.graph,
            request.prompt_override,
        )
    except PromptGenerationError as e:
        return GenerateCrawlerResponse(
            success=False,
            error=str(e)
        )

    # Call LLM
    try:
        client = get_default_client()
        generation_mode = _resolve_generation_mode(request.generation_mode)
        generation_trace: list[dict[str, Any]] = []
        warnings: list[str] = []
        draft_response = client.generate_with_system(
            system=CRAWLER_SYSTEM_PROMPT,
            user=final_prompt,
            max_tokens=SCRIPT_GENERATION_MAX_TOKENS,
        )
        _append_trace(
            generation_trace,
            "draft_generation",
            "completed" if not draft_response.error else "failed",
            model=draft_response.model,
            finish_reason=draft_response.finish_reason,
        )

        if draft_response.error:
            return GenerateCrawlerResponse(
                success=False,
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                error=draft_response.error
            )

        draft_script = draft_response.content
        length_warning = _capture_length_warning(draft_response, "Draft generation")
        if length_warning:
            warnings.append(length_warning)

        if generation_mode == "lite":
            filename = "crawler.py"
            filename_match = re.search(r'crawler_\w+\.py', draft_script)
            if filename_match:
                filename = filename_match.group(0)
            return GenerateCrawlerResponse(
                success=True,
                prompt=final_prompt,
                editable_prompt=editable_prompt,
                script=draft_script,
                filename=filename,
                model=draft_response.model,
                usage=draft_response.usage,
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
            )

        review_prompt = _build_review_prompt(plan_dict, editable_prompt, draft_script)
        review_response = client.generate_with_system(
            system=CRAWLER_REVIEW_SYSTEM_PROMPT,
            user=review_prompt,
            max_tokens=SCRIPT_REVIEW_MAX_TOKENS,
        )
        _append_trace(
            generation_trace,
            "script_review",
            "completed" if not review_response.error else "failed",
            model=review_response.model,
            finish_reason=review_response.finish_reason,
        )
        if review_response.error:
            return GenerateCrawlerResponse(
                success=False,
                prompt=final_prompt,
                editable_prompt=editable_prompt,
                script=draft_script,
                model=draft_response.model,
                usage=_merge_usage(draft_response.usage, review_response.usage),
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                error=review_response.error,
            )

        review_length_warning = _capture_length_warning(review_response, "Script review")
        if review_length_warning:
            warnings.append(review_length_warning)

        try:
            review_summary = _extract_json_object(review_response.content)
        except Exception as e:
            return GenerateCrawlerResponse(
                success=False,
                prompt=final_prompt,
                editable_prompt=editable_prompt,
                script=draft_script,
                model=draft_response.model,
                usage=_merge_usage(draft_response.usage, review_response.usage),
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                error=f"Script review returned invalid JSON: {e}",
            )

        filename = "crawler.py"
        final_script = draft_script
        model_name = draft_response.model
        total_usage = _merge_usage(draft_response.usage, review_response.usage)

        if _review_requires_revision(review_summary):
            revision_prompt = _build_revision_prompt(plan_dict, editable_prompt, draft_script, review_summary)
            revision_response = client.generate_with_system(
                system=CRAWLER_REVISION_SYSTEM_PROMPT,
                user=revision_prompt,
                max_tokens=SCRIPT_GENERATION_MAX_TOKENS,
            )
            _append_trace(
                generation_trace,
                "revision_enhancement",
                "completed" if not revision_response.error else "failed",
                model=revision_response.model,
                finish_reason=revision_response.finish_reason,
            )
            if revision_response.error:
                return GenerateCrawlerResponse(
                    success=False,
                    prompt=final_prompt,
                    editable_prompt=editable_prompt,
                    script=draft_script,
                    model=draft_response.model,
                    usage=_merge_usage(draft_response.usage, review_response.usage, revision_response.usage),
                    generation_mode=generation_mode,
                    generation_trace=generation_trace,
                    warnings=warnings,
                    review_summary=review_summary,
                    error=revision_response.error,
                )
            final_script = revision_response.content
            model_name = revision_response.model or model_name
            total_usage = _merge_usage(draft_response.usage, review_response.usage, revision_response.usage)
            revision_length_warning = _capture_length_warning(revision_response, "Revision enhancement")
            if revision_length_warning:
                warnings.append(revision_length_warning)

        # Try to find a filename like crawler_*.py in the content
        filename_match = re.search(r'crawler_\w+\.py', final_script)
        if filename_match:
            filename = filename_match.group(0)

        return GenerateCrawlerResponse(
            success=True,
            prompt=final_prompt,
            editable_prompt=editable_prompt,
            script=final_script,
            filename=filename,
            model=model_name,
            usage=total_usage,
            generation_mode=generation_mode,
            generation_trace=generation_trace,
            warnings=warnings,
            review_summary=review_summary,
        )
    except Exception as e:
        return GenerateCrawlerResponse(
            success=False,
            error=str(e)
        )
