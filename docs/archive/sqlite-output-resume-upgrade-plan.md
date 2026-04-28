# SQLite Output And Resume Upgrade Plan

## Goal

Add an optional persistence upgrade so a workflow can:

- keep the current in-memory / JSON-style behavior by default
- optionally write extracted records into a local SQLite database
- recover from interruptions and continue safely without duplicating records

This plan is designed to fit the current `crawler-workflow` architecture:

- the React workbench edits a node/edge DSL
- the backend executor currently supports bounded `test-node` / `test-subflow`
- generated crawler skeletons currently write `crawler_output.json`

## Current State

### Runtime executor

- `extract_field` appends records into `ctx.records`
- `emit_record` only mirrors those records into the node result payload
- there is no durable sink abstraction yet
- there is no persisted run state, checkpoint table, or resume token

### Generated script

- deterministic skeleton generation writes all records to `crawler_output.json`
- there is no optional output backend and no resume behavior

### UI / DSL

- `emit_record` has no dedicated configuration today
- the graph has node-local data but no first-class workflow-level runtime config

## Recommendation

Use a **hybrid design**:

- put **record sink configuration** on `emit_record`
- put **run / resume configuration** on a workflow-level runtime object or run request

Why:

- `emit_record` is the semantic place for "where the extracted record goes"
- resume is not only an output concern; it spans pagination, batching, dedupe, and run lifecycle
- forcing all resume policy into `emit_record` would couple sink details to executor traversal rules

## Design Choice Comparison

### Option A: All config on `emit_record`

Pros:

- smallest visible UI change
- easy mental model for "records go here"

Cons:

- mixes sink config with traversal checkpoint policy
- awkward when one workflow has multiple emit paths
- makes future run-level features harder, such as scheduled runs, retry policy, or concurrency control

Verdict:

- acceptable as a short-term compatibility bridge
- not the best long-term model

### Option B: `emit_record` for sink, runtime config for resume

Pros:

- clean separation of concerns
- works for JSON, SQLite, and future sinks
- keeps checkpoint logic owned by the executor / runner
- easier to expose through API and generated scripts

Cons:

- requires one additional config surface beyond node data

Verdict:

- **recommended**

### Option C: Add a separate persistence node

Pros:

- explicit in graph shape

Cons:

- overlaps heavily with `emit_record`
- makes graph authoring noisier
- introduces node-order ambiguity

Verdict:

- not recommended

## Proposed Capability Model

### 1. `emit_record` sink configuration

Recommended new `emit_record.data` fields:

```json
{
  "label": "输出记录",
  "output_mode": "memory|json_file|sqlite",
  "json_file_path": "output/products.json",
  "sqlite_path": "output/products.db",
  "sqlite_table": "products",
  "write_mode": "append|upsert",
  "dedupe_keys": ["detail_url"],
  "batch_size": 50
}
```

Notes:

- `memory` preserves current behavior
- `json_file` is useful for parity with the existing generated skeleton
- `sqlite` enables durable storage
- `dedupe_keys` is the most important field for safe resume
- `write_mode=upsert` is strongly recommended for SQLite resume mode

### 2. Runtime / resume configuration

Recommended shape for a future workflow-level config:

```json
{
  "meta": {
    "runtime": {
      "job_id": "eworldship-products",
      "resume_mode": "off|safe|force",
      "checkpoint_mode": "page",
      "checkpoint_interval": 1
    }
  }
}
```

If adding `graph.meta` immediately feels too invasive for the current frontend, the short-term bridge should be:

- keep sink config on `emit_record`
- add runtime options to the **run request payload**, not to `emit_record`

That gives us durability without blocking on a top-level DSL schema redesign.

## Why Page-Level Resume Is Better Than Item-Level Resume

For this project, the safest default is:

- checkpoint at **page boundaries**
- dedupe at **record boundaries**

Not recommended as the primary strategy:

- restoring a precise "DOM item index" inside a page

Reason:

- list ordering can drift between runs
- ads / promoted rows can appear or disappear
- DOM structure may shift after reload

Better strategy:

1. persist the last completed page cursor
2. on resume, reopen the run
3. continue from the last committed page boundary
4. rely on SQLite upsert / unique constraints to absorb duplicates safely

This is simpler and more robust than trying to resume in the middle of a page.

## SQLite Schema Proposal

Use one SQLite file per workflow output target.

### Business table

Table name comes from `emit_record.data.sqlite_table`.

Recommended columns:

- user fields inferred from `extract_field`
- `_sea_run_id TEXT`
- `_sea_source_url TEXT`
- `_sea_emitted_at TEXT`
- `_sea_record_hash TEXT`

Recommended indexes:

- unique index on `dedupe_keys` when provided
- otherwise unique index on `_sea_record_hash`

### Internal metadata tables

#### `_sea_runs`

```sql
CREATE TABLE IF NOT EXISTS _sea_runs (
  job_id TEXT PRIMARY KEY,
  workflow_fingerprint TEXT NOT NULL,
  output_target TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT,
  last_error TEXT
);
```

#### `_sea_checkpoints`

```sql
CREATE TABLE IF NOT EXISTS _sea_checkpoints (
  job_id TEXT PRIMARY KEY,
  page_index INTEGER NOT NULL DEFAULT 0,
  current_url TEXT,
  last_next_selector TEXT,
  emitted_count INTEGER NOT NULL DEFAULT 0,
  cursor_json TEXT,
  updated_at TEXT NOT NULL,
  finished INTEGER NOT NULL DEFAULT 0
);
```

`cursor_json` should hold extensible structured state, for example:

```json
{
  "entry_url": "https://www.eworldship.com/app/product_1772.html",
  "page_index": 12,
  "current_url": "https://www.eworldship.com/app/product_1772.html?&p=13",
  "pagination_strategy": "click_next",
  "pagination_selector": ".kq-pager a.next"
}
```

## Backend Architecture Changes

## A. Add a record sink abstraction

Introduce a small runtime interface:

```python
class RecordSink:
    def open(self) -> None: ...
    def write_records(self, records: list[dict[str, Any]], context: dict[str, Any]) -> int: ...
    def checkpoint(self, state: dict[str, Any]) -> None: ...
    def close(self) -> None: ...
```

Implementations:

- `InMemorySink`
- `JsonFileSink`
- `SQLiteSink`

The existing in-memory behavior becomes the default sink, which keeps backward compatibility intact.

## B. Extend `ExecutionContext`

Add fields such as:

- `run_id`
- `job_id`
- `record_sink`
- `resume_mode`
- `checkpoint_state`

`handle_emit_record()` should stop being only a payload mirror and become the flush point to the configured sink.

## C. Keep `test-subflow` lightweight

`test-subflow` is currently an inspection endpoint, not a production runner.

Recommended behavior:

- keep `test-subflow` returning in-memory sample records
- optionally allow it to exercise sink config in a bounded way later
- do **not** make it the primary durable execution API

Instead, add a new production-oriented endpoint in a later phase:

- `POST /api/workflows/run`

Recommended request shape:

```json
{
  "graph": { "...": "..." },
  "session_id": "optional",
  "runtime": {
    "job_id": "eworldship-products",
    "resume_mode": "safe"
  }
}
```

## D. Compile plan / code generation support

Extend the execution plan to include output settings:

```json
{
  "output": {
    "mode": "memory|json_file|sqlite",
    "json_file_path": "output/products.json",
    "sqlite_path": "output/products.db",
    "sqlite_table": "products",
    "write_mode": "append|upsert",
    "dedupe_keys": ["detail_url"]
  }
}
```

The generated skeleton should then:

- keep JSON output as the default
- optionally create / write SQLite
- optionally resume from `_sea_checkpoints`

## Frontend / UX Plan

### `emit_record` panel

Add an "输出目标" section:

- 输出模式: 内存 / JSON 文件 / SQLite
- JSON 文件路径
- SQLite 文件路径
- SQLite 表名
- 写入模式: append / upsert
- 去重键: tag-style input or comma-separated list
- 批量写入条数

### Run controls

Resume settings are better exposed in run controls than buried inside a node:

- job id
- resume mode
- whether to clear previous checkpoint

Short-term compromise if there is no run dialog yet:

- allow advanced users to edit runtime config through DSL JSON

## Resume Semantics

### `resume_mode = off`

- ignore prior checkpoint
- create a fresh run

### `resume_mode = safe`

- require matching `workflow_fingerprint`
- require matching sink target
- resume from persisted checkpoint
- rely on upsert / dedupe to avoid duplicate rows

### `resume_mode = force`

- reuse checkpoint even if workflow fingerprint changed
- intended only for expert/manual recovery use

## Failure Handling

### Crash before checkpoint commit

Possible outcome:

- some records may already be written
- checkpoint may lag behind

Mitigation:

- records are written with upsert or unique constraint
- resume replays the last page safely

### Crash during batch write

Mitigation:

- wrap each batch in a SQLite transaction
- update checkpoint only after the batch commit succeeds

### Workflow changed after previous run

Mitigation:

- compare `workflow_fingerprint`
- block `safe` resume when the graph materially changed

## Implementation Phases

### Phase 1: Optional SQLite sink without resume

Scope:

- add `emit_record` config fields
- add sink abstraction
- add SQLite writer
- keep executor response payload unchanged
- extend generated skeleton to support SQLite output mode

Success criteria:

- existing workflows still work with no config changes
- `emit_record.output_mode = sqlite` writes rows into a local `.db`
- repeated runs with `write_mode=upsert` do not duplicate rows when dedupe keys are set

### Phase 2: Durable run + page-level checkpoint resume

Scope:

- add production run endpoint
- add `_sea_runs` and `_sea_checkpoints`
- persist checkpoint after each completed page
- support `resume_mode`

Success criteria:

- killing a run mid-pagination and restarting resumes near the last completed page
- duplicate rows are prevented by unique keys / record hash

### Phase 3: Workbench UX and observability

Scope:

- add `emit_record` sink editor
- add run dialog / runtime config UI
- show active run status, checkpoint time, rows written, last error

Success criteria:

- users can configure SQLite and resume without editing raw JSON

## Recommended First Implementation Slice

If we want the smallest safe upgrade path, start here:

1. `emit_record` gains `output_mode`, `sqlite_path`, `sqlite_table`, `write_mode`, `dedupe_keys`
2. backend adds `SQLiteSink`
3. generated skeleton supports SQLite output
4. resume is deferred until the sink path is proven stable

This gives immediate value without entangling the current bounded test executor with long-running state management too early.

## Final Recommendation

Best long-term design:

- `emit_record` owns output sink configuration
- a future workflow runtime config or run request owns resume / checkpoint policy
- page-level checkpoint + record-level upsert is the default recovery model

Best next step:

- implement **Phase 1** first
- then add a dedicated durable run API for **Phase 2**
