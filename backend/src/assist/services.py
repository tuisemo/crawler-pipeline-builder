"""Assist services for AI-guided workflow authoring."""

from __future__ import annotations
import logging
import re
from html import unescape
from typing import Any

from core.app_logging import audit_event
from llm import (
    get_default_client,
)
from prompts.assemblers.assist import (
    build_field_inference_prompt,
    build_selector_optimization_prompt,
)
from prompts.contracts.assist_contracts import (
    FIELD_INFERENCE_RESPONSE_CONTRACT,
    PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    SELECTOR_OPTIMIZATION_RESPONSE_CONTRACT,
)

logger = logging.getLogger(__name__)

from assist.json_protocol import (
    JSON_REPAIR_SYSTEM_PROMPT,
    _build_json_repair_prompt,
    _build_json_task_system_prompt,
    _extract_json_payload,
)
from assist.pagination_recovery import (
    PAGINATION_ANALYSIS_SYSTEM_RULES,
    build_pagination_evidence_prompt,
    has_pagination_evidence,
    is_semantically_empty_pagination_result,
    recover_pagination_from_summary,
    recover_partial_pagination_json,
)
from workflow.schemas import (
    AssistLlmRequest,
    AssistLlmResponse,
)
from assist.utils import extract_html_section, stable_class_tokens


def _confidence_bucket(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "unknown"
    if value >= 0.85:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def _emit_assist_prompt_quality_metric(
    *,
    task_name: str,
    success: bool,
    user_prompt: str,
    raw_output: str,
    model: str | None,
    usage: dict[str, Any] | None,
    confidence: object,
    error_code: str | None,
    json_valid_first_pass: bool,
    used_partial_recovery: bool,
    used_repair_pass: bool,
    used_semantic_retry: bool,
    used_heuristic_fallback: bool,
    semantic_empty_detected: bool,
) -> None:
    audit_event(
        "assist_prompt_quality_metric",
        task_name=task_name,
        success=success,
        error_code=error_code,
        model=model or "",
        prompt_chars=len(user_prompt or ""),
        output_chars=len(raw_output or ""),
        usage=usage or {},
        confidence_bucket=_confidence_bucket(confidence),
        json_valid_first_pass=json_valid_first_pass,
        used_partial_recovery=used_partial_recovery,
        used_repair_pass=used_repair_pass,
        used_semantic_retry=used_semantic_retry,
        used_heuristic_fallback=used_heuristic_fallback,
        semantic_empty_detected=semantic_empty_detected,
    )


def _extract_item_samples(html_fragment: str) -> list[str]:
    item_samples = extract_html_section("ITEM_SAMPLES", html_fragment) or html_fragment or ""
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
        class_sets.append(stable_class_tokens(class_match.group(1)))
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
    classes = stable_class_tokens(class_name)
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
        normalized["page_number_selectors"] = [
            selector for selector in page_selectors if isinstance(selector, str) and selector.strip()
        ] if isinstance(page_selectors, list) else []
    confidence = normalized.get("confidence")
    if not isinstance(confidence, (int, float)):
        normalized["confidence"] = None

    reason = normalized.get("reason")
    if not isinstance(reason, str):
        normalized["reason"] = None

    return normalized


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
        response_format={"type": "json_object"},
        request_name="assist_json_repair",
    )
    if repair_response.error:
        return None, repair_response
    return _extract_json_payload(repair_response.content or ""), repair_response


def _run_llm_json_task(
    user_prompt: str,
    task_name: str,
    response_contract: str,
    system_suffix: str = "",
) -> AssistLlmResponse:
    quality = {
        "json_valid_first_pass": False,
        "used_partial_recovery": False,
        "used_repair_pass": False,
        "used_semantic_retry": False,
        "used_heuristic_fallback": False,
        "semantic_empty_detected": False,
    }

    def _return_with_quality(result: AssistLlmResponse, error_code: str | None = None) -> AssistLlmResponse:
        confidence = None
        if isinstance(result.result, dict):
            confidence = result.result.get("confidence")
        elif isinstance(result.confidence, (int, float)):
            confidence = result.confidence

        _emit_assist_prompt_quality_metric(
            task_name=task_name,
            success=result.success,
            user_prompt=user_prompt,
            raw_output=result.raw or "",
            model=result.model,
            usage=result.usage if isinstance(result.usage, dict) else None,
            confidence=confidence,
            error_code=error_code,
            json_valid_first_pass=quality["json_valid_first_pass"],
            used_partial_recovery=quality["used_partial_recovery"],
            used_repair_pass=quality["used_repair_pass"],
            used_semantic_retry=quality["used_semantic_retry"],
            used_heuristic_fallback=quality["used_heuristic_fallback"],
            semantic_empty_detected=quality["semantic_empty_detected"],
        )
        return result

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
            response_format={"type": "json_object"},
            request_name=f"assist_{task_name}",
        )
    except Exception as error:
        logger.exception("Assist task failed before LLM response", extra={"task_name": task_name})
        audit_event("assist_task_exception", task_name=task_name, error=str(error))
        return _return_with_quality(
            AssistLlmResponse(success=False, error=str(error), raw=""),
            error_code="assist_task_exception",
        )

    if response.error:
        audit_event("assist_task_llm_error", task_name=task_name, error=response.error)
        return _return_with_quality(
            AssistLlmResponse(success=False, error=response.error, raw=response.content, model=response.model, usage=response.usage),
            error_code="assist_task_llm_error",
        )

    parsed = _extract_json_payload(response.content or "")
    quality["json_valid_first_pass"] = parsed is not None
    if parsed is None:
        partial_recovery = recover_partial_pagination_json(response.content or "") if task_name == "analyze_pagination" else None
        if partial_recovery is not None:
            quality["used_partial_recovery"] = True
            parsed = partial_recovery
        else:
            quality["used_repair_pass"] = True
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
                return _return_with_quality(
                    AssistLlmResponse(
                        success=False,
                        error="Model output was not valid JSON; expected a single JSON object only",
                        raw=response.content,
                        model=repair_response.model or response.model,
                        usage=combined_usage,
                    ),
                    error_code="assist_task_invalid_json",
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
        quality["semantic_empty_detected"] = True
        heuristic_result = recover_pagination_from_summary(user_prompt)
        if heuristic_result is not None:
            normalized = heuristic_result
            quality["used_heuristic_fallback"] = True
            audit_event("assist_task_heuristic_fallback", task_name=task_name, recovered_result=normalized)
        else:
            quality["used_semantic_retry"] = True
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
                return _return_with_quality(
                    AssistLlmResponse(
                        success=False,
                        error="Pagination analysis returned a semantically empty result despite visible pagination evidence",
                        raw=response.content,
                        model=getattr(retry_response, "model", None) or response.model,
                        usage=response.usage,
                    ),
                    error_code="assist_task_semantic_empty",
                )

    audit_event(
        "assist_task_completed",
        task_name=task_name,
        result=normalized,
        model=response.model,
        usage=response.usage,
    )
    return _return_with_quality(
        AssistLlmResponse(
            success=True,
            result=normalized,
            confidence=float(normalized.get("confidence")) if isinstance(normalized.get("confidence"), (int, float)) else None,
            reason=normalized.get("reason") if isinstance(normalized.get("reason"), str) else None,
            raw=response.content,
            model=response.model,
            usage=response.usage,
        ),
    )


def infer_fields(request: AssistLlmRequest) -> AssistLlmResponse:
    # Truncate HTML to 6000 chars to prevent prompt token explosion on large pages.
    html = (request.html_fragment or "")[:6000]
    user_intent = request.user_intent if isinstance(request.user_intent, str) else None
    prompt = build_field_inference_prompt(html, user_intent=user_intent)
    return _run_llm_json_task(prompt, task_name="infer_fields", response_contract=FIELD_INFERENCE_RESPONSE_CONTRACT)


def optimize_selector(request: AssistLlmRequest) -> AssistLlmResponse:
    initial_selector = request.initial_selector or ""
    # Truncate HTML to 6000 chars to keep prompt within budget.
    html = (request.html_fragment or "")[:6000]
    prompt = build_selector_optimization_prompt(initial_selector, html)
    return _run_llm_json_task(prompt, task_name="optimize_selector", response_contract=SELECTOR_OPTIMIZATION_RESPONSE_CONTRACT)


def analyze_pagination(request: AssistLlmRequest) -> AssistLlmResponse:
    # Pass only HTML evidence in user prompt; move analysis rules to system suffix.
    evidence_prompt = build_pagination_evidence_prompt(request)
    return _run_llm_json_task(
        evidence_prompt,
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
        system_suffix=PAGINATION_ANALYSIS_SYSTEM_RULES,
    )
