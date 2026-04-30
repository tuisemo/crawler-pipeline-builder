"""LLM-backed workflow crawler generation pipeline."""

from __future__ import annotations

import json
import re
from typing import Any

from backend.core.app_logging import audit_event
from backend.core.settings import get_settings
from backend.llm import CRAWLER_SYSTEM_PROMPT, get_default_client
from backend.prompts.tasks.crawler_system import (
    CRAWLER_REVIEW_SYSTEM_PROMPT,
    CRAWLER_REVISION_SYSTEM_PROMPT,
)

from backend.workflow.schemas import GenerateCrawlerRequest, GenerateCrawlerResponse, NodeData, WorkflowGraph, WorkflowNode
from .prompting import (
    PromptGenerationError,
    _build_review_prompt,
    _build_revision_prompt,
    _build_skeleton_enhancement_prompt,
)
from .script_sandbox import run_generated_script_sandbox


_settings = get_settings()
SCRIPT_GENERATION_MAX_TOKENS = _settings.script_generation_max_tokens
SCRIPT_REVIEW_MAX_TOKENS = _settings.script_review_max_tokens
SCRIPT_SANDBOX_ENABLED = _settings.script_sandbox_enabled
SCRIPT_SANDBOX_TIMEOUT_SECONDS = _settings.script_sandbox_timeout_seconds
SUPPORTED_GENERATION_MODES = {"lite", "pro"}
DEPRECATED_NODE_DATA_KEYS = {"max_steps", "max_items"}


def _extract_json_object(content: str) -> dict:
    raw = (content or "").strip()
    if not raw:
        raise ValueError("empty response")

    # Try to find JSON block in markdown fences
    fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced_match:
        try:
            return json.loads(fenced_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON object
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            # Try to parse the largest possible JSON object found
            candidate = raw[start:end + 1]
            return json.loads(candidate)
    except Exception:
        pass

    raise ValueError("response did not contain a valid JSON object")


def _review_requires_revision(review_summary: dict) -> bool:
    if review_summary.get("approve") is False:
        return True
    issues = review_summary.get("issues")
    if isinstance(issues, list) and issues:
        return True
    revision_instructions = review_summary.get("revision_instructions")
    if isinstance(revision_instructions, list) and revision_instructions:
        return True
    return False


def _merge_usage(*usages: dict | None) -> dict[str, int] | None:
    totals: dict[str, int] = {}
    for usage in usages:
        if not isinstance(usage, dict):
            continue
        for key, value in usage.items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _resolve_generation_mode(value: str | None) -> str:
    mode = str(value or "lite").strip().lower()
    return mode if mode in SUPPORTED_GENERATION_MODES else "lite"


def _append_trace(trace: list[dict[str, Any]], stage: str, status: str, **extra: Any) -> None:
    item: dict[str, Any] = {"stage": stage, "status": status}
    for key, value in extra.items():
        if value is not None:
            item[key] = value
    trace.append(item)


def _graph_summary(graph: WorkflowGraph) -> dict[str, Any]:
    return {
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "node_types": [node.type for node in graph.nodes],
    }


def _sanitize_graph(graph: WorkflowGraph) -> WorkflowGraph:
    return WorkflowGraph(
        nodes=[
            WorkflowNode(
                id=node.id,
                type=node.type,
                data=NodeData.model_validate({
                    key: value
                    for key, value in node.data.model_dump().items()
                    if key not in DEPRECATED_NODE_DATA_KEYS
                }),
            )
            for node in graph.nodes
        ],
        edges=list(graph.edges),
    )


def _capture_length_warning(response, stage: str) -> str | None:
    if getattr(response, "finish_reason", None) == "length":
        return f"{stage} reached the model token limit; the returned content may be truncated."
    return None


def _with_optional_max_tokens(max_tokens: int | None) -> dict[str, int]:
    return {"max_tokens": max_tokens} if isinstance(max_tokens, int) and max_tokens > 0 else {}


def _build_empty_script_error(stage: str, finish_reason: str | None) -> str:
    if finish_reason == "length":
        return f"{stage} returned empty content after hitting the model token limit."
    return f"{stage} returned empty content."


def _detect_script_compatibility_issues(script: str) -> list[str]:
    if not isinstance(script, str) or not script.strip():
        return []

    issues: list[str] = []
    patterns = {
        r"\bitem\.locator\s*\(": "Generated script uses `item.locator(...)`; `item` is typically an ElementHandle in this platform.",
        r"\bfirst\.locator\s*\(": "Generated script uses `first.locator(...)`; `first` is typically an ElementHandle in this platform.",
        r"\belement\.locator\s*\(": "Generated script uses `element.locator(...)`; ElementHandle does not expose `.locator(...)` in Playwright Python sync API.",
        r"\bel\.locator\s*\(": "Generated script uses `el.locator(...)`; ElementHandle does not expose `.locator(...)` in Playwright Python sync API.",
        r"\bsub_el\.locator\s*\(": "Generated script uses `sub_el.locator(...)`; ElementHandle does not expose `.locator(...)` in Playwright Python sync API.",
        r"\bnext_button\.locator\s*\(": "Generated script uses `next_button.locator(...)`; `next_button` is expected to be an ElementHandle in this platform.",
    }
    for pattern, message in patterns.items():
        if re.search(pattern, script):
            issues.append(message)
    return issues


def _should_run_sandbox(request: GenerateCrawlerRequest) -> bool:
    if request.run_sandbox is None:
        return False
    return SCRIPT_SANDBOX_ENABLED and bool(request.run_sandbox)


def _resolve_sandbox_timeout(request: GenerateCrawlerRequest) -> int:
    timeout = request.sandbox_timeout_seconds
    if isinstance(timeout, int) and timeout > 0:
        return timeout
    return SCRIPT_SANDBOX_TIMEOUT_SECONDS


def _run_final_script_sandbox(
    *,
    request: GenerateCrawlerRequest,
    script: str,
    filename: str,
    generation_mode: str,
    model_name: str,
    generation_trace: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any] | None:
    if not _should_run_sandbox(request):
        return None

    timeout = _resolve_sandbox_timeout(request)
    sandbox_result = run_generated_script_sandbox(
        script,
        filename=filename,
        timeout_seconds=timeout,
        metadata={
            "generation_mode": generation_mode,
            "model": model_name,
        },
    ).to_dict()
    _append_trace(
        generation_trace,
        "script_sandbox",
        "completed" if sandbox_result.get("success") else "failed",
        run_id=sandbox_result.get("run_id"),
        log_path=sandbox_result.get("log_path"),
        exit_code=sandbox_result.get("exit_code"),
        timed_out=sandbox_result.get("timed_out"),
    )
    if not sandbox_result.get("success"):
        warnings.append(
            f"Script sandbox failed; see execution log: {sandbox_result.get('log_path')}"
        )
    return sandbox_result


def generate_crawler(request: GenerateCrawlerRequest) -> GenerateCrawlerResponse:
    """Generate a Playwright crawler script from a DSL workflow graph."""
    generation_mode = _resolve_generation_mode(request.generation_mode)
    sanitized_graph = _sanitize_graph(request.graph)
    audit_event(
        "workflow_generate_crawler_started",
        generation_mode=generation_mode,
        has_prompt_override=bool((request.prompt_override or "").strip()),
        graph_summary=_graph_summary(sanitized_graph),
    )
    try:
        final_prompt, editable_prompt, plan_dict, _skeleton_script = _build_skeleton_enhancement_prompt(
            sanitized_graph,
            request.prompt_override,
        )
    except PromptGenerationError as e:
        audit_event(
            "workflow_generate_crawler_failed",
            stage="prompt_build",
            generation_mode=generation_mode,
            error=str(e),
        )
        return GenerateCrawlerResponse(success=False, error=str(e))

    try:
        client = get_default_client()
        generation_trace: list[dict[str, Any]] = []
        warnings: list[str] = []
        draft_response = client.generate_with_system(
            system=CRAWLER_SYSTEM_PROMPT,
            user=final_prompt,
            request_name="workflow_generate_crawler_draft",
            **_with_optional_max_tokens(SCRIPT_GENERATION_MAX_TOKENS),
        )
        _append_trace(
            generation_trace,
            "draft_generation",
            "completed" if not draft_response.error else "failed",
            model=draft_response.model,
            finish_reason=draft_response.finish_reason,
        )
        audit_event(
            "workflow_generate_crawler_stage",
            stage="draft_generation",
            generation_mode=generation_mode,
            status="completed" if not draft_response.error else "failed",
            model=draft_response.model,
            finish_reason=draft_response.finish_reason,
            usage=draft_response.usage,
        )

        if draft_response.error:
            audit_event(
                "workflow_generate_crawler_failed",
                stage="draft_generation",
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                error=draft_response.error,
            )
            return GenerateCrawlerResponse(
                success=False,
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                error=draft_response.error,
            )

        draft_script = draft_response.content
        length_warning = _capture_length_warning(draft_response, "Draft generation")
        if length_warning:
            warnings.append(length_warning)
        if not isinstance(draft_script, str) or not draft_script.strip():
            error_message = _build_empty_script_error("Draft generation", draft_response.finish_reason)
            audit_event(
                "workflow_generate_crawler_failed",
                stage="draft_generation_empty",
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                error=error_message,
            )
            return GenerateCrawlerResponse(
                success=False,
                prompt=final_prompt,
                editable_prompt=editable_prompt,
                script=draft_script,
                model=draft_response.model,
                usage=draft_response.usage,
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                error=error_message,
            )
        draft_compatibility_issues = _detect_script_compatibility_issues(draft_script)
        if draft_compatibility_issues:
            error_message = "Draft generation produced Playwright-incompatible ElementHandle locator usage."
            audit_event(
                "workflow_generate_crawler_failed",
                stage="draft_generation_compatibility",
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                issues=draft_compatibility_issues,
                error=error_message,
            )
            return GenerateCrawlerResponse(
                success=False,
                prompt=final_prompt,
                editable_prompt=editable_prompt,
                script=draft_script,
                model=draft_response.model,
                usage=draft_response.usage,
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=[*warnings, *draft_compatibility_issues],
                error=error_message,
            )

        if generation_mode == "lite":
            filename = "crawler.py"
            filename_match = re.search(r"crawler_\w+\.py", draft_script)
            if filename_match:
                filename = filename_match.group(0)
            sandbox_result = _run_final_script_sandbox(
                request=request,
                script=draft_script,
                filename=filename,
                generation_mode=generation_mode,
                model_name=draft_response.model,
                generation_trace=generation_trace,
                warnings=warnings,
            )
            audit_event(
                "workflow_generate_crawler_completed",
                generation_mode=generation_mode,
                filename=filename,
                model=draft_response.model,
                usage=draft_response.usage,
                warnings=warnings,
                generation_trace=generation_trace,
                sandbox_result=sandbox_result,
            )
            return GenerateCrawlerResponse(
                success=True,
                prompt=final_prompt,
                editable_prompt=editable_prompt,
                script=draft_script,
                filename=filename,
                model=draft_response.model,
                usage=draft_response.usage,
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                sandbox_result=sandbox_result,
                warnings=warnings,
            )

        review_prompt = _build_review_prompt(plan_dict, editable_prompt, draft_script)
        review_response = client.generate_with_system(
            system=CRAWLER_REVIEW_SYSTEM_PROMPT,
            user=review_prompt,
            request_name="workflow_generate_crawler_review",
            **_with_optional_max_tokens(SCRIPT_REVIEW_MAX_TOKENS),
        )
        _append_trace(
            generation_trace,
            "script_review",
            "completed" if not review_response.error else "failed",
            model=review_response.model,
            finish_reason=review_response.finish_reason,
        )
        audit_event(
            "workflow_generate_crawler_stage",
            stage="script_review",
            generation_mode=generation_mode,
            status="completed" if not review_response.error else "failed",
            model=review_response.model,
            finish_reason=review_response.finish_reason,
            usage=review_response.usage,
        )
        if review_response.error:
            audit_event(
                "workflow_generate_crawler_failed",
                stage="script_review",
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                error=review_response.error,
            )
            return GenerateCrawlerResponse(
                success=False,
                prompt=final_prompt,
                editable_prompt=editable_prompt,
                script=draft_script,
                model=draft_response.model,
                usage=_merge_usage(draft_response.usage, review_response.usage),
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                error=review_response.error,
            )

        review_length_warning = _capture_length_warning(review_response, "Script review")
        if review_length_warning:
            warnings.append(review_length_warning)

        try:
            review_summary = _extract_json_object(review_response.content)
        except Exception as e:
            audit_event(
                "workflow_generate_crawler_failed",
                stage="script_review_parse",
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                error=f"Script review returned invalid JSON: {e}",
            )
            return GenerateCrawlerResponse(
                success=False,
                prompt=final_prompt,
                editable_prompt=editable_prompt,
                script=draft_script,
                model=draft_response.model,
                usage=_merge_usage(draft_response.usage, review_response.usage),
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                error=f"Script review returned invalid JSON: {e}",
            )

        filename = "crawler.py"
        final_script = draft_script
        model_name = draft_response.model
        total_usage = _merge_usage(draft_response.usage, review_response.usage)

        if _review_requires_revision(review_summary):
            revision_prompt = _build_revision_prompt(plan_dict, editable_prompt, draft_script, review_summary)
            revision_response = client.generate_with_system(
                system=CRAWLER_REVISION_SYSTEM_PROMPT,
                user=revision_prompt,
                request_name="workflow_generate_crawler_revision",
                **_with_optional_max_tokens(SCRIPT_GENERATION_MAX_TOKENS),
            )
            _append_trace(
                generation_trace,
                "revision_enhancement",
                "completed" if not revision_response.error else "failed",
                model=revision_response.model,
                finish_reason=revision_response.finish_reason,
            )
            audit_event(
                "workflow_generate_crawler_stage",
                stage="revision_enhancement",
                generation_mode=generation_mode,
                status="completed" if not revision_response.error else "failed",
                model=revision_response.model,
                finish_reason=revision_response.finish_reason,
                usage=revision_response.usage,
            )
            if revision_response.error:
                audit_event(
                    "workflow_generate_crawler_failed",
                    stage="revision_enhancement",
                    generation_mode=generation_mode,
                    generation_trace=generation_trace,
                    warnings=warnings,
                    review_summary=review_summary,
                    error=revision_response.error,
                )
                return GenerateCrawlerResponse(
                    success=False,
                    prompt=final_prompt,
                    editable_prompt=editable_prompt,
                    script=draft_script,
                    model=draft_response.model,
                    usage=_merge_usage(draft_response.usage, review_response.usage, revision_response.usage),
                    generation_mode=generation_mode,
                    generation_trace=generation_trace,
                    warnings=warnings,
                    review_summary=review_summary,
                    error=revision_response.error,
                )
            final_script = revision_response.content
            model_name = revision_response.model or model_name
            total_usage = _merge_usage(draft_response.usage, review_response.usage, revision_response.usage)
            revision_length_warning = _capture_length_warning(revision_response, "Revision enhancement")
            if revision_length_warning:
                warnings.append(revision_length_warning)
            if not isinstance(final_script, str) or not final_script.strip():
                error_message = _build_empty_script_error("Revision enhancement", revision_response.finish_reason)
                audit_event(
                    "workflow_generate_crawler_failed",
                    stage="revision_enhancement_empty",
                    generation_mode=generation_mode,
                    generation_trace=generation_trace,
                    warnings=warnings,
                    review_summary=review_summary,
                    error=error_message,
                )
                return GenerateCrawlerResponse(
                    success=False,
                    prompt=final_prompt,
                    editable_prompt=editable_prompt,
                    script=final_script,
                    model=model_name,
                    usage=total_usage,
                    generation_mode=generation_mode,
                    generation_trace=generation_trace,
                    warnings=warnings,
                    review_summary=review_summary,
                    error=error_message,
                )
            final_compatibility_issues = _detect_script_compatibility_issues(final_script)
            if final_compatibility_issues:
                error_message = "Revision enhancement produced Playwright-incompatible ElementHandle locator usage."
                audit_event(
                    "workflow_generate_crawler_failed",
                    stage="revision_enhancement_compatibility",
                    generation_mode=generation_mode,
                    generation_trace=generation_trace,
                    warnings=warnings,
                    review_summary=review_summary,
                    issues=final_compatibility_issues,
                    error=error_message,
                )
                return GenerateCrawlerResponse(
                    success=False,
                    prompt=final_prompt,
                    editable_prompt=editable_prompt,
                    script=final_script,
                    model=model_name,
                    usage=total_usage,
                    generation_mode=generation_mode,
                    generation_trace=generation_trace,
                    warnings=[*warnings, *final_compatibility_issues],
                    review_summary=review_summary,
                    error=error_message,
                )
                return GenerateCrawlerResponse(
                    success=False,
                    prompt=final_prompt,
                    editable_prompt=editable_prompt,
                    script=final_script,
                    model=model_name,
                    usage=total_usage,
                    generation_mode=generation_mode,
                    generation_trace=generation_trace,
                    warnings=warnings,
                    review_summary=review_summary,
                    error=error_message,
                )

        filename_match = re.search(r"crawler_\w+\.py", final_script)
        if filename_match:
            filename = filename_match.group(0)

        sandbox_result = _run_final_script_sandbox(
            request=request,
            script=final_script,
            filename=filename,
            generation_mode=generation_mode,
            model_name=model_name,
            generation_trace=generation_trace,
            warnings=warnings,
        )

        audit_event(
            "workflow_generate_crawler_completed",
            generation_mode=generation_mode,
            filename=filename,
            model=model_name,
            usage=total_usage,
            warnings=warnings,
            generation_trace=generation_trace,
            review_summary=review_summary,
            sandbox_result=sandbox_result,
        )
        return GenerateCrawlerResponse(
            success=True,
            prompt=final_prompt,
            editable_prompt=editable_prompt,
            script=final_script,
            filename=filename,
            model=model_name,
            usage=total_usage,
            generation_mode=generation_mode,
            generation_trace=generation_trace,
            sandbox_result=sandbox_result,
            warnings=warnings,
            review_summary=review_summary,
        )
    except Exception as e:
        audit_event(
            "workflow_generate_crawler_failed",
            stage="unexpected_exception",
            generation_mode=generation_mode,
            error=str(e),
        )
        return GenerateCrawlerResponse(success=False, error=str(e))
