from fastapi import APIRouter

from .workflow_executor import executor
from .workflow_schemas import (
    FromLegacyConfigRequest,
    FromLegacyConfigResponse,
    GenerateCrawlerRequest,
    GenerateCrawlerResponse,
    TestNodeRequest,
    TestNodeResponse,
    TestSubflowRequest,
    TestSubflowResponse,
    ToPromptRequest,
    ValidateWorkflowRequest,
)
from .workflow_services import convert_legacy_config, generate_crawler, graph_to_prompt, validate_graph

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

@router.post("/validate")
def validate_workflow(request: ValidateWorkflowRequest):
    return validate_graph(request)

@router.post("/from-legacy-config", response_model=FromLegacyConfigResponse)
def from_legacy_config(request: FromLegacyConfigRequest):
    return convert_legacy_config(request)

@router.post("/to-prompt")
def to_prompt(request: ToPromptRequest):
    return graph_to_prompt(request)


@router.post("/generate-crawler", response_model=GenerateCrawlerResponse)
def generate_crawler_endpoint(request: GenerateCrawlerRequest):
    """Generate a Playwright crawler script from a DSL workflow graph.

    This endpoint:
    1. Receives a WorkflowGraph (nodes + edges)
    2. Calls existing CrawlerPromptGenerator to generate prompt
    3. Calls LLM via llm_client.py to generate the crawler script
    4. Returns {success, prompt, script, filename, model, usage} or error
    """
    return generate_crawler(request)


@router.post("/test-node")
async def test_node(request: TestNodeRequest) -> TestNodeResponse:
    """Test a single workflow node with minimal prerequisites.
    
    This endpoint executes only the requested node and its necessary
    prerequisites, without committing downstream workflow side effects.
    Returns structured logs and node results for inspection.
    """
    return await executor.test_node(request)


@router.post("/test-subflow")
async def test_subflow(request: TestSubflowRequest) -> TestSubflowResponse:
    """Test a workflow subflow within graph boundaries.
    
    This endpoint executes nodes within the specified subflow boundaries,
    respecting execution limits (max_items, max_pages, max_steps).
    Returns structured logs, node results, and sample records.
    Partial-run failures preserve inspectable outputs.
    """
    return await executor.test_subflow(request)
