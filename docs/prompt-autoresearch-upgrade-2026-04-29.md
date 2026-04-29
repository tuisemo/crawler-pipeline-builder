# Prompt Audit And AutoResearch-Informed Optimization (2026-04-29)

## Scope
This document audits all model-facing prompts in the crawler-workflow system and records an optimization pass informed by AutoResearch methodology.
The goal is not to make business prompts "sound like AutoResearch", but to use its prompt-R&D discipline to produce higher-quality selectors, pagination decisions, and crawler scripts.

Audited modules:
- `llm_client.py`
- `prompts/crawler_prompt.py`
- `backend/workflows/prompting.py`
- `backend/workflows/generation_pipeline.py`
- `backend/assist/json_protocol.py`
- `backend/assist/pagination_recovery.py`

## Reverse Evaluation By Capability
### Product Function To Prompt Responsibility
- Visual workflow authoring: prompts must preserve user-authored graph intent instead of optimizing for a generic crawler.
- Prompt preview/editing: editable prompt text is treated as operator intent, while deterministic plan and output contract remain higher-priority guardrails.
- Script generation: prompts must produce executable Python, not only plausible scraping advice.
- Pro mode review/revision: prompts must behave as a quality gate and patch loop, not as a second free-form generation attempt.
- Assist features (field inference, selector optimization, pagination analysis): prompts must return bounded JSON decisions that the UI can immediately use.
- Runtime feedback: script sandbox logs now connect generation output back to product quality metrics.

### 1) Crawler Draft Generation
- Goal: Generate a runnable Playwright crawler that strictly follows deterministic plan + output contract.
- Previous strengths: Rich domain constraints, selector compatibility notes, skeleton-preserving instruction.
- Previous risks:
  - No explicit accept/reject gate for final output quality.
  - "Do many things" style guidance without measurable completion criteria.
  - Failure policy (what to do when uncertain/conflicting) was implicit.
- Upgrade:
  - Added explicit success criteria and final self-check in `CRAWLER_SYSTEM_PROMPT`.
  - Added an explicit quality gate in user prompt assembly (`_build_quality_gate_prompt`).
  - Reinforced minimal-change policy to reduce architecture drift.

### 2) Crawler Review Stage
- Goal: Produce deterministic go/no-go judgment and actionable fixes in JSON.
- Previous strengths: Structured JSON contract with severity/category/fix fields.
- Previous risks:
  - Rubric under-specified; "approve" threshold depended too much on model style.
- Upgrade:
  - Added an explicit release-gate rubric in `CRAWLER_REVIEW_SYSTEM_PROMPT`.
  - Added decision policy in `_build_review_prompt` to bias toward evidence-based findings.

### 3) Crawler Revision Stage
- Goal: Apply review findings while preserving deterministic plan and persistence strategy.
- Previous strengths: Plan + review context both present.
- Previous risks:
  - Could still over-edit or refactor broadly.
- Upgrade:
  - Added minimal-change policy in revision system prompt and revision user prompt.

### 4) Field Inference
- Goal: Infer `item_selector` + field selectors with high precision and stable extraction.
- Previous strengths: Strong selector constraints and field coverage guidance.
- Previous risks:
  - Weak explicit policy for low-evidence cases.
- Upgrade:
  - Added objective, failure policy, and self-check to reduce speculative fields.

### 5) Selector Optimization
- Goal: Improve selector robustness while preserving semantic target.
- Previous strengths: Clear convergence and stability steps.
- Previous risks:
  - No explicit rule for "initial selector already optimal".
- Upgrade:
  - Added failure policy and "return unchanged with reason" path.

### 6) Pagination Analysis
- Goal: Identify exact next/load-more control + robust selector.
- Previous strengths: Good contract and explicit anti-broad-selector rules.
- Previous risks:
  - Conflicting instruction: CSS-only requirements vs `:has-text(...)` example in pagination system rules.
  - Missing explicit abstain behavior under weak evidence in system suffix.
- Upgrade:
  - Removed text-locator style example and replaced with CSS-attribute-based examples.
  - Added explicit weak-evidence fallback and CSS-only output rule.

### 7) Data Cleaning
- Goal: Normalize raw values by target data type for machine consumption.
- Previous strengths: Covered common data types.
- Previous risks:
  - Output contract lacked explicit `reason`.
  - Uncertain cases had no consistent fallback.
- Upgrade:
  - Added objective + failure policy.
  - Extended output contract with `reason`.

### 8) Assist JSON Protocol / Repair
- Goal: Ensure downstream parser always receives one valid JSON object.
- Previous strengths: Strict no-markdown/no-prose rules.
- Previous risks:
  - Uncertainty handling not strongly framed as structured fallback.
- Upgrade:
  - Added explicit objective and failure policy (always object, never scalar/list, prefer low-confidence uncertainty over fabrication).
  - Strengthened repair rule to preserve CSS compatibility.

## Methodology Applied
- Clear objective and acceptance gate per stage.
- Fixed trust boundary (deterministic plan/output contract remain source of truth).
- Structured quality-gate framing for model self-verification.
- Low-cost failure mode: abstain/low-confidence structured output instead of free-form guessing.
- Minimal-change bias to reduce regressions and preserve working baseline.

## Expected Impact
- Higher output consistency across runs.
- Lower rate of semantically-invalid but syntactically-valid outputs.
- Reduced script drift (especially around output persistence and pagination behavior).
- Better observability of model decisions through explicit `reason` and review structure.

## Continuous Optimization Harness
### Offline prompt regression set
- Added fixed regression cases at `tests/fixtures/prompt_regression_cases.json`.
- Added executable regression assertions at `tests/test_prompt_regression_dataset.py`.
- Coverage includes:
  - infer_fields normalization stability,
  - wrapped JSON extraction stability,
  - pagination semantic-empty fallback stability.

### Prompt quality telemetry
- Added structured quality event `assist_prompt_quality_metric` in `backend/assist_services.py`.
- This event tracks:
  - `json_valid_first_pass`,
  - `used_partial_recovery`,
  - `used_repair_pass`,
  - `used_semantic_retry`,
  - `used_heuristic_fallback`,
  - `semantic_empty_detected`,
  - `confidence_bucket`,
  - prompt/output char lengths and token usage.

These metrics enable longitudinal tracking of prompt quality without changing API contracts.

## Manual Script Sandbox Feedback Loop
- Added a final script execution sandbox in `backend/workflows/script_sandbox.py`.
- The generation API returns scripts without executing them by default.
- Users manually trigger sandbox execution from the script workspace when they want runtime validation for the current generated or edited script.
- Each sandbox run writes:
  - isolated script copy,
  - `execution.jsonl`,
  - stdout/stderr tails,
  - exit code,
  - timeout and duration metadata.
- Sandbox summaries are returned as `sandbox_result` on `GenerateCrawlerResponse`.
- Runtime audit events:
  - `script_sandbox_started`,
  - `script_sandbox_completed`.
- Frontend result details show a first-class "脚本沙箱" block after manual execution.

Configuration:
- `SCRIPT_SANDBOX_ENABLED=true|false`
- `SCRIPT_SANDBOX_TIMEOUT_SECONDS=20`

Manual endpoint:
- `POST /api/workflows/run-script-sandbox`

Generation request-level controls remain available for API callers, but the workbench uses manual execution:
- `run_sandbox`
- `sandbox_timeout_seconds`

Technical selection details are documented in `docs/script-sandbox-technical-evaluation.md`.

This closes the prompt tuning loop: generated scripts can be reviewed by a model and then manually exercised in a repeatable execution environment whose logs become future tuning data.
