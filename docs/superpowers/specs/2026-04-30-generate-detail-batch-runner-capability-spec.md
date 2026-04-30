# Generate Detail Batch Runner Capability Spec

## 1. Purpose

This document defines the platform-facing capability:

- `Generate Detail Batch Runner`

Its purpose is to generate a standalone Python batch orchestration script that bridges:

- list-page SQLite output
- the independent detail extractor CLI
- durable detail task state tracking

This capability is part of the platform's script-generation product line and must remain distinct from:

- runtime detail extraction
- backend-only scheduling services
- ad hoc one-off operator scripts


## 2. Scope

This spec defines:

- capability intent
- request/response contract
- prompt assembly behavior
- deterministic payload builder responsibilities
- skeleton-enhancement generation mode
- output validation requirements
- failure and warning behavior

This spec does not define:

- the detail extractor CLI internals
- the full detail task table schema in detail
- the final implementation classes inside the backend


## 3. Capability Definition

### 3.1 Product role

`Generate Detail Batch Runner` is the script-generation counterpart to the detail extraction product line.

Its output is:

- one standalone Python script

That script is responsible for:

- syncing detail tasks from an existing SQLite list-result database
- claiming runnable tasks
- invoking `detail-extractor collect`
- parsing stdout JSON summaries
- writing task state and artifact paths back into SQLite

### 3.2 What it is not

This capability must not:

- generate the internals of the detail extractor
- embed detail extraction logic directly into the batch runner
- assume a backend daemon or task queue exists


## 4. Relationship To Existing Generation Capabilities

The current platform already supports list-page script generation.

The new capability should be treated as a sibling product capability:

- `Generate Crawler`
  Generates list-page collection scripts

- `Generate Detail Batch Runner`
  Generates orchestration scripts that consume list-page database results and trigger detail extraction tasks

This distinction should remain explicit in product design and code organization.


## 5. Inputs

The capability input should be built from structured data, not from free-form prompt text alone.

### 5.1 Required conceptual inputs

Required inputs:

- list result database path
- list result table name
- record identity field name
- detail URL field name
- detail task table contract
- detail CLI contract
- execution policy

### 5.2 Recommended optional inputs

- source URL field name
- title field name
- crawl run identifier field name
- default concurrency
- default batch size
- retry ceiling
- subprocess timeout
- output root path
- dry-run support policy
- limit support policy


## 6. Request Contract

Recommended capability request schema:

```json
{
  "database": {
    "type": "sqlite",
    "path": "output/crawler_output.db",
    "list_table_name": "records",
    "record_id_field": "record_id",
    "detail_url_field": "detail_url",
    "source_url_field": "source_url",
    "title_field": "title"
  },
  "detail_task": {
    "table_name": "detail_collection_tasks",
    "status_values": [
      "pending",
      "running",
      "succeeded",
      "failed_retryable",
      "failed_terminal",
      "skipped"
    ],
    "max_attempts": 3
  },
  "detail_cli": {
    "executable": "detail-extractor",
    "subcommand": "collect",
    "output_root": "./detail-output",
    "stdout_format": "json",
    "exit_code_policy": "0_success_nonzero_failure"
  },
  "execution_policy": {
    "default_concurrency": 4,
    "default_batch_size": 20,
    "subprocess_timeout_seconds": 180,
    "support_dry_run": true,
    "support_limit": true
  },
  "generation_policy": {
    "language": "python",
    "mode": "skeleton_enhancement"
  }
}
```

### 6.1 Why the request must stay structured

The request should not make the model infer:

- field names
- status names
- CLI executable names
- timeout policy

The platform already knows these and should pass them explicitly.


## 7. Response Contract

Recommended response schema:

```json
{
  "success": true,
  "script": "full python script text",
  "filename": "run_detail_batch.py",
  "model": "model-name",
  "generation_trace": [],
  "warnings": [],
  "validation": {
    "passed": true,
    "checks": []
  },
  "error": null
}
```

### 7.1 Required response fields

- `success`
- `script`
- `filename`
- `validation`
- `error`

### 7.2 Recommended response fields

- `model`
- `generation_trace`
- `warnings`


## 8. Generation Mode

### 8.1 Required mode

The recommended generation mode is:

- `skeleton_enhancement`

Meaning:

1. the platform provides a deterministic Python batch-runner skeleton
2. the model enhances and fills in project-specific mappings and operational details
3. the final output is the complete script

### 8.2 Why free-form generation is discouraged

Free-form generation is too risky because the model may:

- invent different architecture shapes
- drift to asyncio
- collapse all logic into one file section
- embed detail extraction logic
- miss task lifecycle behaviors


## 9. Prompt Assembly Behavior

### 9.1 Prompt inputs

The prompt builder should assemble:

1. structured execution plan for the batch runner
2. detail task store contract
3. detail CLI contract
4. generation context schema
5. deterministic Python skeleton

### 9.2 Prompt intent

The prompt should instruct the model to:

- preserve the deterministic skeleton structure
- preserve approved status values
- preserve the CLI-only detail execution boundary
- preserve the main-thread task claiming model
- return only the final complete Python script

### 9.3 Prompt sections

Recommended prompt sections:

- `Batch Runner Mission`
- `List Output Contract`
- `Detail Task Contract`
- `Detail CLI Contract`
- `Execution Constraints`
- `Python Skeleton`
- `Output Requirement`


## 10. Deterministic Payload Builder

### 10.1 Responsibility

The payload builder must convert the raw request into a generation-safe structured package.

It should:

- normalize missing optional values
- inject defaults
- reject invalid field names early when possible
- freeze status names and policy names

### 10.2 Normalization rules

Examples:

- if no list table name is provided, use a platform default only if explicitly configured
- if `max_attempts` is absent, fill from policy default
- if concurrency is invalid, clamp or reject according to validation policy

### 10.3 Validation before model call

The platform should fail fast before invoking the model if:

- required database fields are missing
- CLI executable name is blank
- detail task table name is invalid
- status value list does not match the approved state set


## 11. Deterministic Skeleton

The capability should have a built-in canonical Python skeleton aligned with:

- [Detail Batch Runner Python Skeleton Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-batch-runner-python-skeleton-spec.md)

The generation flow should always use this skeleton as the base artifact.

The model may improve:

- naming clarity
- SQL statements
- error classification structure
- argument handling
- logging details

The model may not replace:

- the overall class structure
- the concurrency model
- the CLI boundary


## 12. Validation Pipeline

The capability must not return a generated script without validation.

### 12.1 Required validation stages

1. **static structure validation**
2. **contract validation**
3. **warning extraction**

### 12.2 Static structure validation

Must confirm:

- required classes exist
- required functions exist
- `subprocess.run` exists
- `ThreadPoolExecutor` exists
- approved statuses are present
- `if __name__ == "__main__":` exists

### 12.3 Contract validation

Must confirm:

- list DB field names are referenced
- task table name is referenced
- CLI executable is referenced
- summary fields expected from the CLI are handled

### 12.4 Warning extraction

Warnings should be emitted when:

- the script includes suspicious extra complexity
- the script references unsupported imports
- the script omits recommended arguments like `--dry-run` or `--limit` despite policy requesting them


## 13. Failure Behavior

### 13.1 Fail-fast cases

The capability should return `success=false` before or after generation when:

- required input contract is incomplete
- skeleton assembly fails
- generated output fails mandatory validation

### 13.2 Warning-only cases

The capability may still succeed with warnings when:

- optional fields are unused
- some recommended validation checks are not satisfied but mandatory ones are
- the script is valid but less feature-complete than recommended


## 14. Save And Export Behavior

The capability should integrate with existing script save/export flow patterns.

Recommended output filename:

- `run_detail_batch.py`

Recommended save behavior:

- save inside the repository workspace using the same save-script mechanisms already used for generated scripts


## 15. Suggested Backend Layering

The future implementation may follow a structure such as:

- request/response schemas
- payload builder
- prompt builder
- deterministic skeleton provider
- generation service
- validator

The exact module names can be chosen later, but these responsibilities should remain separate.


## 16. Suggested Generation Trace

Recommended generation trace stages:

- `request_validation`
- `payload_build`
- `skeleton_prepare`
- `draft_generation`
- `script_validation`
- `finalize`

This helps diagnose generation quality regressions later.


## 17. Acceptance Criteria

This capability is accepted when:

1. it generates a standalone Python script
2. the script follows the required skeleton contract
3. the script invokes the detail extractor CLI rather than embedding extraction logic
4. the script references the correct database and task-table contracts
5. the script passes mandatory validation


## 18. Final Recommendation

Implement `Generate Detail Batch Runner` as a constrained generation capability built around:

- structured request data
- deterministic payload building
- a canonical Python skeleton
- post-generation validation

This is the most stable path for extending the platform's script-generation product line into detail-task orchestration.
