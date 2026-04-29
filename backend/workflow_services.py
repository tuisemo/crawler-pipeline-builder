"""Workflow services - domain logic layer for workflow operations.

This module contains pure business logic without HTTP concerns.
HTTP protocol handling (JSONResponse construction) is handled by workflow_routes.py.
"""

from dataclasses import dataclass

from .workflow_compiler import compile_graph_to_plan, execution_plan_to_dict
from .workflow_codegen import generate_playwright_skeleton
from .workflows.generation_pipeline import generate_crawler
from .workflows.prompting import (
    PromptGenerationError,
    _build_generation_prompt,
)
from .workflows.script_artifacts import (
    ScriptFormattingError,
    ScriptPersistenceError,
    format_script,
    save_script,
)
from .workflows.script_sandbox import run_generated_script_sandbox
from .workflows.validation import WorkflowValidationError, validate_graph
from .core.settings import get_settings

from .workflow_schemas import (
    FromLegacyConfigRequest,
    FromLegacyConfigResponse,
    NodeData,
    ToPromptRequest,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    CompilePlanRequest,
    CompilePlanResponse,
    GenerateSkeletonRequest,
    GenerateSkeletonResponse,
    RunScriptSandboxRequest,
    RunScriptSandboxResponse,
)


DEPRECATED_NODE_DATA_KEYS = {"max_steps", "max_items"}
DEPRECATED_EXTRACTION_FIELD_KEYS = {"sample_value", "clean_data_type", "normalized_sample"}


def _sanitize_extract_fields(fields: list[dict] | None) -> list[dict] | None:
    if fields is None:
        return None
    sanitized_fields: list[dict] = []
    for field in fields:
        if not isinstance(field, dict):
            sanitized_fields.append(field)
            continue
        sanitized_fields.append({
            key: value
            for key, value in field.items()
            if key not in DEPRECATED_EXTRACTION_FIELD_KEYS
        })
    return sanitized_fields


def _sanitize_node_data(data: NodeData) -> NodeData:
    payload = data.model_dump()
    for key in DEPRECATED_NODE_DATA_KEYS:
        payload.pop(key, None)
    if isinstance(payload.get("fields"), list):
        payload["fields"] = _sanitize_extract_fields(payload.get("fields"))
    return NodeData.model_validate(payload)


def _sanitize_graph(graph: WorkflowGraph) -> WorkflowGraph:
    return WorkflowGraph(
        nodes=[
            WorkflowNode(id=node.id, type=node.type, data=_sanitize_node_data(node.data))
            for node in graph.nodes
        ],
        edges=list(graph.edges),
    )


# ----------------------------------------------------------------------
# Domain Exceptions - raised by service layer, caught by routes layer
# ----------------------------------------------------------------------


@dataclass
class WorkflowConversionError(Exception):
    """Raised when legacy config conversion fails."""
    error: str

    def __str__(self):
        return self.error


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
            data=NodeData(fields=_sanitize_extract_fields(request.fields), html_fragment=request.html_fragment),
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
    sanitized_graph = _sanitize_graph(request.graph)
    final_prompt, editable_prompt, plan_dict = _build_generation_prompt(sanitized_graph)
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
        plan = compile_graph_to_plan(_sanitize_graph(request.graph))
        return CompilePlanResponse(success=True, plan=execution_plan_to_dict(plan), warnings=[])
    except Exception as e:
        return CompilePlanResponse(success=False, error=str(e))


def generate_skeleton(request: GenerateSkeletonRequest) -> GenerateSkeletonResponse:
    """Generate deterministic crawler skeleton from workflow graph."""
    try:
        plan = compile_graph_to_plan(_sanitize_graph(request.graph))
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


def run_script_sandbox(request: RunScriptSandboxRequest) -> RunScriptSandboxResponse:
    """Manually execute a generated or edited script in the configured sandbox."""
    settings = get_settings()
    if not settings.script_sandbox_enabled:
        return RunScriptSandboxResponse(success=False, error="Script sandbox is disabled by configuration.")

    try:
        result = run_generated_script_sandbox(
            request.script,
            filename=request.filename,
            timeout_seconds=request.timeout_seconds or settings.script_sandbox_timeout_seconds,
            metadata={"source": "manual_request"},
        )
        return RunScriptSandboxResponse(success=result.success, sandbox_result=result.to_dict(), error=result.error)
    except Exception as e:
        return RunScriptSandboxResponse(success=False, error=str(e))
