from fastapi import APIRouter

from backend.core.api_response import api_response
from backend.workflow.executor import executor
from backend.workflow.schemas import (
    FromLegacyConfigRequest,
    FormatScriptRequest,
    GenerateCrawlerRequest,
    RunScriptSandboxRequest,
    SaveScriptRequest,
    TestNodeRequest,
    TestSubflowRequest,
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


@router.post("/validate")
def validate_workflow(request: ValidateWorkflowRequest):
    """Validate a workflow DSL graph."""
    try:
        return api_response(validate_graph(request))
    except WorkflowValidationError as e:
        return api_response(status_code=400, success=False, error_code=e.error_code, error=e.error)

@router.post("/from-legacy-config")
def from_legacy_config(request: FromLegacyConfigRequest):
    """Convert a legacy config to a workflow DSL graph."""
    try:
        return api_response(convert_legacy_config(request))
    except WorkflowConversionError as e:
        return api_response(status_code=400, success=False, error_code="workflow_conversion_error", error=str(e))

@router.post("/to-prompt")
def to_prompt(request: ToPromptRequest):
    """Convert a workflow DSL graph to a prompt for LLM generation."""
    try:
        return api_response(graph_to_prompt(request))
    except PromptGenerationError as e:
        return api_response(status_code=400, success=False, error_code="prompt_generation_error", error=str(e))


@router.post("/compile-plan")
def compile_plan_endpoint(request: CompilePlanRequest):
    """Compile a workflow DSL graph into a deterministic execution plan."""
    return api_response(compile_plan(request))


@router.post("/generate-skeleton")
def generate_skeleton_endpoint(request: GenerateSkeletonRequest):
    """Generate deterministic crawler skeleton without invoking LLM."""
    return api_response(generate_skeleton(request))


@router.post("/generate-crawler")
def generate_crawler_endpoint(request: GenerateCrawlerRequest):
    """Generate a Playwright crawler script from a DSL workflow graph.

    This endpoint:
    1. Receives a WorkflowGraph (nodes + edges)
    2. Calls existing CrawlerPromptGenerator to generate prompt
    3. Calls the backend LLM client to generate the crawler script
    4. Returns {success, prompt, script, filename, model, usage} or error
    """
    return api_response(generate_crawler(request))


@router.post("/run-script-sandbox")
def run_script_sandbox_endpoint(request: RunScriptSandboxRequest):
    """Manually execute a generated or edited script in the script sandbox."""
    return api_response(run_script_sandbox(request))


@router.post("/format-script")
def format_script_endpoint(request: FormatScriptRequest):
    """Format generated script content for the editor workspace."""
    try:
        return api_response(format_script(request))
    except ScriptFormattingError as e:
        return api_response(status_code=400, success=False, error_code="script_formatting_error", error=str(e))


@router.post("/save-script")
def save_script_endpoint(request: SaveScriptRequest):
    """Save generated or edited script content into the project workspace."""
    try:
        return api_response(save_script(request))
    except ScriptPersistenceError as e:
        return api_response(status_code=400, success=False, error_code=e.error_code, error=e.error)


@router.post("/test-node")
async def test_node(request: TestNodeRequest):
    """Test a single workflow node with minimal prerequisites.
    
    This endpoint executes only the requested node and its necessary
    prerequisites, without committing downstream workflow side effects.
    Returns structured logs and node results for inspection.
    """
    return api_response(await executor.test_node(request))


@router.post("/test-subflow")
async def test_subflow(request: TestSubflowRequest):
    """Test a workflow subflow within graph boundaries.
    
    This endpoint executes nodes within the specified subflow boundaries,
    respecting execution limits (max_pages).
    Returns structured logs, node results, and sample records.
    Partial-run failures preserve inspectable outputs.
    """
    return api_response(await executor.test_subflow(request))
