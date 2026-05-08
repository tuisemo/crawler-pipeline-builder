"""AI assist API routes."""

from fastapi import APIRouter

from backend.core.api_response import api_response
from backend.assist.services import (
    analyze_pagination,
    infer_fields,
    optimize_selector,
)
from backend.workflow.schemas import (
    AssistLlmRequest,
)

router = APIRouter(prefix="/api/assist", tags=["assist"])


@router.post("/infer-fields")
def infer_fields_endpoint(request: AssistLlmRequest):
    response = infer_fields(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)


@router.post("/optimize-selector")
def optimize_selector_endpoint(request: AssistLlmRequest):
    response = optimize_selector(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)


@router.post("/analyze-pagination")
def analyze_pagination_endpoint(request: AssistLlmRequest):
    response = analyze_pagination(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)
