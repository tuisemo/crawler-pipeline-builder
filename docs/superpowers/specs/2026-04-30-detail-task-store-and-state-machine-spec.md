# Detail Task Store And State Machine Spec

## 1. Purpose

This document defines the durable task model that connects:

- list-page collection results already stored in SQLite
- the independent detail extraction CLI
- the generated batch orchestration script

Its focus is stage 2 of the target product line:

1. list records are already in the database
2. batch orchestration reads `detail_url`, tracks task state, and invokes detail collection
3. detail collection executes as an external CLI task


## 2. Scope

This spec covers:

- required assumptions for the existing list result table
- the dedicated detail task table
- task state definitions
- state transitions
- claiming, retry, and idempotency rules
- database update responsibilities for the batch runner

This spec does not cover:

- detail extraction internals
- CLI argument design in depth
- prompt schema for model generation


## 3. Design Principles

The task store must satisfy these principles:

1. List data and detail task lifecycle are separate concerns.
2. Task state must be durable and resumable.
3. Task creation must be idempotent.
4. A single orchestration script instance must be able to run tasks concurrently without duplicate local consumption.
5. Artifact paths are task outputs and must be stored on the task row, not inferred later.


## 4. Upstream List Result Assumptions

The existing list collector already writes records into SQLite.

The batch runner depends on the following minimum fields:

- `record_id`
- `detail_url`

Recommended upstream fields:

- `source_url`
- `title`
- `crawl_run_id`
- `created_at`

### 4.1 `record_id`

`record_id` is the stable identity of the list result record.

It may be:

- a primary key already written by the list collector
- a dedupe identity
- a synthetic stable ID derived from the record payload

The batch runner treats it as opaque text.

### 4.2 `detail_url`

`detail_url` is the URL that should be passed into the detail extractor CLI.

Rows with empty or invalid `detail_url` must not become runnable detail tasks.


## 5. Dedicated Detail Task Table

The batch orchestration layer must use a dedicated table:

- `detail_collection_tasks`

Recommended schema:

```sql
CREATE TABLE IF NOT EXISTS detail_collection_tasks (
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
);
```


## 6. Column Semantics

### 6.1 Identity fields

- `task_id`
  Stable identity of the detail task row. Recommended as UUID or deterministic synthetic ID.

- `record_id`
  Link to the upstream list result row.

- `detail_url`
  The target URL for detail collection.

### 6.2 Execution control fields

- `status`
  The current lifecycle state.

- `attempt_count`
  Number of execution attempts already made.

- `priority`
  Reserved for future scheduling hints.

- `batch_run_id`
  Logical ID for the current batch-runner execution session.

- `worker_id`
  Local worker identity inside one batch-runner process.

### 6.3 Timing fields

- `started_at`
  Time at which the most recent attempt started.

- `completed_at`
  Time at which the task reached its last terminal or successful state.

- `last_heartbeat_at`
  Optional heartbeat timestamp for future stuck-task recovery.

### 6.4 Error fields

- `error_code`
  Machine-friendly normalized failure code.

- `error_message`
  Human-readable failure summary.

### 6.5 Artifact fields

- `result_summary_path`
  Path to the stored raw summary JSON returned by the CLI.

- `content_markdown_path`
  Path to `content.md` if generated.

- `pdf_snapshot_path`
  Path to the PDF evidence artifact if generated.

- `attachments_dir`
  Path to the attachment directory if generated.

- `task_dir`
  Root directory for the detail task workspace.

- `detail_cli_version`
  Version string of the CLI used for this run.

### 6.6 Audit fields

- `created_at`
  Row creation time.

- `updated_at`
  Last mutation time.


## 7. State Definitions

The task table uses a fixed state machine:

- `pending`
- `running`
- `succeeded`
- `failed_retryable`
- `failed_terminal`
- `skipped`

### 7.1 `pending`

Task exists and is eligible to run.

### 7.2 `running`

Task has been claimed by the current batch orchestration process and has not yet completed.

### 7.3 `succeeded`

The detail extractor CLI completed successfully and returned usable output.

### 7.4 `failed_retryable`

The attempt failed, but the task may be retried later within the retry ceiling.

### 7.5 `failed_terminal`

The task failed for a non-retryable reason, or retry attempts have been exhausted.

### 7.6 `skipped`

The task was intentionally excluded and should not run, for example:

- missing `detail_url`
- invalid URL format
- filtered by operator rule


## 8. Allowed State Transitions

Recommended transition graph:

- `pending -> running`
- `running -> succeeded`
- `running -> failed_retryable`
- `running -> failed_terminal`
- `pending -> skipped`
- `failed_retryable -> running`
- `failed_retryable -> failed_terminal`

Disallowed transitions by default:

- `succeeded -> pending`
- `succeeded -> running`
- `failed_terminal -> running`

These may be enabled only by an explicit operator override mode in a later phase.


## 9. Task Creation Rules

The batch runner must create detail tasks by syncing from the list result table.

### 9.1 Sync rule

For each list record with a non-empty `detail_url`:

- if `(record_id, detail_url)` does not exist in `detail_collection_tasks`, insert a new row in `pending`
- if it already exists, do not create a duplicate row

### 9.2 Skip rule

If the row has:

- empty `detail_url`
- whitespace-only `detail_url`
- invalid URL format

the batch runner may:

- not create a task row at all, or
- create a `skipped` task row if audit visibility is desired

The default recommendation is:

- create a `skipped` row only when explicit auditability is needed
- otherwise, ignore the row during sync


## 10. Claiming Rules

### 10.1 Single-process concurrency assumption

First version assumes:

- one batch-runner process
- many worker threads
- one shared SQLite database

The main thread must claim tasks before handing them to worker threads.

### 10.2 Claim batch algorithm

The main thread:

1. selects up to `batch_size` runnable rows
2. filters by status in:
   - `pending`
   - `failed_retryable` with `attempt_count < max_attempts`
3. updates them to `running`
4. writes:
   - `batch_run_id`
   - `worker_id` placeholder or null
   - `started_at`
   - `updated_at`

Only after that should the rows be dispatched to worker threads.

### 10.3 Why workers must not self-claim

Workers should not independently query and update SQLite for task ownership because:

- duplicate local consumption becomes more likely
- contention grows
- generated code gets more complex


## 11. Attempt Counting

`attempt_count` should be incremented when a task is actually submitted to the CLI for execution, not merely when selected for inspection.

Recommended rule:

- increment `attempt_count` during transition to `running`

Reason:

- it reflects real execution attempts
- it simplifies retry ceiling evaluation


## 12. Retry Policy

### 12.1 Retryable examples

Typical retryable errors:

- subprocess timeout
- transient network errors
- attachment download instability
- temporary browser startup failure
- recoverable CLI execution error codes

### 12.2 Terminal examples

Typical terminal errors:

- invalid or missing URL
- malformed CLI invocation
- unsupported URL scheme
- invalid output root configuration
- unrecoverable input contract failure

### 12.3 Retry ceiling

When:

- `attempt_count >= max_attempts`

then any new retryable failure should be rewritten as:

- `failed_terminal`


## 13. Success Update Contract

On success, the batch runner must update:

- `status = 'succeeded'`
- `completed_at`
- `updated_at`
- `error_code = NULL`
- `error_message = NULL`
- `result_summary_path`
- `content_markdown_path`
- `pdf_snapshot_path`
- `attachments_dir`
- `task_dir`
- `detail_cli_version`


## 14. Failure Update Contract

On failure, the batch runner must update:

- `status`
- `completed_at`
- `updated_at`
- `error_code`
- `error_message`

If partial artifact paths are returned and are trustworthy, they may also be written, but this should not be required.


## 15. Idempotency Rules

### 15.1 Task creation idempotency

The unique constraint on `(record_id, detail_url)` is the primary guardrail.

### 15.2 Execution idempotency

Re-running the batch runner must be safe:

- `succeeded` rows are skipped unless future explicit re-run mode is enabled
- `failed_terminal` rows are skipped by default
- `failed_retryable` rows may run again within retry ceiling

### 15.3 Artifact ownership

The task row must store the artifact paths returned by the CLI rather than recomputing them.


## 16. Recommended Indexes

Recommended supporting indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_detail_tasks_status
ON detail_collection_tasks(status);

CREATE INDEX IF NOT EXISTS idx_detail_tasks_record_id
ON detail_collection_tasks(record_id);

CREATE INDEX IF NOT EXISTS idx_detail_tasks_updated_at
ON detail_collection_tasks(updated_at);
```


## 17. Future Extensions

The schema should remain compatible with future features such as:

- explicit re-run modes
- priority scheduling
- multi-policy detail extraction
- multi-run lineage
- artifact validation status

But these are not required in the first version.


## 18. Final Recommendation

Use a dedicated `detail_collection_tasks` table, keep the state machine explicit and small, and enforce idempotency with `(record_id, detail_url)`.

This is the cleanest bridge between:

- mature list-page result storage
- an independent detail extraction CLI
- a generated batch orchestration script
