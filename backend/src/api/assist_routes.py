"""AI assist API routes — all routes require authentication."""

from typing import Annotated

from fastapi import APIRouter, Depends

from auth.dependencies import require_auth, AuthenticatedUser
from core.api_response import api_response
from assist.services import (
    analyze_pagination,
    infer_fields,
    optimize_selector,
)
from workflow.schemas import (
    AssistLlmRequest,
)

router = APIRouter(prefix="/api/assist", tags=["assist"])
CurrentUser = Annotated[AuthenticatedUser, Depends(require_auth)]


@router.post("/infer-fields")
def infer_fields_endpoint(request: AssistLlmRequest, _current_user: CurrentUser):
    response = infer_fields(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)


@router.post("/optimize-selector")
def optimize_selector_endpoint(request: AssistLlmRequest, _current_user: CurrentUser):
    response = optimize_selector(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)


@router.post("/analyze-pagination")
def analyze_pagination_endpoint(request: AssistLlmRequest, _current_user: CurrentUser):
    response = analyze_pagination(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)
