# Detail Batch Runner And CLI Bridge Design

## 1. Background

The current `crawler-workflow` system is already strong at list-page collection:

- generate list-page Playwright collection scripts
- persist records to SQLite / JSON
- support prompt-assisted workflow authoring and script generation

Related split specifications:

- [Detail Task Store And State Machine Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-task-store-and-state-machine-spec.md)
- [Detail Extractor CLI Contract Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-extractor-cli-contract-spec.md)
- [Detail Batch Runner Generation Context Schema](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-batch-runner-generation-context-schema.md)
- [Detail Batch Runner Python Skeleton Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-batch-runner-python-skeleton-spec.md)
- [Generate Detail Batch Runner Capability Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-generate-detail-batch-runner-capability-spec.md)
- [Detail Batch Runner Validation And Acceptance Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-batch-runner-validation-and-acceptance-spec.md)

We now want to add a production-grade detail-page collection product line with these stages:

1. list-page data is collected and written into a database
2. a batch orchestration layer reads detail-page URLs from the database, tracks task status, and supports concurrent execution
3. a detail-page collector performs deep extraction for each detail URL

The key planning target in this design is **stage 2**.

This design treats detail-page collection as a **pure engineering capability package**, explicitly excluding LLM-based extraction from the runtime collector itself. At the same time, the platform's core value remains **script generation**, so stage 2 must be planned as a stable script generation capability rather than a hand-built one-off utility.


## 2. Design Goals

This design must achieve the following:

1. Define a clean bridge between list-page result storage and detail-page collection execution.
2. Package detail-page collection as an independent CLI command that can be called by scripts or other orchestrators.
3. Define how the system gives structured context to the model so the model can generate a robust, independent batch orchestration script.
4. Keep list-page collection, detail-page collection, and task orchestration clearly separated.
5. Support resumable and concurrent batch processing with durable status tracking.


## 3. Non-Goals

This design does not include:

- implementing detail-page collection now
- implementing new backend routes now
- implementing distributed multi-host scheduling
- using LLM in the runtime detail extractor
- modifying the current list-page workflow engine to directly absorb all detail-page logic


## 4. High-Level Product Line

The target product line is:

1. **List Collector**
   Existing capability. Generates and runs scripts that extract list-page records and persist them to SQLite.

2. **Detail Extractor CLI**
   New independent engineering capability. Accepts a single detail URL and writes task artifacts such as markdown, PDF, attachments, metadata, and a machine-readable summary.

3. **Detail Batch Runner**
   New generated orchestration script. Reads list results from SQLite, creates and manages detail tasks, invokes the detail extractor CLI concurrently, and writes task state and artifact paths back into the database.

The system's core script generation responsibilities become:

- `Generate Crawler`: generate list-page scripts
- `Generate Detail Batch Runner`: generate batch orchestration scripts for detail-page collection


## 5. Recommended Architectural Positioning

### 5.1 Why stage 2 should be an independent script

The user explicitly chose the final form of stage 2 as:

- an independent runnable batch orchestration script

That is the correct boundary because stage 2 is operational glue:

- it connects the list database to the detail CLI
- it manages concurrency, retries, and status transitions
- it is not the place to implement low-level detail extraction itself

### 5.2 Why stage 2 should not be a backend-only service first

A backend service could eventually exist, but it is not the best first target because:

- the platform's main value is script generation
- independent scripts are easier to inspect, run, and customize
- deployment requirements stay simpler
- operators can run stage 2 near the data and artifact environment without depending on the full platform runtime

### 5.3 Why stage 2 should not embed detail extraction logic

The batch runner must not reimplement detail extraction. It should only:

- read tasks
- call the CLI
- parse results
- update state

This keeps stage 2 short, stable, and easy for the model to generate reliably.


## 6. System Boundaries

### 6.1 List Collector boundary

The existing list collector remains responsible for:

- opening list pages
- paginating
- extracting structured fields
- persisting records

It must produce:

- a stable SQLite database output
- a record identifier or dedupe identity
- a detail URL field

### 6.2 Detail Extractor CLI boundary

The detail extractor CLI is responsible for:

- loading one detail URL
- extracting main content
- producing markdown
- optionally producing PDF snapshot
- optionally scanning and downloading attachments
- writing task artifacts into a workspace directory
- outputting a machine-readable result summary

It must not know how to:

- query the list result database
- decide batch scheduling policy
- perform cross-record orchestration

### 6.3 Detail Batch Runner boundary

The batch runner is responsible for:

- syncing candidate detail tasks from list results
- scheduling pending tasks
- invoking the detail extractor CLI concurrently
- updating task states
- recording error and artifact information

It must not:

- rewrite the detail extractor logic
- directly generate markdown, PDF, or attachments itself


## 7. Database Design For Stage 2

### 7.1 Existing list result table assumptions

The batch runner will depend on an existing SQLite table produced by list collection.

Minimum required fields:

- `record_id` or another stable row identity
- `detail_url`

Recommended fields:

- `source_url`
- `title`
- `crawl_run_id`
- `created_at`

### 7.2 New detail task table

Introduce a dedicated table:

- `detail_collection_tasks`

Recommended columns:

- `task_id TEXT PRIMARY KEY`
- `record_id TEXT NOT NULL`
- `detail_url TEXT NOT NULL`
- `status TEXT NOT NULL`
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `priority INTEGER NOT NULL DEFAULT 0`
- `batch_run_id TEXT`
- `worker_id TEXT`
- `started_at TEXT`
- `completed_at TEXT`
- `last_heartbeat_at TEXT`
- `error_code TEXT`
- `error_message TEXT`
- `result_summary_path TEXT`
- `content_markdown_path TEXT`
- `pdf_snapshot_path TEXT`
- `attachments_dir TEXT`
- `task_dir TEXT`
- `detail_cli_version TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Recommended uniqueness rule:

- unique key on `(record_id, detail_url)`

This enforces idempotent task creation while still allowing each logical list record to have one detail task for one detail URL.

### 7.3 Why a separate task table is required

Do not overload the list result table with many detail execution fields.

Reasons:

- list data and detail task lifecycle are different concerns
- detail tasks may be retried many times while the list record itself stays unchanged
- future versions may support multiple detail runs per list record with different policies
- artifact paths are task outputs, not primary list data


## 8. Task State Machine

### 8.1 State set

The batch runner should use a minimal, explicit state machine:

- `pending`
- `running`
- `succeeded`
- `failed_retryable`
- `failed_terminal`
- `skipped`

### 8.2 State meaning

- `pending`
  Task exists and is ready to run.

- `running`
  Task has been claimed by the current batch runner and is in progress.

- `succeeded`
  Detail extraction completed and artifact paths were recorded.

- `failed_retryable`
  The task failed for a retryable reason and may be attempted again.

- `failed_terminal`
  The task failed for a non-retryable reason and should not be retried automatically.

- `skipped`
  The task was intentionally excluded, for example missing `detail_url` or failing a pre-validation rule.

### 8.3 Failure classification

Recommended retryable examples:

- CLI timeout
- transient network errors
- temporary download failures
- browser launch instability

Recommended terminal examples:

- empty or invalid detail URL
- unsupported URL scheme
- malformed CLI configuration
- detail extractor input contract failure
- task workspace creation failure caused by invalid path configuration

### 8.4 Retry ceiling

Each task should stop retrying once `attempt_count >= max_attempts`, at which point the state becomes:

- `failed_terminal`


## 9. Detail Extractor CLI Contract

### 9.1 Primary command

The CLI should expose an explicit command such as:

```bash
detail-extractor collect \
  --url "https://example.com/detail/123" \
  --task-id "detail_task_xxx" \
  --output-root "./detail-output" \
  --format "json" \
  --timeout 180 \
  --save-markdown \
  --save-pdf \
  --download-attachments
```

### 9.2 Required properties of the CLI

The CLI contract must be stable and machine-friendly:

- deterministic arguments
- deterministic JSON summary output
- meaningful exit code
- durable task directory
- log file written to the task directory

### 9.3 Required summary schema

The CLI must print a single JSON object to `stdout`:

```json
{
  "status": "success",
  "task_id": "detail_task_xxx",
  "detail_url": "https://example.com/detail/123",
  "task_dir": "/abs/path/to/task",
  "content_markdown_path": "/abs/path/to/content.md",
  "pdf_snapshot_path": "/abs/path/to/page.pdf",
  "attachments_dir": "/abs/path/to/attachments",
  "attachment_discovered_count": 3,
  "attachment_downloaded_count": 2,
  "error_code": null,
  "error_message": null,
  "started_at": "2026-04-30 10:00:00",
  "completed_at": "2026-04-30 10:00:08"
}
```

### 9.4 Exit code semantics

Recommended exit code policy:

- `0`: success
- non-zero: failure

The batch runner should still parse JSON when available, but must not require success JSON in all failure cases. When JSON is absent, it should classify the task from exit code, stderr, and timeout context.


## 10. Internal Structure Of The Generated Batch Runner

To keep generation reliable, the batch runner should follow a fixed internal architecture.

Required structure:

1. `Config`
2. `TaskRepository`
3. `CliInvoker`
4. `TaskRunner`
5. `BatchExecutor`
6. `main`

### 10.1 Config

Contains:

- SQLite database path
- list table name
- detail task table name
- `record_id` field mapping
- `detail_url` field mapping
- CLI executable path
- concurrency
- batch size
- retry ceiling
- task output root
- subprocess timeout
- logging settings

### 10.2 TaskRepository

Responsibilities:

- create task table if needed
- sync candidate tasks from the list result table
- fetch runnable tasks
- claim a batch of tasks by setting status to `running`
- update task results
- update failure state

### 10.3 CliInvoker

Responsibilities:

- build CLI arguments
- execute `subprocess.run`
- parse stdout JSON
- normalize failure output

### 10.4 TaskRunner

Responsibilities:

- run a single task
- invoke the CLI
- classify result state
- return a normalized update payload for database persistence

### 10.5 BatchExecutor

Responsibilities:

- loop over pending or retryable tasks
- claim tasks in batches
- dispatch tasks with `ThreadPoolExecutor`
- collect results
- print run summary


## 11. Concurrency Model

### 11.1 Recommended model

Use:

- `ThreadPoolExecutor`

Do not use `asyncio` in the first version.

Reason:

- stage 2 mostly performs DB I/O and subprocess orchestration
- `subprocess.run` is straightforward with threads
- SQLite access is easier to reason about in a main-thread claim / worker-thread execute model
- generated code remains shorter and more reliable

### 11.2 Task ownership model

The main thread should:

1. select a batch of runnable tasks
2. mark them as `running`
3. assign `worker_id`, `batch_run_id`, `started_at`
4. submit them to the thread pool

Workers should not directly claim tasks from the database.

This reduces duplicate consumption risk and keeps SQLite contention manageable.

### 11.3 Scope of concurrency support

First-stage support target:

- one batch runner process
- many worker threads
- each worker calls one independent detail CLI process

Not in first-stage scope:

- multiple independent batch runner processes racing on the same SQLite task database


## 12. Idempotency Rules

### 12.1 Task creation idempotency

Task creation must be idempotent:

- the same `(record_id, detail_url)` pair must not create duplicate active tasks

### 12.2 Task execution idempotency

Re-running the batch runner must be safe:

- successful tasks are skipped unless an explicit re-run mode is requested
- retryable failed tasks can be retried
- completed fields may be overwritten only for the same task row

### 12.3 Artifact path idempotency

The detail CLI should be responsible for deterministic task directory creation and artifact layout.

The batch runner should only store returned paths; it should not infer or fabricate artifact locations.


## 13. Logging And Observability

The generated batch runner should always include:

- console logging
- per-run log file
- final run summary

Each task log line should preferably include:

- `task_id`
- `record_id`
- `detail_url`
- `status`
- `attempt_count`

The run summary should include:

- total tasks synced
- total tasks selected
- succeeded count
- retryable failure count
- terminal failure count
- skipped count
- total duration


## 14. Model Context Package For Script Generation

The model should not receive a vague natural-language request alone. It should receive a structured generation payload composed of seven sections.

### 14.1 Section A: List Output Contract

Contains:

- database type
- database path
- list table name
- primary key field
- detail URL field
- sample rows

### 14.2 Section B: Detail Task Contract

Contains:

- task table name
- key columns
- uniqueness rule
- status values
- retry rule

### 14.3 Section C: Detail CLI Contract

Contains:

- executable name
- command name
- required arguments
- optional arguments
- JSON summary schema
- exit code semantics

### 14.4 Section D: Execution Constraints

Contains hard rules such as:

- generate a standalone Python script
- use standard library modules first
- use `sqlite3`, `subprocess`, `json`, `concurrent.futures`
- use `ThreadPoolExecutor`
- do not implement detail extraction logic
- do not depend on platform-only runtime modules unless explicitly requested

### 14.5 Section E: Operational Policy

Contains:

- default concurrency
- default batch size
- retry ceiling
- timeout
- status transitions
- skip rules for empty URLs
- optional `--dry-run`
- optional `--limit`

### 14.6 Section F: Script Skeleton Contract

Contains required structure:

- `class Config`
- `class TaskRepository`
- `class CliInvoker`
- `class TaskRunner`
- `class BatchExecutor`
- `def main()`

### 14.7 Section G: Output Requirement

Contains:

- return only the complete Python script
- no markdown fences
- no explanation text
- keep logging
- keep concise comments only where necessary


## 15. Script Generation Strategy

### 15.1 Recommended generation mode

Use a **deterministic skeleton + LLM constrained fill-in** mode.

The system should not ask the model to invent the entire batch runner architecture from scratch.

Instead:

1. the platform constructs a deterministic generation payload
2. the platform may provide a fixed batch-runner skeleton
3. the model fills in project-specific mappings and emits the final runnable script

### 15.2 Why this approach is recommended

Benefits:

- lower variance
- easier testability
- fewer orchestration mistakes
- easier regression locking
- script generation stays aligned with the product's main value proposition

### 15.3 New generation capability

Introduce a new explicit product capability:

- `Generate Detail Batch Runner`

Inputs:

- list database contract
- field mapping
- task table contract
- detail CLI contract
- execution policy

Output:

- a standalone Python batch orchestration script


## 16. CLI Publication Plan

The detail-page capability package should be publishable and callable independently.

Recommended packaging goals:

- installable Python package
- console entry point such as `detail-extractor`
- stable CLI subcommands
- versioned output summary contract

Recommended subcommand shape:

- `detail-extractor collect`
- future optional commands:
  - `detail-extractor validate`
  - `detail-extractor inspect`
  - `detail-extractor doctor`

The batch runner only depends on:

- the `collect` command contract


## 17. Integration Channel Between List Results And Detail Tasks

The connection channel should be:

1. list collector persists structured rows into SQLite
2. batch runner reads rows with a non-empty `detail_url`
3. batch runner inserts missing rows into `detail_collection_tasks`
4. batch runner executes pending tasks via CLI
5. batch runner writes artifact paths and status back into `detail_collection_tasks`
6. downstream reporting or UI joins list results and detail task results by `record_id`

This channel is preferred over storing detail extraction outputs directly in the original list result table.


## 18. Phase Plan

### Phase 0: Contract preparation

Deliverables:

- detail CLI contract
- detail task table schema
- batch runner generation payload schema
- batch runner skeleton contract

### Phase 1: Script generation capability for stage 2

Deliverables:

- deterministic generation payload builder
- prompt contract for batch runner generation
- runnable batch orchestration script output

### Phase 2: Detail extractor CLI productization

Deliverables:

- installable CLI
- task workspace layout
- JSON summary output
- structured logging

### Phase 3: End-to-end connection

Deliverables:

- list result to detail task sync
- batch execution
- result join/query documentation


## 19. Risks

### 19.1 Architecture risk

If detail extraction logic leaks into the batch runner, the generated script will become too large and unstable.

### 19.2 SQLite contention risk

If task claiming is not centralized in the main thread, concurrent duplicate execution becomes more likely.

### 19.3 Contract drift risk

If the detail CLI summary format changes without version discipline, generated batch runners will break.

### 19.4 Product boundary risk

If the platform treats stage 2 as just another crawler script, users will struggle to understand that it is an orchestration layer, not a detail extraction engine.


## 20. Final Recommendation

Proceed with the following strategy:

1. treat detail extraction as an independent CLI product
2. treat stage 2 as a generated independent batch orchestration script
3. connect list results to detail execution through a dedicated task table
4. generate stage 2 from a deterministic contract package rather than free-form prompts

This is the cleanest path that preserves the current system's core focus on script generation while creating a robust bridge to a production-grade detail-page collection toolchain.
