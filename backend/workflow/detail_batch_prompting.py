"""Prompt and payload assembly for detail batch runner generation."""

from __future__ import annotations

import json
from typing import Any

from backend.workflow.detail_batch_codegen import generate_detail_batch_runner_skeleton
from backend.workflow.schemas import GenerateDetailBatchRunnerRequest


def build_detail_batch_generation_payload(request: GenerateDetailBatchRunnerRequest) -> dict[str, Any]:
    """Build the structured generation payload for detail batch runner scripts."""
    database = request.database
    detail_task = request.detail_task
    detail_cli = request.detail_cli
    execution_policy = request.execution_policy
    generation_policy = request.generation_policy
    return {
        "generation_target": "detail_batch_runner",
        "context_version": "1.0",
        "list_output_contract": {
            "database_type": database.database_type,
            "database_path": database.path,
            "table_name": database.list_table_name,
            "record_id_field": database.record_id_field,
            "detail_url_field": database.detail_url_field,
            "source_url_field": database.source_url_field,
            "title_field": database.title_field,
        },
        "detail_task_contract": {
            "table_name": detail_task.table_name,
            "status_values": detail_task.status_values,
            "max_attempts": detail_task.max_attempts,
        },
        "detail_cli_contract": {
            "executable": detail_cli.executable,
            "command_prefix": detail_cli.command_prefix or [],
            "subcommand": detail_cli.subcommand,
            "output_root": detail_cli.output_root,
            "stdout_format": detail_cli.stdout_format,
            "exit_code_policy": detail_cli.exit_code_policy,
        },
        "execution_constraints": {
            "language": generation_policy.language,
            "standalone_script": True,
            "concurrency_model": "thread_pool",
            "main_thread_claims_tasks": True,
            "workers_do_not_self_claim": True,
            "database_type": database.database_type,
            "do_not_reimplement_detail_extractor": True,
        },
        "operational_policy": {
            "default_concurrency": execution_policy.default_concurrency,
            "default_batch_size": execution_policy.default_batch_size,
            "max_attempts": detail_task.max_attempts,
            "subprocess_timeout_seconds": execution_policy.subprocess_timeout_seconds,
            "support_dry_run": execution_policy.support_dry_run,
            "support_limit": execution_policy.support_limit,
        },
        "script_skeleton_contract": {
            "required_classes": [
                "Config",
                "TaskRepository",
                "CliInvoker",
                "TaskRunner",
                "BatchExecutor",
            ],
            "required_functions": ["main"],
        },
        "output_requirement": {
            "artifact_type": "python_script",
            "return_only_script": True,
            "no_markdown_fences": True,
            "windows_compatible": True,
        },
    }


def build_detail_batch_runner_prompt(request: GenerateDetailBatchRunnerRequest) -> tuple[str, str]:
    """Build the final generation prompt and reference skeleton."""
    payload = build_detail_batch_generation_payload(request)
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    skeleton = generate_detail_batch_runner_skeleton(request)
    operator_notes = (request.prompt_override or "").strip()
    notes_section = ""
    if operator_notes:
        notes_section = (
            "## Operator Notes\n"
            f"{operator_notes}\n\n"
        )
    prompt = (
        "You are generating a standalone Python batch orchestration script.\n\n"
        "## Generation Payload\n"
        "```json\n"
        f"{payload_json}\n"
        "```\n\n"
        f"{notes_section}"
        "## Requirements\n"
        "- Preserve the approved task statuses and CLI-only execution boundary.\n"
        "- Keep the main thread responsible for claiming SQLite tasks.\n"
        "- Use ThreadPoolExecutor for worker concurrency.\n"
        "- Do not implement detail-page extraction logic inside the batch runner.\n"
        "- Return only the final complete Python script.\n\n"
        "## Deterministic Skeleton (Reference Base)\n"
        "Use the following script as the required base structure and improve it surgically.\n\n"
        "```python\n"
        f"{skeleton}\n"
        "```\n"
    )
    return prompt, skeleton
