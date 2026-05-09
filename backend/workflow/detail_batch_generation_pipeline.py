"""Generation pipeline for detail batch runner scripts."""

from __future__ import annotations

from typing import Any

from backend.core.app_logging import audit_event
from backend.llm import get_default_client
from backend.prompts.tasks.detail_batch_runner_system import DETAIL_BATCH_RUNNER_SYSTEM_PROMPT
from backend.workflow.detail_batch_prompting import build_detail_batch_runner_prompt
from backend.workflow.detail_batch_validation import validate_generated_detail_batch_runner
from backend.workflow.schemas import (
    GenerateDetailBatchRunnerRequest,
    GenerateDetailBatchRunnerResponse,
)


SUPPORTED_GENERATION_MODES = {"skeleton_enhancement", "llm_skeleton_enhancement"}


def _resolve_generation_mode(value: str | None) -> str:
    mode = str(value or "skeleton_enhancement").strip().lower()
    return mode if mode in SUPPORTED_GENERATION_MODES else "skeleton_enhancement"


def _append_trace(trace: list[dict[str, Any]], stage: str, status: str, **extra: Any) -> None:
    item: dict[str, Any] = {"stage": stage, "status": status}
    for key, value in extra.items():
        if value is not None:
            item[key] = value
    trace.append(item)


def generate_detail_batch_runner_pipeline(
    request: GenerateDetailBatchRunnerRequest,
) -> GenerateDetailBatchRunnerResponse:
    """Generate detail batch runner script with deterministic or LLM-enhanced mode."""
    generation_mode = _resolve_generation_mode(request.generation_policy.mode)
    audit_event(
        "workflow_generate_detail_batch_runner_started",
        generation_mode=generation_mode,
        database_path=request.database.path,
        list_table_name=request.database.list_table_name,
        task_table_name=request.detail_task.table_name,
    )
    generation_trace: list[dict[str, Any]] = []
    warnings: list[str] = []

    try:
        prompt, skeleton = build_detail_batch_runner_prompt(request)
        _append_trace(generation_trace, "prompt_build", "completed")
    except Exception as exc:
        audit_event(
            "workflow_generate_detail_batch_runner_failed",
            stage="prompt_build",
            generation_mode=generation_mode,
            error=str(exc),
        )
        return GenerateDetailBatchRunnerResponse(
            success=False,
            generation_mode=generation_mode,
            generation_trace=generation_trace,
            error=str(exc),
        )

    if generation_mode == "skeleton_enhancement":
        validation = validate_generated_detail_batch_runner(skeleton, request)
        audit_event(
            "workflow_generate_detail_batch_runner_completed",
            generation_mode=generation_mode,
            filename="run_detail_batch.py",
            warnings=validation.warnings,
            validation_passed=validation.passed,
        )
        return GenerateDetailBatchRunnerResponse(
            success=validation.passed,
            prompt=prompt,
            script=skeleton,
            filename="run_detail_batch.py",
            generation_mode=generation_mode,
            generation_trace=generation_trace,
            warnings=validation.warnings,
            validation=validation,
            error=None if validation.passed else "Generated detail batch runner failed validation.",
        )

    try:
        client = get_default_client()
        response = client.generate_with_system(
            system=DETAIL_BATCH_RUNNER_SYSTEM_PROMPT,
            user=prompt,
            request_name="workflow_generate_detail_batch_runner",
        )
        _append_trace(
            generation_trace,
            "llm_generation",
            "completed" if not response.error else "failed",
            model=response.model,
            finish_reason=response.finish_reason,
        )
        if response.error:
            audit_event(
                "workflow_generate_detail_batch_runner_failed",
                stage="llm_generation",
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                error=response.error,
            )
            return GenerateDetailBatchRunnerResponse(
                success=False,
                prompt=prompt,
                filename="run_detail_batch.py",
                model=response.model,
                usage=response.usage,
                generation_mode=generation_mode,
                generation_trace=generation_trace,
                warnings=warnings,
                error=response.error,
            )

        script = response.content or ""
        validation = validate_generated_detail_batch_runner(script, request)
        audit_event(
            "workflow_generate_detail_batch_runner_completed",
            generation_mode=generation_mode,
            filename="run_detail_batch.py",
            model=response.model,
            usage=response.usage,
            warnings=[*warnings, *validation.warnings],
            validation_passed=validation.passed,
        )
        return GenerateDetailBatchRunnerResponse(
            success=validation.passed,
            prompt=prompt,
            script=script,
            filename="run_detail_batch.py",
            model=response.model,
            usage=response.usage,
            generation_mode=generation_mode,
            generation_trace=generation_trace,
            warnings=[*warnings, *validation.warnings],
            validation=validation,
            error=None if validation.passed else "Generated detail batch runner failed validation.",
        )
    except Exception as exc:
        audit_event(
            "workflow_generate_detail_batch_runner_failed",
            stage="unexpected_exception",
            generation_mode=generation_mode,
            generation_trace=generation_trace,
            error=str(exc),
        )
        return GenerateDetailBatchRunnerResponse(
            success=False,
            prompt=prompt,
            filename="run_detail_batch.py",
            generation_mode=generation_mode,
            generation_trace=generation_trace,
            warnings=warnings,
            error=str(exc),
        )
