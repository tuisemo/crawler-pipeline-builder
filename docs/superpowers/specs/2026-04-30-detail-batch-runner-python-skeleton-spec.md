# Detail Batch Runner Python Skeleton Spec

## 1. Purpose

This document defines the canonical Python skeleton for the generated stage-2 batch orchestration script.

Its goal is to make `Generate Detail Batch Runner` deterministic enough that:

- the platform can provide a stable structure
- the model only fills in project-specific mappings and policies
- generated scripts remain readable, resumable, and auditable

This spec sits below the higher-level design docs and below the generation context schema. It is the concrete blueprint for the final standalone script.


## 2. Scope

This spec covers:

- required top-level modules
- required classes and functions
- class responsibilities
- expected method boundaries
- CLI invocation flow
- database synchronization flow
- concurrency flow
- validation expectations for the generated script

This spec does not define:

- the internal implementation of the detail extractor CLI
- the detail task table schema in full
- the model context JSON schema in full


## 3. Design Principles

The generated script must follow these principles:

1. The script is standalone and runnable with standard Python.
2. The script uses the standard library first.
3. The script does not implement detail-page extraction logic.
4. The script centralizes database claiming in the main thread.
5. The script uses worker threads only for subprocess orchestration.
6. The script keeps logging and error classification explicit.
7. The script must be easy for operators to inspect and modify locally.


## 4. Required File Properties

The output artifact must be:

- a single `.py` file
- runnable on Windows
- usable without importing platform-only runtime modules

Recommended characteristics:

- ASCII source when possible
- concise comments only where structure is not obvious
- no hidden metaprogramming
- no dynamic code generation at runtime


## 5. Required Imports

The generated script should prefer this import set:

```python
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
```

Not every script must use every import, but the skeleton should stay within this family unless there is a strong reason otherwise.


## 6. Required Top-Level Layout

The script must contain the following top-level sections in order:

1. imports
2. constants
3. small helper functions
4. dataclasses
5. `Config`
6. `TaskRepository`
7. `CliInvoker`
8. `TaskRunner`
9. `BatchExecutor`
10. `build_arg_parser()`
11. `main()`
12. `if __name__ == "__main__":`


## 7. Required Dataclasses

The skeleton should define a minimal set of dataclasses for clarity.

Recommended dataclasses:

- `TaskRow`
- `TaskExecutionResult`
- `RunSummary`

### 7.1 `TaskRow`

Represents a single claimed task from the database.

Recommended fields:

- `task_id`
- `record_id`
- `detail_url`
- `attempt_count`
- `status`

Optional fields:

- `priority`
- `batch_run_id`
- `source_url`
- `title`

### 7.2 `TaskExecutionResult`

Represents the normalized result returned from running the detail CLI for one task.

Recommended fields:

- `task_id`
- `record_id`
- `status`
- `error_code`
- `error_message`
- `summary`
- `started_at`
- `completed_at`

### 7.3 `RunSummary`

Represents the final run-level metrics printed at the end of the script.

Recommended fields:

- `batch_run_id`
- `synced_count`
- `selected_count`
- `succeeded_count`
- `retryable_failed_count`
- `terminal_failed_count`
- `skipped_count`
- `duration_seconds`


## 8. `Config` Class

### 8.1 Responsibility

`Config` is the canonical source of runtime settings.

It must not talk to the database or invoke subprocesses.

### 8.2 Required fields

Required config fields:

- `database_path`
- `list_table_name`
- `task_table_name`
- `record_id_field`
- `detail_url_field`
- `detail_cli_executable`
- `detail_cli_subcommand`
- `output_root`
- `concurrency`
- `batch_size`
- `max_attempts`
- `subprocess_timeout_seconds`
- `log_level`
- `run_log_path`
- `dry_run`
- `limit`

### 8.3 Required helpers

Recommended methods:

- `from_args(...)`
- `now_iso()`
- `new_batch_run_id()`


## 9. `TaskRepository` Class

### 9.1 Responsibility

All database access belongs here.

The repository must isolate SQL from the rest of the script.

### 9.2 Required methods

The class must contain methods equivalent to:

- `ensure_schema()`
- `sync_tasks_from_list_results()`
- `fetch_runnable_tasks()`
- `claim_tasks(...)`
- `mark_task_succeeded(...)`
- `mark_task_failed(...)`
- `mark_task_skipped(...)`
- `count_tasks_by_status(...)`

### 9.3 `ensure_schema()`

Creates:

- the detail task table if missing
- supporting indexes if missing

### 9.4 `sync_tasks_from_list_results()`

Must:

- read list rows with non-empty `detail_url`
- insert missing `(record_id, detail_url)` combinations into the task table
- return a synced count

### 9.5 `fetch_runnable_tasks()`

Must select tasks in statuses:

- `pending`
- `failed_retryable` where `attempt_count < max_attempts`

The returned rows should be limited by `batch_size` and optionally by `limit`.

### 9.6 `claim_tasks(...)`

Must:

- run in the main thread
- set selected rows to `running`
- increment `attempt_count`
- stamp `batch_run_id`
- stamp `started_at`
- stamp `updated_at`

### 9.7 Success and failure update methods

These methods must be separate and explicit rather than reusing one generic update blob with hidden logic.

Reason:

- easier review
- easier validation
- clearer generated code


## 10. `CliInvoker` Class

### 10.1 Responsibility

`CliInvoker` converts one `TaskRow` into one subprocess call.

### 10.2 Required methods

Recommended methods:

- `build_command(task: TaskRow) -> list[str]`
- `invoke(task: TaskRow) -> TaskExecutionResult`
- `parse_summary(stdout: str) -> dict[str, Any] | None`
- `classify_subprocess_failure(...) -> tuple[str, str]`

### 10.3 `build_command(...)`

Must construct a command that:

- calls `detail-extractor collect`
- passes `--url`
- passes `--task-id`
- passes `--output-root`
- requests JSON output
- passes timeout or other deterministic options if configured

### 10.4 `invoke(...)`

Must:

- call `subprocess.run`
- capture `stdout`
- capture `stderr`
- respect timeout
- never raise uncaught exceptions to the worker pool boundary
- always return a normalized `TaskExecutionResult`

### 10.5 Summary parsing

If stdout contains valid JSON:

- use it directly

If it does not:

- classify from exit code, stderr, or timeout context

The batch runner must not rely on fragile text parsing when JSON is absent.


## 11. `TaskRunner` Class

### 11.1 Responsibility

`TaskRunner` is the per-task orchestration layer between:

- database task row
- CLI invoker
- repository update payloads

### 11.2 Required methods

Recommended methods:

- `run_task(task: TaskRow) -> TaskExecutionResult`
- `classify_cli_result(...)`

### 11.3 Expected behavior

`TaskRunner` should:

1. log task start
2. invoke the CLI
3. normalize summary output
4. classify success vs retryable vs terminal failure
5. return the structured result

It should not write to the database directly if the design chooses to keep all persistence in the main thread. Either design is acceptable, but the preferred design is:

- worker returns result
- main thread persists result

This keeps SQLite write ownership simpler.


## 12. `BatchExecutor` Class

### 12.1 Responsibility

`BatchExecutor` runs the whole stage-2 flow.

### 12.2 Required methods

Recommended methods:

- `run() -> RunSummary`
- `_run_one_batch(...)`
- `_persist_worker_result(...)`
- `_log_run_summary(...)`

### 12.3 `run()`

Expected high-level sequence:

1. initialize logging
2. ensure schema
3. sync tasks from list results
4. repeatedly:
   - fetch runnable tasks
   - if none, stop
   - claim tasks
   - dispatch claimed tasks to thread pool
   - persist returned results
5. build final summary
6. print final summary

### 12.4 `_run_one_batch(...)`

Must:

- submit claimed tasks into `ThreadPoolExecutor`
- collect future results with `as_completed`
- return normalized per-task outcomes


## 13. Small Helper Functions

The script should keep small standalone helpers rather than burying trivial logic inside large methods.

Recommended helpers:

- `utc_now_iso()`
- `is_valid_detail_url(url: str) -> bool`
- `build_run_log_path(...)`
- `safe_json_loads(...)`

The URL validator should be conservative:

- require http/https
- reject blank strings


## 14. Logging Requirements

The skeleton must include:

- console logging
- per-run file logging

Recommended log messages:

- batch runner start
- number of tasks synced
- number of tasks claimed
- per-task success/failure
- retry classification
- final summary

Each per-task log should include:

- `task_id`
- `record_id`
- `detail_url`
- `attempt_count`


## 15. CLI Entry Requirements

The generated script must support local invocation via:

```bash
python run_detail_batch.py --db output/crawler_output.db
```

Recommended CLI arguments:

- `--db`
- `--list-table`
- `--task-table`
- `--record-id-field`
- `--detail-url-field`
- `--cli-executable`
- `--output-root`
- `--concurrency`
- `--batch-size`
- `--max-attempts`
- `--timeout`
- `--log-level`
- `--dry-run`
- `--limit`


## 16. Error Classification Skeleton

The script should include an explicit classifier function that maps:

- timeout
- non-zero exit code
- stderr content
- CLI summary `error_code`

to:

- `failed_retryable`
- `failed_terminal`

The classifier should be deterministic and small.


## 17. Validation Checklist For Generated Output

The platform should validate the generated script against this skeleton spec.

Recommended checks:

1. Contains required classes:
   - `Config`
   - `TaskRepository`
   - `CliInvoker`
   - `TaskRunner`
   - `BatchExecutor`

2. Contains required functions:
   - `main`

3. Uses `ThreadPoolExecutor`
4. Uses `subprocess.run`
5. References the CLI executable
6. References the approved task statuses
7. Contains a schema creation path
8. Contains task sync logic
9. Contains result persistence logic
10. Contains a `__main__` block


## 18. Non-Permitted Skeleton Drift

The generated script should not:

- import project-only runtime services by default
- call detail extraction Python modules directly
- switch to asyncio without explicit approval
- let workers claim SQLite tasks themselves
- merge all responsibilities into `main()`
- skip logging


## 19. Minimal Pseudocode Blueprint

```python
def main() -> int:
    args = build_arg_parser().parse_args()
    config = Config.from_args(args)
    executor = BatchExecutor(config)
    summary = executor.run()
    return 0 if summary.terminal_failed_count == 0 else 1
```

And inside `BatchExecutor.run()`:

```python
ensure_schema()
synced_count = sync_tasks_from_list_results()
while True:
    tasks = fetch_runnable_tasks()
    if not tasks:
        break
    claimed = claim_tasks(tasks)
    results = run_workers(claimed)
    persist_results(results)
return build_summary()
```


## 20. Final Recommendation

Treat this skeleton spec as the canonical shape of the generated stage-2 script.

The platform should prefer:

- deterministic structure
- constrained model fill-in
- explicit validation

over unconstrained script generation.
