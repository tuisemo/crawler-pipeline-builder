"""Assist services for AI-guided workflow authoring."""

from __future__ import annotations

import json
import logging
import re
from html import unescape
from typing import Any

from backend.core.app_logging import audit_event
from extraction.auto_detector import AutoDetector
from extraction.html_extractor import HtmlExtractor
from llm_client import (
    DATA_CLEANING_PROMPT,
    FIELD_INFERENCE_PROMPT,
    PAGINATION_ANALYSIS_PROMPT,
    SELECTOR_OPTIMIZATION_PROMPT,
    get_default_client,
)

logger = logging.getLogger(__name__)

from .assist.json_protocol import (
    JSON_REPAIR_SYSTEM_PROMPT,
    _build_json_repair_prompt,
    _build_json_task_system_prompt,
    _extract_json_payload,
)
from .assist.pagination_recovery import (
    PAGINATION_ANALYSIS_SYSTEM_RULES,
    build_pagination_analysis_user_prompt,
    has_pagination_evidence,
    is_semantically_empty_pagination_result,
    recover_pagination_from_summary,
    recover_partial_pagination_json,
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


FIELD_INFERENCE_RESPONSE_CONTRACT = """Return one JSON object with this shape:
{
  "item_selector": "string",
  "fields": [
    {"name": "string", "selector": "string", "type": "string", "confidence": 0.0}
  ],
  "confidence": 0.0,
  "reason": "string"
}

Rules:
- "fields" must always be an array, even when empty.
- Each field entry must remain a JSON object.
- "confidence" values must be numbers between 0 and 1.
"""

SELECTOR_OPTIMIZATION_RESPONSE_CONTRACT = """Return one JSON object with this shape:
{
  "optimized_selector": "string",
  "confidence": 0.0,
  "reason": "string"
}

Rules:
- "optimized_selector" must be a CSS selector string, or an empty string if unavailable.
- "confidence" must be a number between 0 and 1.
"""

PAGINATION_ANALYSIS_RESPONSE_CONTRACT = """Return one JSON object with this shape:
{
  "pagination_strategy": "click_next|infinite_scroll|load_more|none",
  "next_button_selector": "string",
  "page_number_selectors": ["string"],
  "item_selector": "string",
  "confidence": 0.0,
  "reason": "string"
}

Rules:
- "page_number_selectors" must always be an array.
- Use empty strings or an empty array when data is unavailable.
- "confidence" must be a number between 0 and 1.
"""

DATA_CLEANING_RESPONSE_CONTRACT = """Return one JSON object with this shape:
{
  "cleaned_value": "string | number | boolean | null",
  "confidence": 0.0,
  "reason": "string"
}

Rules:
- Always include the "cleaned_value" key even when the value is null.
- "confidence" must be a number between 0 and 1.
"""

def _extract_html_section(section_name: str, html_fragment: str) -> str:
    pattern = re.compile(
        rf"<!--\s*{re.escape(section_name)}\s*-->\s*([\s\S]*?)(?:<!--\s*[A-Z_]+\s*-->|$)",
        re.IGNORECASE,
    )
    match = pattern.search(html_fragment or "")
    return match.group(1).strip() if match else ""


def _extract_item_samples(html_fragment: str) -> list[str]:
    item_samples = _extract_html_section("ITEM_SAMPLES", html_fragment) or html_fragment or ""
    return [line.strip() for line in item_samples.splitlines() if line.strip().startswith("<")]


def _extract_shared_item_selector_from_samples(samples: list[str]) -> str:
    if not samples:
        return ""
    opening_tags = [re.match(r"<([a-zA-Z0-9]+)([^>]*)>", sample) for sample in samples]
    opening_tags = [match for match in opening_tags if match]
    if not opening_tags:
        return ""
    tag = opening_tags[0].group(1).lower()
    class_sets: list[list[str]] = []
    for match in opening_tags:
        attrs = match.group(2)
        class_match = re.search(r'class="([^"]+)"', attrs)
        if not class_match:
            class_sets.append([])
            continue
        class_sets.append(_stable_class_tokens(class_match.group(1)))
    shared = class_sets[0]
    for token_list in class_sets[1:]:
        token_set = set(token_list)
        shared = [token for token in shared if token in token_set]
        if not shared:
            break
    if shared:
        return f'{tag}.{".".join(shared)}'
    return tag


def _selector_from_tag_and_class(tag: str, class_name: str) -> str:
    classes = _stable_class_tokens(class_name)
    if classes:
        return f'{tag}.{".".join(classes)}'
    return tag


def _extract_text_candidates(sample_html: str, pattern: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for match in re.finditer(pattern, sample_html, re.IGNORECASE | re.DOTALL):
        tag = match.group("tag").lower()
        attrs = match.group("attrs") or ""
        text = re.sub(r"<[^>]+>", " ", match.group("text") or "")
        text = re.sub(r"\s+", " ", unescape(text)).strip()
        class_match = re.search(r'class="([^"]+)"', attrs)
        candidates.append({
            "tag": tag,
            "class": class_match.group(1) if class_match else "",
            "text": text,
        })
    return candidates


def _heuristic_infer_fields(html_fragment: str) -> dict[str, Any] | None:
    samples = _extract_item_samples(html_fragment)
    if not samples:
        return None

    first = samples[0]
    fields: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_field(name: str, selector: str, field_type: str, confidence: float):
        key = (name, selector, field_type)
        if not selector or key in seen:
            return
        seen.add(key)
        fields.append({
            "name": name,
            "selector": selector,
            "type": field_type,
            "confidence": confidence,
        })

    title_candidates = _extract_text_candidates(
        first,
        r"<(?P<tag>h[1-6]|a|p|span|div)(?P<attrs>[^>]*)>(?P<text>.*?)</(?P=tag)>",
    )
    for candidate in title_candidates:
        text = candidate["text"]
        class_name = candidate["class"]
        if not text or len(text) < 6 or len(text) > 220:
            continue
        if candidate["tag"].startswith("h") or re.search(r"(title|tit|name|heading)", class_name, re.IGNORECASE):
            add_field("title", _selector_from_tag_and_class(candidate["tag"], class_name), "text", 0.9)
            break
    if not any(field["name"] == "title" for field in fields):
        for candidate in title_candidates:
            text = candidate["text"]
            if candidate["tag"] == "a" and 6 <= len(text) <= 220:
                add_field("title", _selector_from_tag_and_class(candidate["tag"], candidate["class"]), "text", 0.78)
                break

    image_match = re.search(r"<img(?P<attrs>[^>]*)>", first, re.IGNORECASE)
    if image_match:
        attrs = image_match.group("attrs") or ""
        class_match = re.search(r'class="([^"]+)"', attrs)
        add_field("image", _selector_from_tag_and_class("img", class_match.group(1) if class_match else ""), "attr:src", 0.86)

    link_match = re.search(r"<a(?P<attrs>[^>]*)href=\"[^\"]+\"[^>]*>(?P<text>.*?)</a>", first, re.IGNORECASE | re.DOTALL)
    if link_match:
        attrs = link_match.group("attrs") or ""
        class_match = re.search(r'class="([^"]+)"', attrs)
        link_text = re.sub(r"<[^>]+>", " ", link_match.group("text") or "")
        link_text = re.sub(r"\s+", " ", unescape(link_text)).strip()
        confidence = 0.82 if len(link_text) >= 6 else 0.68
        add_field("link", _selector_from_tag_and_class("a", class_match.group(1) if class_match else ""), "attr:href", confidence)

    date_candidates = _extract_text_candidates(
        first,
        r"<(?P<tag>span|em|time|p|div)(?P<attrs>[^>]*)>(?P<text>.*?)</(?P=tag)>",
    )
    for candidate in date_candidates:
        text = candidate["text"]
        class_name = candidate["class"]
        if re.search(r"(date|time|sj)", class_name, re.IGNORECASE) or re.search(r"\d{4}[-./年]\d{1,2}[-./月]?\d{0,2}", text):
            add_field("date", _selector_from_tag_and_class(candidate["tag"], class_name), "text", 0.8)
            break

    for candidate in title_candidates:
        text = candidate["text"]
        if candidate["tag"] == "p" and len(text) >= 40:
            add_field("summary", _selector_from_tag_and_class(candidate["tag"], candidate["class"]), "text", 0.72)
            break

    if not fields:
        return None

    return {
        "item_selector": _extract_shared_item_selector_from_samples(samples),
        "fields": fields[:6],
        "confidence": 0.62,
        "reason": "Recovered from deterministic HTML heuristics because the model returned an empty field inference result.",
    }


def _heuristic_optimize_selector(initial_selector: str, html_fragment: str) -> dict[str, Any] | None:
    selector = (initial_selector or "").strip()
    if not selector:
        return None

    optimized = selector
    reason_parts: list[str] = []

    optimized = re.sub(r"\.(?:clearfix|clear|active|current|selected)\b", "", optimized)
    optimized = re.sub(r"\.item-\d+\b", "", optimized)
    optimized = re.sub(r"\.w-node-[a-zA-Z0-9_-]+\b", "", optimized)
    optimized = re.sub(r"\s{2,}", " ", optimized).strip()

    if optimized != selector:
        reason_parts.append("Removed utility or volatile classes that are unlikely to be semantic.")

    if "#" in optimized:
        repeated_id_match = re.search(r'id="([^"]+)"', html_fragment)
        if repeated_id_match and html_fragment.count(f'id="{repeated_id_match.group(1)}"') > 1:
            shared_selector = _extract_shared_item_selector_from_samples(_extract_item_samples(html_fragment))
            if shared_selector:
                optimized = shared_selector
                reason_parts.append("Replaced a duplicated ID-based selector with a shared tag/class selector derived from repeated item samples.")

    optimized = re.sub(r"\s+\>\s+", " > ", optimized).strip()
    optimized = re.sub(r"\.{2,}", ".", optimized)

    if not optimized:
        return None

    if not reason_parts:
        reason_parts.append("The current selector is already stable enough based on the repeated item structure in the provided HTML.")

    return {
        "optimized_selector": optimized,
        "confidence": 0.78 if optimized != selector else 0.92,
        "reason": " ".join(reason_parts),
    }


def _normalize_assist_json_result(task_name: str, parsed: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(parsed)

    if task_name == "infer_fields":
        normalized["item_selector"] = normalized.get("item_selector") if isinstance(normalized.get("item_selector"), str) else ""
        fields = normalized.get("fields")
        normalized["fields"] = fields if isinstance(fields, list) else []
    elif task_name == "optimize_selector":
        normalized["optimized_selector"] = normalized.get("optimized_selector") if isinstance(normalized.get("optimized_selector"), str) else ""
    elif task_name == "analyze_pagination":
        strategy = normalized.get("pagination_strategy")
        normalized["pagination_strategy"] = strategy if isinstance(strategy, str) else "none"
        normalized["next_button_selector"] = normalized.get("next_button_selector") if isinstance(normalized.get("next_button_selector"), str) else ""
        page_selectors = normalized.get("page_number_selectors")
        normalized["page_number_selectors"] = page_selectors if isinstance(page_selectors, list) else []
        normalized["item_selector"] = normalized.get("item_selector") if isinstance(normalized.get("item_selector"), str) else ""
    elif task_name == "clean_data":
        if "cleaned_value" not in normalized:
            normalized["cleaned_value"] = None

    confidence = normalized.get("confidence")
    if not isinstance(confidence, (int, float)):
        normalized["confidence"] = None

    reason = normalized.get("reason")
    if not isinstance(reason, str):
        normalized["reason"] = None

    return normalized


def _stable_class_tokens(class_name: str) -> list[str]:
    tokens = []
    for token in re.split(r"\s+", class_name.strip()):
        cleaned = token.strip()
        if not cleaned or any(ch.isdigit() for ch in cleaned) or len(cleaned) > 40:
            continue
        if re.match(r"^[a-zA-Z_-][a-zA-Z0-9_-]*$", cleaned):
            tokens.append(cleaned)
    return tokens[:2]


def _attempt_semantic_retry(
    client: Any,
    user_prompt: str,
    task_name: str,
    response_contract: str,
    previous_output: str,
    system_suffix: str = "",
) -> tuple[dict[str, Any] | None, Any]:
    retry_response = client.generate_with_system(
        system=(
            f"{_build_json_task_system_prompt(response_contract, system_suffix=system_suffix)}\n\n"
            "The previous answer was semantically empty. If pagination evidence exists, do not return an all-empty `none` result."
        ),
        user=(
            f"{user_prompt}\n\n"
            "Previous model output was semantically empty and should be treated as invalid for this task:\n"
            f"{previous_output}"
        ),
        temperature=0.05,
        max_tokens=4000,
        response_format={"type": "json_object"},
        request_name=f"assist_{task_name}_semantic_retry",
    )
    if retry_response.error:
        return None, retry_response
    parsed = _extract_json_payload(retry_response.content or "")
    if parsed is None:
        return None, retry_response
    normalized = _normalize_assist_json_result(task_name, parsed)
    return normalized, retry_response


def _attempt_repair_json_payload(client: Any, raw_output: str, response_contract: str) -> tuple[dict[str, Any] | None, Any]:
    repair_response = client.generate_with_system(
        system=f"{JSON_REPAIR_SYSTEM_PROMPT}\n\n{response_contract}",
        user=_build_json_repair_prompt(response_contract, raw_output),
        temperature=0,
        max_tokens=1200,
        response_format={"type": "json_object"},
        request_name="assist_json_repair",
    )
    if repair_response.error:
        return None, repair_response
    return _extract_json_payload(repair_response.content or ""), repair_response


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
        # Stateless assist calls with only a URL should not silently reuse the
        # most recent browser session from another site. Reuse is reserved for
        # explicit session_id-based workflows initiated by the UI.
        if url and not session_id:
            session = page_session_mgr.create()
        else:
            session = get_active_session()
            if session is not None and not session.is_alive():
                page_session_mgr.close(session.id)
                session = None

            if session is None:
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
    audit_event(
        "assist_auto_detect_started",
        session_id=request.session_id,
        url=request.url,
    )
    session, error = _ensure_session(request.session_id, request.url)
    if error:
        audit_event(
            "assist_auto_detect_failed",
            session_id=request.session_id,
            url=request.url,
            error=error,
        )
        return AutoDetectResponse(success=False, error=error)

    detector = AutoDetector()
    result = detector.detect(session.page)
    audit_event(
        "assist_auto_detect_completed",
        session_id=session.id,
        url=request.url,
        result={
            "item_selector": result.item_selector,
            "item_count": result.item_count,
            "item_signature": result.item_signature,
            "pagination_selector": result.pagination_selector,
            "pagination_strategy": result.pagination_strategy,
            "pagination_score": result.pagination_score,
            "confidence": result.confidence,
            "field_count": len(result.fields),
            "html_fragment": result.html_fragment,
        },
    )
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
        audit_event(
            "assist_extract_html_failed",
            session_id=request.session_id,
            url=request.url,
            item_selector=request.item_selector,
            include_pagination=request.include_pagination,
            max_items=request.max_items,
            error=error,
        )
        return AssistHtmlExtractResponse(success=False, error=error)

    extractor = HtmlExtractor()
    if request.include_pagination:
        result = extractor.extract_pagination_context(
            session.page,
            request.item_selector,
            max_items=request.max_items,
        )
    else:
        result = extractor.extract_item_container(
            session.page,
            request.item_selector,
            max_items=request.max_items,
        )
    audit_event(
        "assist_extract_html_completed",
        session_id=session.id,
        url=request.url,
        item_selector=request.item_selector,
        include_pagination=request.include_pagination,
        max_items=request.max_items,
        html_fragment=result.html,
        metadata={
            "truncated": result.truncated,
            "original_size": result.original_size,
            "truncated_size": result.truncated_size,
            "item_count": result.item_count,
            "has_item_samples": "<!-- ITEM_SAMPLES -->" in result.html,
            "has_pagination_html": "<!-- PAGINATION -->" in result.html,
            "has_pagination_summary": "<!-- PAGINATION_CONTROL_SUMMARY -->" in result.html,
        },
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


def _run_llm_json_task(
    user_prompt: str,
    task_name: str,
    response_contract: str,
    system_suffix: str = "",
    max_tokens: int = 8000,
) -> AssistLlmResponse:
    audit_event(
        "assist_task_started",
        task_name=task_name,
        response_contract=response_contract,
        user_prompt=user_prompt,
    )
    try:
        client = get_default_client()
        response = client.generate_with_system(
            system=_build_json_task_system_prompt(response_contract, system_suffix=system_suffix),
            user=user_prompt,
            temperature=0.1,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            request_name=f"assist_{task_name}",
        )
    except Exception as error:
        logger.exception("Assist task failed before LLM response", extra={"task_name": task_name})
        audit_event("assist_task_exception", task_name=task_name, error=str(error))
        return AssistLlmResponse(success=False, error=str(error))

    if response.error:
        audit_event("assist_task_llm_error", task_name=task_name, error=response.error)
        return AssistLlmResponse(success=False, error=response.error)

    parsed = _extract_json_payload(response.content or "")
    if parsed is None:
        partial_recovery = recover_partial_pagination_json(response.content or "") if task_name == "analyze_pagination" else None
        if partial_recovery is not None:
            parsed = partial_recovery
        else:
            repaired_payload, repair_response = _attempt_repair_json_payload(
                client,
                response.content or "",
                response_contract,
            )
            audit_event(
                "assist_task_repair_attempt",
                task_name=task_name,
                raw_output=response.content or "",
                repair_response=getattr(repair_response, "content", None),
            )
            if repaired_payload is None:
                combined_usage = response.usage
                if isinstance(response.usage, dict) and isinstance(getattr(repair_response, "usage", None), dict):
                    combined_usage = {
                        key: int(response.usage.get(key, 0)) + int(repair_response.usage.get(key, 0))
                        for key in set(response.usage) | set(repair_response.usage)
                    }
                return AssistLlmResponse(
                    success=False,
                    error="Model output was not valid JSON; expected a single JSON object only",
                    raw=response.content,
                    model=repair_response.model or response.model,
                    usage=combined_usage,
                )
            parsed = repaired_payload
            if isinstance(response.usage, dict) and isinstance(getattr(repair_response, "usage", None), dict):
                response.usage = {
                    key: int(response.usage.get(key, 0)) + int(repair_response.usage.get(key, 0))
                    for key in set(response.usage) | set(repair_response.usage)
                }
            if getattr(repair_response, "content", None):
                response.content = repair_response.content
            if getattr(repair_response, "model", None):
                response.model = repair_response.model

    normalized = _normalize_assist_json_result(task_name, parsed)
    audit_event(
        "assist_task_normalized",
        task_name=task_name,
        normalized_result=normalized,
        raw_output=response.content or "",
    )

    if is_semantically_empty_pagination_result(task_name, normalized) and has_pagination_evidence(user_prompt):
        heuristic_result = recover_pagination_from_summary(user_prompt)
        if heuristic_result is not None:
            normalized = heuristic_result
            audit_event("assist_task_heuristic_fallback", task_name=task_name, recovered_result=normalized)
        else:
            retried_result, retry_response = _attempt_semantic_retry(
                client,
                user_prompt,
                task_name,
                response_contract,
                response.content or "",
                system_suffix=system_suffix,
            )
            audit_event(
                "assist_task_semantic_retry",
                task_name=task_name,
                retry_response=getattr(retry_response, "content", None),
                retried_result=retried_result,
            )
            if retried_result is not None and not is_semantically_empty_pagination_result(task_name, retried_result):
                normalized = retried_result
                if isinstance(response.usage, dict) and isinstance(getattr(retry_response, "usage", None), dict):
                    response.usage = {
                        key: int(response.usage.get(key, 0)) + int(retry_response.usage.get(key, 0))
                        for key in set(response.usage) | set(retry_response.usage)
                    }
                if getattr(retry_response, "content", None):
                    response.content = retry_response.content
                if getattr(retry_response, "model", None):
                    response.model = retry_response.model
            else:
                audit_event(
                    "assist_task_semantic_failure",
                    task_name=task_name,
                    raw_output=response.content or "",
                    normalized_result=normalized,
                )
                return AssistLlmResponse(
                    success=False,
                    error="Pagination analysis returned a semantically empty result despite visible pagination evidence",
                    raw=response.content,
                    model=getattr(retry_response, "model", None) or response.model,
                    usage=response.usage,
                )

    audit_event(
        "assist_task_completed",
        task_name=task_name,
        result=normalized,
        model=response.model,
        usage=response.usage,
    )
    return AssistLlmResponse(
        success=True,
        result=normalized,
        confidence=float(normalized.get("confidence")) if isinstance(normalized.get("confidence"), (int, float)) else None,
        reason=normalized.get("reason") if isinstance(normalized.get("reason"), str) else None,
        raw=response.content,
        model=response.model,
        usage=response.usage,
    )


def infer_fields(request: AssistLlmRequest) -> AssistLlmResponse:
    # Truncate HTML to 6000 chars to prevent prompt token explosion on large pages.
    html = (request.html_fragment or "")[:6000]
    prompt = FIELD_INFERENCE_PROMPT.format(html_fragment=html)
    return _run_llm_json_task(prompt, task_name="infer_fields", response_contract=FIELD_INFERENCE_RESPONSE_CONTRACT)


def optimize_selector(request: AssistLlmRequest) -> AssistLlmResponse:
    initial_selector = request.initial_selector or ""
    # Truncate HTML to 6000 chars to keep prompt within budget.
    html = (request.html_fragment or "")[:6000]
    prompt = SELECTOR_OPTIMIZATION_PROMPT.format(
        initial_selector=initial_selector,
        html_fragment=html,
    )
    return _run_llm_json_task(prompt, task_name="optimize_selector", response_contract=SELECTOR_OPTIMIZATION_RESPONSE_CONTRACT)


def analyze_pagination(request: AssistLlmRequest) -> AssistLlmResponse:
    # Pass only HTML evidence in user prompt; move analysis rules to system suffix.
    evidence_prompt = build_pagination_analysis_user_prompt(request.html_fragment)
    return _run_llm_json_task(
        evidence_prompt,
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
        system_suffix=PAGINATION_ANALYSIS_SYSTEM_RULES,
        max_tokens=4000,
    )


def clean_data(request: AssistCleanDataRequest) -> AssistLlmResponse:
    prompt = DATA_CLEANING_PROMPT.format(
        raw_data=request.raw_data,
        data_type=request.data_type,
    )
    return _run_llm_json_task(prompt, task_name="clean_data", response_contract=DATA_CLEANING_RESPONSE_CONTRACT)
