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
from .workflows.validation import WorkflowValidationError, validate_graph

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

