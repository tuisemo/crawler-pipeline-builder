"""Workflow services - domain logic layer for workflow operations.

This module contains pure business logic without HTTP concerns.
HTTP protocol handling (JSONResponse construction) is handled by workflow_routes.py.
"""

from backend.workflow.compiler import compile_graph_to_plan, execution_plan_to_dict
from backend.workflow.codegen import generate_playwright_skeleton
from backend.workflow.detail_batch_generation_pipeline import generate_detail_batch_runner_pipeline
from backend.workflow.generation_pipeline import generate_crawler
from backend.workflow.prompting import (
    PromptGenerationError,
    _build_generation_prompt,
)
from backend.workflow.script_artifacts import (
    ScriptFormattingError,
    ScriptPersistenceError,
    format_script,
    save_script,
)
from backend.workflow.script_sandbox import run_generated_script_sandbox
from backend.workflow.validation import WorkflowValidationError, validate_graph
from backend.core.settings import get_settings

from backend.workflow.schemas import (
    NodeData,
    ToPromptRequest,
    WorkflowGraph,
    CompilePlanRequest,
    CompilePlanResponse,
    GenerateSkeletonRequest,
    GenerateSkeletonResponse,
    GenerateDetailBatchRunnerRequest,
    GenerateDetailBatchRunnerResponse,
    RunScriptSandboxRequest,
    RunScriptSandboxResponse,
)

from backend.workflow._shared import (
    sanitize_graph as _sanitize_graph,
)


# ----------------------------------------------------------------------
# Domain Exceptions - raised by service layer, caught by routes layer
# ----------------------------------------------------------------------


def graph_to_prompt(request: ToPromptRequest) -> dict:
    """Convert a workflow graph to a prompt for LLM generation.
    
    Raises PromptGenerationError if required config is missing.
    """
    try:
        sanitized_graph = _sanitize_graph(request.graph)
    except ValueError as e:
        raise PromptGenerationError(str(e)) from e
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


def generate_detail_batch_runner(request: GenerateDetailBatchRunnerRequest) -> GenerateDetailBatchRunnerResponse:
    """Generate deterministic detail batch orchestration script from structured contracts."""
    try:
        if request.database.database_type.strip().lower() != "sqlite":
            return GenerateDetailBatchRunnerResponse(
                success=False,
                error="Only sqlite database_type is supported for detail batch runner generation.",
            )
        return generate_detail_batch_runner_pipeline(request)
    except Exception as e:
        return GenerateDetailBatchRunnerResponse(success=False, error=str(e))


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
