# Detail Extractor CLI Contract Spec

## 1. Purpose

This document defines the runtime contract for the independent detail-page collection CLI.

The CLI is the engineering capability package that performs **single-detail-page** collection. It is intentionally separate from:

- the list-page collection script
- the batch orchestration script
- the script generation layer

The batch runner depends on this CLI contract remaining stable.


## 2. Role In The Product Line

The detail extractor CLI is responsible for:

- taking one detail URL as input
- executing detail-page collection
- writing artifacts into a dedicated task workspace
- returning a machine-readable summary

It is not responsible for:

- reading the list result database
- deciding batch concurrency
- scheduling retries
- tracking global task lifecycle


## 3. Design Principles

The CLI contract should satisfy these requirements:

1. One invocation processes one detail URL.
2. The CLI is deterministic and machine-callable.
3. JSON output must be stable and versionable.
4. Logging must go to the console and a task-local log file.
5. Artifact layout must be predictable.
6. The runtime implementation should be pure engineering, without LLM dependency.


## 4. Primary Command Shape

Recommended command entry point:

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

Recommended executable name:

- `detail-extractor`

Recommended primary subcommand:

- `collect`


## 5. Required Arguments

### 5.1 `--url`

Required.

The target detail page URL.

### 5.2 `--task-id`

Required.

The caller-provided task identity. The CLI should use this to create a deterministic task directory and to stamp logs and summary output.

### 5.3 `--output-root`

Required.

The root directory under which the CLI creates the task workspace.

### 5.4 `--format`

Required in the first generated orchestration flow.

Allowed values:

- `json`

This keeps the batch runner contract simple.


## 6. Recommended Optional Arguments

- `--timeout`
- `--save-markdown`
- `--save-pdf`
- `--download-attachments`
- `--log-level`
- `--log-file`
- `--skip-attachments`
- `--attachment-concurrency`
- `--no-cookie-consent`

The batch runner may choose a stable subset of these.


## 7. Task Workspace Contract

For each invocation, the CLI must create a task workspace under `output-root`.

Recommended path rule:

- `<output-root>/<task-id>/`

Recommended contents:

- `content.md`
- `page.pdf`
- `attachments/`
- `summary.json`
- `metadata.json`
- `logs/collect.log`

The exact set may vary by options, but `summary.json` and a log file should always be present unless execution fails before workspace creation.


## 8. Summary Output Contract

The CLI must print a single JSON object to `stdout`.

Recommended schema:

```json
{
  "status": "success",
  "task_id": "detail_task_xxx",
  "detail_url": "https://example.com/detail/123",
  "task_dir": "/abs/path/to/task",
  "result_summary_path": "/abs/path/to/task/summary.json",
  "content_markdown_path": "/abs/path/to/task/content.md",
  "pdf_snapshot_path": "/abs/path/to/task/page.pdf",
  "attachments_dir": "/abs/path/to/task/attachments",
  "attachment_discovered_count": 3,
  "attachment_downloaded_count": 2,
  "detail_cli_version": "0.1.0",
  "error_code": null,
  "error_message": null,
  "started_at": "2026-04-30 10:00:00",
  "completed_at": "2026-04-30 10:00:08"
}
```

### 8.1 Required fields

- `status`
- `task_id`
- `detail_url`
- `task_dir`
- `started_at`
- `completed_at`

### 8.2 Strongly recommended fields

- `result_summary_path`
- `content_markdown_path`
- `pdf_snapshot_path`
- `attachments_dir`
- `attachment_discovered_count`
- `attachment_downloaded_count`
- `detail_cli_version`
- `error_code`
- `error_message`


## 9. Summary Field Semantics

### 9.1 `status`

Allowed values:

- `success`
- `failed`
- optionally later: `partial`

For the first version, `success` and `failed` are sufficient.

### 9.2 Artifact path fields

These fields must contain:

- absolute paths, or
- paths that are explicitly documented as relative to `task_dir`

Recommended rule for first version:

- always return absolute paths

This makes the batch runner simpler.

### 9.3 Count fields

- `attachment_discovered_count`
  Number of attachment candidates found.

- `attachment_downloaded_count`
  Number of attachment files successfully downloaded.

### 9.4 Error fields

- `error_code`
  Stable machine-consumable code.

- `error_message`
  Human-readable summary.


## 10. Exit Code Contract

Recommended exit code contract:

- `0`: success
- non-zero: failure

Suggested internal grouping:

- `1`: generic failure
- `2`: invalid input
- `3`: timeout
- `4`: network-related failure
- `5`: artifact write failure

The batch runner should not depend on exact numeric semantics in the first version, but the CLI should still keep them stable for future classification.


## 11. Logging Contract

The CLI must:

- print operational logs to the console
- write a task-local log file

Recommended log path:

- `<task_dir>/logs/collect.log`

Required log properties:

- timestamp
- task_id
- detail_url
- stage name
- error stack trace on failure

The batch runner does not need to parse logs, but operators must be able to inspect them.


## 12. Runtime Purity Requirement

The CLI runtime must remain a pure engineering capability.

This means:

- no runtime LLM dependency
- no model inference in the collector flow
- deterministic detector / extractor logic only

LLM may still be used elsewhere in the platform to generate scripts or configs, but not inside the runtime detail extractor package.


## 13. Batch Runner Dependency Rules

The batch runner may assume only these CLI behaviors:

1. it can invoke `detail-extractor collect`
2. it can pass a URL, task ID, and output root
3. it can read stdout JSON
4. it can rely on exit code success/failure
5. it can store returned artifact paths directly in the database

The batch runner must not:

- infer artifact layout if the summary did not return it
- rebuild collector internals
- call collector Python modules directly


## 14. Versioning Rule

The summary schema should be treated as a versioned contract.

Recommended future field:

- `summary_schema_version`

Even if omitted in the first iteration, the CLI package version should still be emitted through:

- `detail_cli_version`


## 15. Recommended Future Subcommands

The package may later support:

- `detail-extractor validate`
- `detail-extractor inspect`
- `detail-extractor doctor`

But the first stage only requires:

- `detail-extractor collect`


## 16. Final Recommendation

Keep the CLI contract extremely small and stable:

- one detail URL in
- one task workspace out
- one stdout JSON summary out
- one success/failure exit code

This is the contract that makes the generated batch runner simple, robust, and reusable.
