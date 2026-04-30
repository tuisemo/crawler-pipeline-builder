# Detail Batch Runner Generation Context Schema

## 1. Purpose

This document defines the structured context package that should be provided to the model when generating the stage-2 batch orchestration script.

The main objective is to avoid free-form generation and instead constrain the model with a deterministic, schema-driven input package.


## 2. Why A Context Schema Is Required

The stage-2 script is operational glue. If the model receives only a natural-language description, generation variance will be high.

The model must not invent:

- database tables
- task states
- CLI behavior
- concurrency structure

Instead, these must be passed in as explicit machine-readable contracts.


## 3. Generation Target

The output target of the model is:

- one standalone Python script

That script must:

- read list results from SQLite
- sync rows into a detail task table
- claim runnable tasks
- invoke the detail extraction CLI concurrently
- parse CLI JSON summaries
- write task results back into SQLite


## 4. Context Package Sections

The generation context package must contain seven sections:

1. `list_output_contract`
2. `detail_task_contract`
3. `detail_cli_contract`
4. `execution_constraints`
5. `operational_policy`
6. `script_skeleton_contract`
7. `output_requirement`


## 5. Top-Level Context Schema

Recommended top-level JSON shape:

```json
{
  "generation_target": "detail_batch_runner",
  "context_version": "1.0",
  "list_output_contract": {},
  "detail_task_contract": {},
  "detail_cli_contract": {},
  "execution_constraints": {},
  "operational_policy": {},
  "script_skeleton_contract": {},
  "output_requirement": {}
}
```


## 6. Section A: `list_output_contract`

### 6.1 Purpose

Describes how list-page results are already stored.

### 6.2 Required fields

```json
{
  "database_type": "sqlite",
  "database_path": "output/crawler_output.db",
  "table_name": "records",
  "record_id_field": "record_id",
  "detail_url_field": "detail_url"
}
```

### 6.3 Recommended optional fields

```json
{
  "source_url_field": "source_url",
  "title_field": "title",
  "crawl_run_id_field": "crawl_run_id",
  "sample_rows": [
    {
      "record_id": "abc001",
      "detail_url": "https://example.com/detail/1",
      "title": "Sample title"
    }
  ]
}
```

### 6.4 Why sample rows matter

They help the model:

- understand expected value shapes
- preserve field names correctly
- avoid inventing wrong SQL field mappings


## 7. Section B: `detail_task_contract`

### 7.1 Purpose

Describes the durable task model for stage 2.

### 7.2 Recommended schema

```json
{
  "table_name": "detail_collection_tasks",
  "unique_key": ["record_id", "detail_url"],
  "status_values": [
    "pending",
    "running",
    "succeeded",
    "failed_retryable",
    "failed_terminal",
    "skipped"
  ],
  "columns": {
    "task_id": "TEXT PRIMARY KEY",
    "record_id": "TEXT NOT NULL",
    "detail_url": "TEXT NOT NULL",
    "status": "TEXT NOT NULL",
    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
    "priority": "INTEGER NOT NULL DEFAULT 0",
    "batch_run_id": "TEXT",
    "worker_id": "TEXT",
    "started_at": "TEXT",
    "completed_at": "TEXT",
    "last_heartbeat_at": "TEXT",
    "error_code": "TEXT",
    "error_message": "TEXT",
    "result_summary_path": "TEXT",
    "content_markdown_path": "TEXT",
    "pdf_snapshot_path": "TEXT",
    "attachments_dir": "TEXT",
    "task_dir": "TEXT",
    "detail_cli_version": "TEXT",
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL"
  }
}
```

### 7.3 Required behavioral annotations

```json
{
  "sync_rule": "insert_missing_tasks_from_list_results",
  "success_terminal": true,
  "failed_terminal_is_default_after_retry_ceiling": true
}
```


## 8. Section C: `detail_cli_contract`

### 8.1 Purpose

Tells the model exactly how the orchestration script must call the detail collector.

### 8.2 Recommended schema

```json
{
  "executable": "detail-extractor",
  "subcommand": "collect",
  "required_args": [
    "url",
    "task_id",
    "output_root",
    "format"
  ],
  "optional_args": [
    "timeout",
    "save_markdown",
    "save_pdf",
    "download_attachments"
  ],
  "stdout_format": "json",
  "exit_code_policy": "0_success_nonzero_failure",
  "summary_fields": [
    "status",
    "task_id",
    "detail_url",
    "task_dir",
    "result_summary_path",
    "content_markdown_path",
    "pdf_snapshot_path",
    "attachments_dir",
    "attachment_discovered_count",
    "attachment_downloaded_count",
    "detail_cli_version",
    "error_code",
    "error_message",
    "started_at",
    "completed_at"
  ]
}
```

### 8.3 Hard rule

The context must explicitly say:

- do not implement detail extraction logic in the generated batch runner


## 9. Section D: `execution_constraints`

### 9.1 Purpose

Defines hard implementation limits for the generated script.

### 9.2 Recommended schema

```json
{
  "language": "python",
  "standalone_script": true,
  "preferred_modules": [
    "sqlite3",
    "subprocess",
    "json",
    "pathlib",
    "datetime",
    "concurrent.futures",
    "logging",
    "argparse",
    "uuid"
  ],
  "concurrency_model": "thread_pool",
  "main_thread_claims_tasks": true,
  "workers_do_not_self_claim": true,
  "database_type": "sqlite",
  "do_not_use_platform_runtime_modules": true,
  "do_not_reimplement_detail_extractor": true
}
```

### 9.3 Why this matters

This prevents the model from:

- switching to asyncio unnecessarily
- importing unstable internal modules
- embedding extra business logic


## 10. Section E: `operational_policy`

### 10.1 Purpose

Defines runtime behavior defaults.

### 10.2 Recommended schema

```json
{
  "default_concurrency": 4,
  "default_batch_size": 20,
  "max_attempts": 3,
  "subprocess_timeout_seconds": 180,
  "skip_empty_detail_url": true,
  "support_dry_run": true,
  "support_limit": true,
  "retryable_failure_policy": [
    "timeout",
    "transient_network_error",
    "browser_startup_failure"
  ],
  "terminal_failure_policy": [
    "invalid_url",
    "invalid_cli_arguments",
    "workspace_configuration_failure"
  ]
}
```

### 10.3 Recommended optional policy flags

```json
{
  "write_run_log_file": true,
  "print_final_summary": true,
  "sync_new_tasks_before_execution": true
}
```


## 11. Section F: `script_skeleton_contract`

### 11.1 Purpose

Forces the generated script to follow a stable structure.

### 11.2 Recommended schema

```json
{
  "required_classes": [
    "Config",
    "TaskRepository",
    "CliInvoker",
    "TaskRunner",
    "BatchExecutor"
  ],
  "required_functions": [
    "main"
  ],
  "required_behaviors": [
    "create_task_table_if_needed",
    "sync_tasks_from_list_results",
    "claim_batch_in_main_thread",
    "invoke_detail_cli",
    "parse_cli_json_summary",
    "write_task_success_result",
    "write_task_failure_result",
    "print_run_summary"
  ]
}
```

### 11.3 Why this is better than free generation

It turns the model task into constrained completion rather than unconstrained architecture invention.


## 12. Section G: `output_requirement`

### 12.1 Purpose

Defines exactly what the model must output.

### 12.2 Recommended schema

```json
{
  "artifact_type": "python_script",
  "return_only_script": true,
  "no_markdown_fences": true,
  "no_commentary_before_or_after": true,
  "keep_runtime_logging": true,
  "prefer_short_explanatory_comments_only": true,
  "windows_compatible": true
}
```


## 13. Recommended Prompt Framing

The prompt generated from this schema should tell the model:

- you are generating a standalone Python batch orchestration script
- you must follow the provided database contract and CLI contract exactly
- you must not implement detail-page extraction
- you must invoke the external CLI for each task
- you must keep the script deterministic, resumable, and concurrent


## 14. Deterministic Payload Builder Recommendation

The platform should build this schema payload deterministically from:

- list result database settings
- known field mappings
- task table policy
- detail CLI configuration
- batch policy defaults

The model should never be asked to infer these if the platform already knows them.


## 15. Validation Recommendations

Before accepting the generated script, the platform should validate at least:

- required classes exist
- required functions exist
- CLI executable appears in the script
- task table name is referenced correctly
- required list fields are referenced correctly
- status literals match the approved state set


## 16. Example Minimal Context Package

```json
{
  "generation_target": "detail_batch_runner",
  "context_version": "1.0",
  "list_output_contract": {
    "database_type": "sqlite",
    "database_path": "output/crawler_output.db",
    "table_name": "records",
    "record_id_field": "record_id",
    "detail_url_field": "detail_url"
  },
  "detail_task_contract": {
    "table_name": "detail_collection_tasks",
    "unique_key": ["record_id", "detail_url"],
    "status_values": [
      "pending",
      "running",
      "succeeded",
      "failed_retryable",
      "failed_terminal",
      "skipped"
    ]
  },
  "detail_cli_contract": {
    "executable": "detail-extractor",
    "subcommand": "collect",
    "stdout_format": "json",
    "exit_code_policy": "0_success_nonzero_failure"
  },
  "execution_constraints": {
    "language": "python",
    "standalone_script": true,
    "concurrency_model": "thread_pool",
    "main_thread_claims_tasks": true
  },
  "operational_policy": {
    "default_concurrency": 4,
    "default_batch_size": 20,
    "max_attempts": 3,
    "subprocess_timeout_seconds": 180
  },
  "script_skeleton_contract": {
    "required_classes": [
      "Config",
      "TaskRepository",
      "CliInvoker",
      "TaskRunner",
      "BatchExecutor"
    ],
    "required_functions": ["main"]
  },
  "output_requirement": {
    "artifact_type": "python_script",
    "return_only_script": true,
    "no_markdown_fences": true
  }
}
```


## 17. Final Recommendation

Treat this schema as the canonical bridge between:

- platform knowledge
- the model
- the generated stage-2 script

The more deterministic this context package is, the more stable and auditable the generated batch runner will be.
