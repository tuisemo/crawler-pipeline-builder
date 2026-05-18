"""Deterministic code generator for detail batch runner scripts."""

from __future__ import annotations

import json
import textwrap

from workflow.schemas import GenerateDetailBatchRunnerRequest


def _json_literal(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def generate_detail_batch_runner_skeleton(request: GenerateDetailBatchRunnerRequest) -> str:
    """Generate a standalone Python batch orchestration script."""
    db = request.database
    task = request.detail_task
    cli = request.detail_cli
    policy = request.execution_policy

    status_values_literal = _json_literal(task.status_values)
    script = f"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DATABASE_TYPE = {db.database_type!r}
DATABASE_PATH = {db.path!r}
LIST_TABLE_NAME = {db.list_table_name!r}
TASK_TABLE_NAME = {task.table_name!r}
RECORD_ID_FIELD = {db.record_id_field!r}
DETAIL_URL_FIELD = {db.detail_url_field!r}
SOURCE_URL_FIELD = {db.source_url_field!r}
TITLE_FIELD = {db.title_field!r}
DETAIL_CLI_EXECUTABLE = {cli.executable!r}
DETAIL_CLI_COMMAND_PREFIX = {_json_literal(cli.command_prefix or [])}
DETAIL_CLI_SUBCOMMAND = {cli.subcommand!r}
DETAIL_OUTPUT_ROOT = {cli.output_root!r}
DETAIL_STDOUT_FORMAT = {cli.stdout_format!r}
EXIT_CODE_POLICY = {cli.exit_code_policy!r}
DEFAULT_CONCURRENCY = {policy.default_concurrency}
DEFAULT_BATCH_SIZE = {policy.default_batch_size}
DEFAULT_MAX_ATTEMPTS = {task.max_attempts}
DEFAULT_SUBPROCESS_TIMEOUT_SECONDS = {policy.subprocess_timeout_seconds}
SUPPORTED_TASK_STATUSES = {status_values_literal}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_valid_detail_url(url: str) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in {{"http", "https"}} and bool(parsed.netloc)


def build_run_log_path(output_root: Path, batch_run_id: str) -> Path:
    logs_dir = output_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"detail-batch-run-{{batch_run_id}}.log"


def configure_logging(log_path: Path, log_level: str) -> logging.Logger:
    logger = logging.getLogger("detail_batch_runner")
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, str(log_level).upper(), logging.INFO))
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


@dataclass
class TaskRow:
    task_id: str
    record_id: str
    detail_url: str
    attempt_count: int
    status: str
    source_url: str | None = None
    title: str | None = None


@dataclass
class TaskExecutionResult:
    task_id: str
    record_id: str
    attempt_count: int
    status: str
    error_code: str | None
    error_message: str | None
    summary: dict[str, Any]
    started_at: str
    completed_at: str


@dataclass
class RunSummary:
    batch_run_id: str
    synced_count: int
    selected_count: int
    succeeded_count: int
    retryable_failed_count: int
    terminal_failed_count: int
    skipped_count: int
    duration_seconds: float


@dataclass
class Config:
    database_path: Path
    list_table_name: str
    task_table_name: str
    record_id_field: str
    detail_url_field: str
    source_url_field: str | None
    title_field: str | None
    detail_cli_executable: str
    detail_cli_command_prefix: list[str]
    detail_cli_subcommand: str
    output_root: Path
    concurrency: int
    batch_size: int
    max_attempts: int
    subprocess_timeout_seconds: int
    log_level: str
    run_log_path: Path
    dry_run: bool
    limit: int | None
    batch_run_id: str

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Config":
        output_root = Path(args.output_root).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        batch_run_id = uuid.uuid4().hex
        run_log_path = build_run_log_path(output_root, batch_run_id)
        return cls(
            database_path=Path(args.db).resolve(),
            list_table_name=args.list_table,
            task_table_name=args.task_table,
            record_id_field=args.record_id_field,
            detail_url_field=args.detail_url_field,
            source_url_field=args.source_url_field,
            title_field=args.title_field,
            detail_cli_executable=args.cli_executable,
            detail_cli_command_prefix=list(args.cli_command_prefix or []),
            detail_cli_subcommand=args.cli_subcommand,
            output_root=output_root,
            concurrency=max(1, args.concurrency),
            batch_size=max(1, args.batch_size),
            max_attempts=max(1, args.max_attempts),
            subprocess_timeout_seconds=max(1, args.timeout),
            log_level=args.log_level,
            run_log_path=run_log_path,
            dry_run=bool(args.dry_run),
            limit=args.limit if args.limit and args.limit > 0 else None,
            batch_run_id=batch_run_id,
        )


class TaskRepository:
    def __init__(self, config: Config):
        self.config = config

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.config.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                f'''
                CREATE TABLE IF NOT EXISTS "{{self.config.task_table_name}}" (
                    task_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    detail_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    priority INTEGER NOT NULL DEFAULT 0,
                    batch_run_id TEXT,
                    worker_id TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    last_heartbeat_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    result_summary_path TEXT,
                    content_markdown_path TEXT,
                    pdf_snapshot_path TEXT,
                    attachments_dir TEXT,
                    task_dir TEXT,
                    detail_cli_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(record_id, detail_url)
                )
                '''
            )
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{{self.config.task_table_name}}_status ON "{{self.config.task_table_name}}"(status)'
            )
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{{self.config.task_table_name}}_record_id ON "{{self.config.task_table_name}}"(record_id)'
            )
            conn.commit()

    def sync_tasks_from_list_results(self) -> int:
        source_fields = []
        if self.config.source_url_field:
            source_fields.append(self.config.source_url_field)
        if self.config.title_field:
            source_fields.append(self.config.title_field)
        select_fields = ", ".join(
            ['"' + self.config.record_id_field + '"', '"' + self.config.detail_url_field + '"']
            + ['"' + field + '"' for field in source_fields]
        )

        synced_count = 0
        with self.connect() as conn:
            rows = conn.execute(
                f'SELECT {{select_fields}} FROM "{{self.config.list_table_name}}"'
            ).fetchall()
            for row in rows:
                detail_url = str(row[self.config.detail_url_field] or "").strip()
                if not is_valid_detail_url(detail_url):
                    continue
                record_id = str(row[self.config.record_id_field])
                now = utc_now_iso()
                task_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{{record_id}}|{{detail_url}}").hex
                cursor = conn.execute(
                    f'''
                    INSERT OR IGNORE INTO "{{self.config.task_table_name}}"
                    (task_id, record_id, detail_url, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''',
                    (task_id, record_id, detail_url, "pending", now, now),
                )
                if cursor.rowcount:
                    synced_count += 1
            conn.commit()
        return synced_count

    def fetch_runnable_tasks(self) -> list[TaskRow]:
        query = (
            f'''
            SELECT task_id, record_id, detail_url, attempt_count, status
            FROM "{{self.config.task_table_name}}"
            WHERE status = 'pending'
               OR (status = 'failed_retryable' AND attempt_count < ?)
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
            '''
        )
        params = (self.config.max_attempts, self.config.limit or self.config.batch_size)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            TaskRow(
                task_id=str(row["task_id"]),
                record_id=str(row["record_id"]),
                detail_url=str(row["detail_url"]),
                attempt_count=int(row["attempt_count"]),
                status=str(row["status"]),
            )
            for row in rows
        ]

    def claim_tasks(self, tasks: list[TaskRow]) -> list[TaskRow]:
        if not tasks:
            return []
        claimed: list[TaskRow] = []
        now = utc_now_iso()
        with self.connect() as conn:
            for task in tasks:
                cursor = conn.execute(
                    f'''
                    UPDATE "{{self.config.task_table_name}}"
                    SET status = 'running',
                        attempt_count = attempt_count + 1,
                        batch_run_id = ?,
                        started_at = ?,
                        updated_at = ?
                    WHERE task_id = ?
                      AND (status = 'pending' OR (status = 'failed_retryable' AND attempt_count < ?))
                    ''',
                    (self.config.batch_run_id, now, now, task.task_id, self.config.max_attempts),
                )
                if cursor.rowcount:
                    claimed.append(
                        TaskRow(
                            task_id=task.task_id,
                            record_id=task.record_id,
                            detail_url=task.detail_url,
                            attempt_count=task.attempt_count + 1,
                            status="running",
                        )
                    )
            conn.commit()
        return claimed

    def mark_task_succeeded(self, result: TaskExecutionResult) -> None:
        summary = result.summary
        with self.connect() as conn:
            conn.execute(
                f'''
                UPDATE "{{self.config.task_table_name}}"
                SET status = 'succeeded',
                    completed_at = ?,
                    updated_at = ?,
                    error_code = NULL,
                    error_message = NULL,
                    result_summary_path = ?,
                    content_markdown_path = ?,
                    pdf_snapshot_path = ?,
                    attachments_dir = ?,
                    task_dir = ?,
                    detail_cli_version = ?
                WHERE task_id = ?
                ''',
                (
                    result.completed_at,
                    result.completed_at,
                    summary.get("result_summary_path"),
                    summary.get("content_markdown_path"),
                    summary.get("pdf_snapshot_path"),
                    summary.get("attachments_dir"),
                    summary.get("task_dir"),
                    summary.get("detail_cli_version"),
                    result.task_id,
                ),
            )
            conn.commit()

    def mark_task_failed(self, result: TaskExecutionResult) -> None:
        with self.connect() as conn:
            conn.execute(
                f'''
                UPDATE "{{self.config.task_table_name}}"
                SET status = ?,
                    completed_at = ?,
                    updated_at = ?,
                    error_code = ?,
                    error_message = ?
                WHERE task_id = ?
                ''',
                (
                    result.status,
                    result.completed_at,
                    result.completed_at,
                    result.error_code,
                    result.error_message,
                    result.task_id,
                ),
            )
            conn.commit()

    def mark_task_skipped(self, task_id: str, error_message: str) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                f'''
                UPDATE "{{self.config.task_table_name}}"
                SET status = 'skipped',
                    completed_at = ?,
                    updated_at = ?,
                    error_code = 'skipped',
                    error_message = ?
                WHERE task_id = ?
                ''',
                (now, now, error_message, task_id),
            )
            conn.commit()

    def count_tasks_by_status(self) -> dict[str, int]:
        counts = {{status: 0 for status in SUPPORTED_TASK_STATUSES}}
        with self.connect() as conn:
            rows = conn.execute(
                f'SELECT status, COUNT(*) AS count FROM "{{self.config.task_table_name}}" GROUP BY status'
            ).fetchall()
        for row in rows:
            status = str(row["status"])
            counts[status] = int(row["count"])
        return counts


class CliInvoker:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def build_command(self, task: TaskRow) -> list[str]:
        prefix = list(self.config.detail_cli_command_prefix)
        if not prefix:
            prefix = [self.config.detail_cli_executable]
        command = [
            *prefix,
            self.config.detail_cli_subcommand,
            "--url",
            task.detail_url,
            "--task-id",
            task.task_id,
            "--output-root",
            str(self.config.output_root),
            "--format",
            DETAIL_STDOUT_FORMAT,
            "--timeout",
            str(self.config.subprocess_timeout_seconds),
            "--save-markdown",
        ]
        return command

    def parse_summary(self, stdout: str) -> dict[str, Any] | None:
        raw = (stdout or "").strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def classify_subprocess_failure(
        self,
        *,
        returncode: int | None,
        stderr: str,
        timed_out: bool,
        error_code: str | None,
    ) -> tuple[str, str]:
        lowered_stderr = (stderr or "").lower()
        if timed_out or error_code == "timeout":
            return "failed_retryable", "detail extractor timed out"
        if "network" in lowered_stderr or "connection" in lowered_stderr:
            return "failed_retryable", stderr or "transient network failure"
        if returncode in {{2}} or error_code in {{"invalid_url", "invalid_args"}}:
            return "failed_terminal", stderr or "invalid detail extractor input"
        return "failed_retryable", stderr or "detail extractor subprocess failed"

    def invoke(self, task: TaskRow) -> TaskExecutionResult:
        started_at = utc_now_iso()
        command = self.build_command(task)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.config.subprocess_timeout_seconds,
                check=False,
            )
            summary = self.parse_summary(completed.stdout)
            completed_at = utc_now_iso()
            if completed.returncode == 0 and isinstance(summary, dict):
                return TaskExecutionResult(
                    task_id=task.task_id,
                    record_id=task.record_id,
                    attempt_count=task.attempt_count,
                    status="succeeded",
                    error_code=None,
                    error_message=None,
                    summary=summary,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            error_code = summary.get("error_code") if isinstance(summary, dict) else None
            status, error_message = self.classify_subprocess_failure(
                returncode=completed.returncode,
                stderr=completed.stderr or "",
                timed_out=False,
                error_code=error_code,
            )
            return TaskExecutionResult(
                task_id=task.task_id,
                record_id=task.record_id,
                attempt_count=task.attempt_count,
                status=status,
                error_code=error_code or "subprocess_failure",
                error_message=error_message,
                summary=summary or {{}},
                started_at=started_at,
                completed_at=completed_at,
            )
        except subprocess.TimeoutExpired as exc:
            completed_at = utc_now_iso()
            return TaskExecutionResult(
                task_id=task.task_id,
                record_id=task.record_id,
                attempt_count=task.attempt_count,
                status="failed_retryable",
                error_code="timeout",
                error_message=f"detail extractor timed out after {{self.config.subprocess_timeout_seconds}} seconds",
                summary={{}},
                started_at=started_at,
                completed_at=completed_at,
            )
        except Exception as exc:
            completed_at = utc_now_iso()
            return TaskExecutionResult(
                task_id=task.task_id,
                record_id=task.record_id,
                attempt_count=task.attempt_count,
                status="failed_terminal",
                error_code="invocation_error",
                error_message=str(exc),
                summary={{}},
                started_at=started_at,
                completed_at=completed_at,
            )


class TaskRunner:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.invoker = CliInvoker(config, logger)

    def run_task(self, task: TaskRow) -> TaskExecutionResult:
        self.logger.info(
            "Running detail task: task_id=%s record_id=%s detail_url=%s attempt_count=%s",
            task.task_id,
            task.record_id,
            task.detail_url,
            task.attempt_count,
        )
        return self.invoker.invoke(task)


class BatchExecutor:
    def __init__(self, config: Config):
        self.config = config
        self.logger = configure_logging(config.run_log_path, config.log_level)
        self.repo = TaskRepository(config)
        self.runner = TaskRunner(config, self.logger)

    def _persist_worker_result(self, result: TaskExecutionResult) -> None:
        if result.status == "succeeded":
            self.repo.mark_task_succeeded(result)
        else:
            if result.status == "failed_retryable" and result.attempt_count >= self.config.max_attempts:
                result.status = "failed_terminal"
            self.repo.mark_task_failed(result)

    def _run_one_batch(self, tasks: list[TaskRow]) -> list[TaskExecutionResult]:
        results: list[TaskExecutionResult] = []
        with ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            futures = [executor.submit(self.runner.run_task, task) for task in tasks]
            for future in as_completed(futures):
                results.append(future.result())
        return results

    def _log_run_summary(self, summary: RunSummary) -> None:
        self.logger.info(
            "Detail batch run completed: batch_run_id=%s synced=%s selected=%s succeeded=%s retryable_failed=%s terminal_failed=%s skipped=%s duration_seconds=%.2f",
            summary.batch_run_id,
            summary.synced_count,
            summary.selected_count,
            summary.succeeded_count,
            summary.retryable_failed_count,
            summary.terminal_failed_count,
            summary.skipped_count,
            summary.duration_seconds,
        )

    def run(self) -> RunSummary:
        start_time = time.perf_counter()
        self.logger.info("Detail batch runner started: database=%s", self.config.database_path)
        self.repo.ensure_schema()
        synced_count = self.repo.sync_tasks_from_list_results()
        selected_count = 0

        while True:
            runnable = self.repo.fetch_runnable_tasks()
            if not runnable:
                break
            claimed = self.repo.claim_tasks(runnable[:self.config.batch_size])
            if not claimed:
                break
            selected_count += len(claimed)
            self.logger.info("Claimed %s detail tasks for batch_run_id=%s", len(claimed), self.config.batch_run_id)
            if self.config.dry_run:
                break
            results = self._run_one_batch(claimed)
            for result in results:
                self._persist_worker_result(result)

        counts = self.repo.count_tasks_by_status()
        summary = RunSummary(
            batch_run_id=self.config.batch_run_id,
            synced_count=synced_count,
            selected_count=selected_count,
            succeeded_count=counts.get("succeeded", 0),
            retryable_failed_count=counts.get("failed_retryable", 0),
            terminal_failed_count=counts.get("failed_terminal", 0),
            skipped_count=counts.get("skipped", 0),
            duration_seconds=time.perf_counter() - start_time,
        )
        self._log_run_summary(summary)
        return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run detail extraction tasks from a list-result SQLite database.")
    parser.add_argument("--db", default=DATABASE_PATH, help="SQLite database path")
    parser.add_argument("--list-table", default=LIST_TABLE_NAME, help="List result table name")
    parser.add_argument("--task-table", default=TASK_TABLE_NAME, help="Detail task table name")
    parser.add_argument("--record-id-field", default=RECORD_ID_FIELD, help="List result record ID field")
    parser.add_argument("--detail-url-field", default=DETAIL_URL_FIELD, help="List result detail URL field")
    parser.add_argument("--source-url-field", default=SOURCE_URL_FIELD, help="Optional list result source URL field")
    parser.add_argument("--title-field", default=TITLE_FIELD, help="Optional list result title field")
    parser.add_argument("--cli-executable", default=DETAIL_CLI_EXECUTABLE, help="Detail extractor executable")
    parser.add_argument(
        "--cli-command-prefix",
        nargs="*",
        default=DETAIL_CLI_COMMAND_PREFIX,
        help="Optional full command prefix for launching the page extraction CLI, e.g. python -m page_extractor.cli",
    )
    parser.add_argument("--cli-subcommand", default=DETAIL_CLI_SUBCOMMAND, help="Detail extractor subcommand")
    parser.add_argument("--output-root", default=DETAIL_OUTPUT_ROOT, help="Detail task workspace root directory")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Max concurrent detail tasks")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size for claimed tasks")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS, help="Max task attempts before terminal failure")
    parser.add_argument("--timeout", type=int, default=DEFAULT_SUBPROCESS_TIMEOUT_SECONDS, help="Per-task subprocess timeout in seconds")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Do not invoke the detail extractor CLI")
    parser.add_argument("--limit", type=int, default=None, help="Optional hard limit on runnable tasks")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    config = Config.from_args(args)
    executor = BatchExecutor(config)
    summary = executor.run()
    return 0 if summary.terminal_failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
"""
    return textwrap.dedent(script).strip() + "\n"
