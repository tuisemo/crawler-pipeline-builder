"""Assist services for AI-guided workflow authoring."""

from __future__ import annotations

import json
import re
from typing import Any

from extraction.auto_detector import AutoDetector
from extraction.html_extractor import HtmlExtractor
from llm_client import (
    DATA_CLEANING_PROMPT,
    FIELD_INFERENCE_PROMPT,
    PAGINATION_ANALYSIS_PROMPT,
    SELECTOR_OPTIMIZATION_PROMPT,
    get_default_client,
)

from .browser_session import get_active_session, page_session_mgr
from .workflow_schemas import (
    AssistCleanDataRequest,
    AssistLlmRequest,
    AssistLlmResponse,
    AssistHtmlExtractRequest,
    AssistHtmlExtractResponse,
    AutoDetectRequest,
    AutoDetectResponse,
)


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json_payload(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None

    stripped = raw.strip()
    for candidate in (stripped, *_JSON_BLOCK_RE.findall(stripped)):
        try:
            parsed = json.loads(candidate.strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    object_match = _JSON_OBJECT_RE.search(stripped)
    if object_match:
        try:
            parsed = json.loads(object_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None

    return None


def _ensure_session(session_id: str | None, url: str | None):
    session = None
    if session_id:
        session = page_session_mgr.get(session_id)
        if session is not None and session.is_alive():
            pass # Keep using it
        else:
            if session:
                page_session_mgr.close(session_id)
            session = None

    if session is None:
        session = get_active_session()
        if session is not None and not session.is_alive():
            page_session_mgr.close(session.id)
            session = None
            
        if session is None:
            # We don't have a session, so we create a new one.
            session = page_session_mgr.create()

    # Wait, what if we just created a new session? We need to navigate to the URL if provided.
    # The previous logic conditionally navigated if url was provided.
    # We should always navigate to the URL if it's a new session, or if url is given.
    # Actually, the original logic just did:
    if url:
        try:
            session.navigate(url, timeout=30000)
        except Exception as e:
            return None, f"Failed to navigate: {str(e)}"
            
    return session, None


def auto_detect(request: AutoDetectRequest) -> AutoDetectResponse:
    session, error = _ensure_session(request.session_id, request.url)
    if error:
        return AutoDetectResponse(success=False, error=error)

    detector = AutoDetector()
    result = detector.detect(session.page)
    return AutoDetectResponse(
        success=True,
        session_id=session.id,
        result={
            "item_selector": result.item_selector,
            "item_count": result.item_count,
            "item_signature": result.item_signature,
            "pagination_selector": result.pagination_selector,
            "pagination_strategy": result.pagination_strategy,
            "pagination_score": result.pagination_score,
            "confidence": result.confidence,
            "fields": [
                {
                    "name": field.name,
                    "selector": field.selector,
                    "type": field.extraction_type,
                    "confidence": field.confidence,
                }
                for field in result.fields
            ],
            "html_fragment": result.html_fragment,
        },
    )


def extract_html_fragment(request: AssistHtmlExtractRequest) -> AssistHtmlExtractResponse:
    session, error = _ensure_session(request.session_id, request.url)
    if error:
        return AssistHtmlExtractResponse(success=False, error=error)

    extractor = HtmlExtractor()
    result = extractor.extract_item_container(
        session.page,
        request.item_selector,
        max_items=request.max_items,
    )
    return AssistHtmlExtractResponse(
        success=True,
        session_id=session.id,
        html_fragment=result.html,
        metadata={
            "truncated": result.truncated,
            "original_size": result.original_size,
            "truncated_size": result.truncated_size,
            "item_count": result.item_count,
        },
    )


def _run_llm_json_task(user_prompt: str) -> AssistLlmResponse:
    try:
        client = get_default_client()
        response = client.generate_with_system(
            system="You are a web scraping assistant. Return strict JSON only.",
            user=user_prompt,
            temperature=0.1,
            max_tokens=1500,
        )
    except Exception as error:
        return AssistLlmResponse(success=False, error=str(error))

    if response.error:
        return AssistLlmResponse(success=False, error=response.error)

    parsed = _extract_json_payload(response.content or "")
    if parsed is None:
        return AssistLlmResponse(
            success=False,
            error="Model output was not valid JSON",
            raw=response.content,
            model=response.model,
            usage=response.usage,
        )

    return AssistLlmResponse(
        success=True,
        result=parsed,
        confidence=float(parsed.get("confidence")) if isinstance(parsed.get("confidence"), (int, float)) else None,
        reason=parsed.get("reason") if isinstance(parsed.get("reason"), str) else None,
        raw=response.content,
        model=response.model,
        usage=response.usage,
    )


def infer_fields(request: AssistLlmRequest) -> AssistLlmResponse:
    prompt = FIELD_INFERENCE_PROMPT.format(html_fragment=request.html_fragment)
    return _run_llm_json_task(prompt)


def optimize_selector(request: AssistLlmRequest) -> AssistLlmResponse:
    initial_selector = request.initial_selector or ""
    prompt = SELECTOR_OPTIMIZATION_PROMPT.format(
        initial_selector=initial_selector,
        html_fragment=request.html_fragment,
    )
    return _run_llm_json_task(prompt)


def analyze_pagination(request: AssistLlmRequest) -> AssistLlmResponse:
    prompt = PAGINATION_ANALYSIS_PROMPT.format(html_fragment=request.html_fragment)
    return _run_llm_json_task(prompt)


def clean_data(request: AssistCleanDataRequest) -> AssistLlmResponse:
    prompt = DATA_CLEANING_PROMPT.format(
        raw_data=request.raw_data,
        data_type=request.data_type,
    )
    return _run_llm_json_task(prompt)
