"""Validation helpers for generated detail batch runner scripts."""

from __future__ import annotations

from workflow.schemas import (
    GenerateDetailBatchRunnerRequest,
    GeneratedScriptValidationCheck,
    GeneratedScriptValidationResult,
)


REQUIRED_CLASS_SNIPPETS = [
    "class Config:",
    "class TaskRepository:",
    "class CliInvoker:",
    "class TaskRunner:",
    "class BatchExecutor:",
]
REQUIRED_FUNCTION_SNIPPETS = [
    "def main() -> int:",
    'if __name__ == "__main__":',
]
REQUIRED_RUNTIME_SNIPPETS = [
    "ThreadPoolExecutor",
    "subprocess.run",
    "sqlite3",
]


def validate_generated_detail_batch_runner(
    script: str,
    request: GenerateDetailBatchRunnerRequest,
) -> GeneratedScriptValidationResult:
    """Run static validation against the approved skeleton and contract."""
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[GeneratedScriptValidationCheck] = []

    def add_check(name: str, passed: bool, detail: str | None = None) -> None:
        checks.append(GeneratedScriptValidationCheck(name=name, passed=passed, detail=detail))
        if not passed and detail:
            errors.append(detail)

    try:
        compile(script, "run_detail_batch.py", "exec")
        add_check("syntax", True)
    except Exception as exc:
        add_check("syntax", False, f"Generated detail batch runner has invalid Python syntax: {exc}")

    for snippet in REQUIRED_CLASS_SNIPPETS:
        add_check(
            f"required_class:{snippet}",
            snippet in script,
            None if snippet in script else f"Missing required class snippet: {snippet}",
        )
    for snippet in REQUIRED_FUNCTION_SNIPPETS:
        add_check(
            f"required_function:{snippet}",
            snippet in script,
            None if snippet in script else f"Missing required function snippet: {snippet}",
        )
    for snippet in REQUIRED_RUNTIME_SNIPPETS:
        add_check(
            f"required_runtime:{snippet}",
            snippet in script,
            None if snippet in script else f"Missing required runtime usage: {snippet}",
        )

    contract_snippets = [
        request.database.list_table_name,
        request.detail_task.table_name,
        request.database.record_id_field,
        request.database.detail_url_field,
    ]
    for snippet in contract_snippets:
        add_check(
            f"contract_reference:{snippet}",
            snippet in script,
            None if snippet in script else f"Generated script does not reference required contract value: {snippet}",
        )

    cli_reference_passed = request.detail_cli.executable in script or any(
        isinstance(item, str) and item and item in script
        for item in (request.detail_cli.command_prefix or [])
    )
    add_check(
        "contract_reference:detail_cli_invocation",
        cli_reference_passed,
        None if cli_reference_passed else "Generated script does not reference the configured detail CLI invocation contract.",
    )

    for status in request.detail_task.status_values:
        add_check(
            f"task_status:{status}",
            status in script,
            None if status in script else f"Generated script does not reference approved task status: {status}",
        )

    passed = not errors
    return GeneratedScriptValidationResult(
        passed=passed,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )
