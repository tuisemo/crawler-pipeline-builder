"""API routes for workflow DSL operations — all routes require authentication."""

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.auth.dependencies import require_auth, AuthenticatedUser
from backend.core.api_response import api_response
from backend.workflow.schemas import (
    FromLegacyConfigRequest,
    FormatScriptRequest,
    GenerateCrawlerRequest,
    GenerateDetailBatchRunnerRequest,
    RunScriptSandboxRequest,
    SaveScriptRequest,
    ToPromptRequest,
    ValidateWorkflowRequest,
    CompilePlanRequest,
    GenerateSkeletonRequest,
)
from backend.workflow.services import (
    compile_plan,
    convert_legacy_config,
    format_script,
    generate_skeleton,
    generate_detail_batch_runner,
    generate_crawler,
    graph_to_prompt,
    run_script_sandbox,
    save_script,
    validate_graph,
    WorkflowValidationError,
    WorkflowConversionError,
    PromptGenerationError,
    ScriptFormattingError,
    ScriptPersistenceError,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
CurrentUser = Annotated[AuthenticatedUser, Depends(require_auth)]


@router.post("/validate")
def validate_workflow(request: ValidateWorkflowRequest, _current_user: CurrentUser):
    """Validate a workflow DSL graph."""
    try:
        return api_response(validate_graph(request))
    except WorkflowValidationError as e:
        return api_response(status_code=400, success=False, error_code=e.error_code, error=e.error)


@router.post("/from-legacy-config")
def from_legacy_config(request: FromLegacyConfigRequest, _current_user: CurrentUser):
    """Convert a legacy config to a workflow DSL graph."""
    try:
        return api_response(convert_legacy_config(request))
    except WorkflowConversionError as e:
        return api_response(status_code=400, success=False, error_code="workflow_conversion_error", error=str(e))


@router.post("/to-prompt")
def to_prompt(request: ToPromptRequest, _current_user: CurrentUser):
    """Convert a workflow DSL graph to a prompt for LLM generation."""
    try:
        return api_response(graph_to_prompt(request))
    except PromptGenerationError as e:
        return api_response(status_code=400, success=False, error_code="prompt_generation_error", error=str(e))


@router.post("/compile-plan")
def compile_plan_endpoint(request: CompilePlanRequest, _current_user: CurrentUser):
    """Compile a workflow DSL graph into a deterministic execution plan."""
    return api_response(compile_plan(request))


@router.post("/generate-skeleton")
def generate_skeleton_endpoint(request: GenerateSkeletonRequest, _current_user: CurrentUser):
    """Generate deterministic crawler skeleton without invoking LLM."""
    return api_response(generate_skeleton(request))


@router.post("/generate-crawler")
def generate_crawler_endpoint(request: GenerateCrawlerRequest, _current_user: CurrentUser):
    """Generate a Playwright crawler script from a DSL workflow graph.

    This endpoint:
    1. Receives a WorkflowGraph (nodes + edges)
    2. Calls existing CrawlerPromptGenerator to generate prompt
    3. Calls the backend LLM client to generate the crawler script
    4. Returns {success, prompt, script, filename, model, usage} or error
    """
    return api_response(generate_crawler(request))


@router.post("/generate-detail-batch-runner")
def generate_detail_batch_runner_endpoint(request: GenerateDetailBatchRunnerRequest, _current_user: CurrentUser):
    """Generate a standalone Python batch runner that dispatches detail collection CLI tasks."""
    return api_response(generate_detail_batch_runner(request))


@router.post("/run-script-sandbox")
def run_script_sandbox_endpoint(request: RunScriptSandboxRequest, _current_user: CurrentUser):
    """Manually execute a generated or edited script in the script sandbox."""
    return api_response(run_script_sandbox(request))


@router.post("/format-script")
def format_script_endpoint(request: FormatScriptRequest, _current_user: CurrentUser):
    """Format generated script content for the editor workspace."""
    try:
        return api_response(format_script(request))
    except ScriptFormattingError as e:
        return api_response(status_code=400, success=False, error_code="script_formatting_error", error=str(e))


@router.post("/save-script")
def save_script_endpoint(request: SaveScriptRequest, _current_user: CurrentUser):
    """Save generated or edited script content into the project workspace."""
    try:
        return api_response(save_script(request))
    except ScriptPersistenceError as e:
        return api_response(status_code=400, success=False, error_code=e.error_code, error=e.error)
