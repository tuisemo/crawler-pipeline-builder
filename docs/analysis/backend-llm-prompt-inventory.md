# Backend LLM Prompt Inventory

## Scope

This inventory covers only prompts that are actually sent to models by the backend.

It excludes:

- frontend prompt workspace UI text
- archive-only prompt references
- comments that describe prompts but are not sent to the model

## Prompt Families

### 1. Crawler Generation Family

Purpose:

- generate a runnable crawler draft
- review generated crawler quality
- revise the draft based on structured review findings

Primary files:

- `backend/prompts/tasks/crawler_system.py`
- `backend/prompts/crawler_prompt.py`
- `backend/prompts/assemblers/workflow.py`
- `backend/workflow/prompting.py`
- `backend/workflow/generation_pipeline.py`

Model-facing pieces:

- `CRAWLER_SYSTEM_PROMPT`
- `CRAWLER_REVIEW_SYSTEM_PROMPT`
- `CRAWLER_REVISION_SYSTEM_PROMPT`
- execution-plan prompt block
- output strategy prompt block
- model guardrails prompt block
- quality gate prompt block
- skeleton enhancement prompt block

Key optimization goals:

- reduce duplicated constraint language
- front-load output contract and hard requirements
- keep pagination update confirmation explicit
- keep revision prompts minimal and surgical

### 2. Assist Task Family

Purpose:

- infer fields from HTML evidence
- improve selectors without changing semantic target
- analyze pagination and identify a single actionable next control

Primary files:

- `backend/prompts/tasks/assist_tasks.py`
- `backend/prompts/assemblers/assist.py`
- `backend/assist/pagination_recovery.py`
- `backend/assist/services.py`

Model-facing pieces:

- `FIELD_INFERENCE_PROMPT_TEMPLATE`
- `SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE`
- `PAGINATION_ANALYSIS_PROMPT_TEMPLATE`
- pagination evidence package assembled by `build_pagination_analysis_user_prompt(...)`

Key optimization goals:

- make task objectives more concise
- keep evidence ordering explicit
- unify abstain / low-confidence behavior
- avoid repeating selector compatibility rules unnecessarily

### 3. JSON Protocol Family

Purpose:

- force assist responses into one machine-consumable JSON object
- repair broken model JSON without changing task intent

Primary files:

- `backend/assist/json_protocol.py`
- `backend/prompts/contracts/assist_contracts.py`

Model-facing pieces:

- `ASSIST_JSON_SYSTEM_PROMPT`
- `JSON_REPAIR_SYSTEM_PROMPT`
- `_build_json_task_system_prompt(...)`
- `_build_json_repair_prompt(...)`
- assist response contracts

Key optimization goals:

- front-load output lock
- separate contract shape from task objective cleanly
- keep repair prompt deterministic and non-creative

## Shared Prompt Assets

Primary files:

- `backend/prompts/shared/rules.py`

Shared rule groups:

- selector compatibility
- selector preservation
- Playwright element-handle constraints
- minimal-change policy
- low-confidence fallback policy

Optimization goals:

- keep shared rules short and reusable
- move repeated wording into shared fragments
- keep task prompts focused on what is unique to the task

## Runtime Prompt Call Sites

### Workflow generation

- `backend/workflow/generation_pipeline.py`
  - draft generation
  - review
  - revision

### Assist tasks

- `backend/assist/services.py`
  - infer fields
  - optimize selector
  - analyze pagination
  - JSON repair
  - semantic retry

## Current Optimization Policy

The repository currently follows these optimization constraints:

1. Preserve task intent and API contracts.
2. Prefer structural clarity over stylistic rewriting.
3. Keep prompts explicit about output format and hard constraints.
4. Avoid speculative reasoning instructions that do not help the target model.
5. Keep shared rules centralized and task goals local.
