# Script-First Production Crawler Plan

## Goal

Re-plan the SQLite output and resume capability around a **script-first delivery model**:

- the platform still keeps a deterministic workflow graph, compile plan, and bounded executor
- the production artifact is a generated Python crawler script
- SQLite output, checkpoint resume, and production hardening can be added by **multi-stage script generation and rewriting**
- every generated script must pass a structured verification pipeline before it is considered production-ready

This plan fits the current repository state:

- `backend/workflow_services.py` already builds a deterministic execution plan and prompt envelope
- `backend/workflow_codegen.py` already generates a deterministic Playwright skeleton with SQLite persistence helpers
- `generate-crawler` already exists as an LLM-based script generation path
- the workbench already supports prompt editing, skeleton generation, and result inspection

## Why This Direction Makes Sense

The current codebase now has two real capabilities:

1. a **platform-native execution path**
   - useful for bounded testing, workflow inspection, and fast validation
2. a **script generation path**
   - useful for exporting a deployable crawler artifact that teams can run, review, and version independently

For SQLite output and resume, a script-first strategy has strong advantages:

- the final production behavior lives in a plain Python file, which is easier to review and deploy
- output persistence and resume logic become explicit code, not only platform runtime behavior
- different customers can evolve generated scripts without waiting for every runtime feature to become first-class in the platform
- the generated script can be validated, linted, patched, and regression-tested as a normal software artifact

The key change is:

- do not rely on a **single LLM generation pass**
- instead, use the existing deterministic plan and skeleton as the base, then run **bounded enhancement passes**

## Core Recommendation

Use a **dual-track architecture**:

- keep the platform runner as the canonical bounded test environment
- treat the generated Python script as the canonical production delivery artifact

That means:

- workflow graph remains the source of truth for intent
- execution plan remains the source of truth for deterministic structure
- generated script becomes the source of truth for deployable runtime behavior

## Recommended Generation Pipeline

### Stage 0: Deterministic Plan

Input:

- workflow graph
- extracted field schema
- pagination strategy
- optional sink/runtime hints

Output:

- normalized execution plan from `compile_graph_to_plan`

Why it matters:

- the LLM should not infer core control flow from scratch
- the plan anchors URL, selector, field schema, pagination, limits, and output target

### Stage 1: Deterministic Skeleton

Input:

- execution plan

Output:

- baseline script from `generate_playwright_skeleton`

This stage should remain non-LLM.

It already gives us:

- stable Playwright imports and structure
- extraction helpers
- pagination helper
- JSON / SQLite persistence helpers
- consistent output shape

This skeleton should become the **starting code artifact** for every production script pipeline.

### Stage 2: LLM Functional Enhancement

Input:

- deterministic skeleton
- execution plan
- editable user prompt
- optional HTML fragment

Output:

- enhanced crawler script

Scope of this pass:

- improve waits and retry behavior
- strengthen selector robustness
- add anti-detection tactics where needed
- improve pagination verification
- preserve the execution plan and output contract

Important constraint:

- this stage should not be allowed to freely redesign the crawler architecture
- it should operate as a controlled enhancement pass over the deterministic skeleton

### Stage 3: LLM Persistence / Resume Rewrite

Input:

- enhanced script
- structured persistence contract

Output:

- script upgraded with SQLite sink and checkpoint resume semantics

This can be done as a second LLM pass rather than forcing one giant prompt.

Recommended persistence contract:

```json
{
  "output_mode": "sqlite",
  "sqlite_path": "output/products.db",
  "sqlite_table": "products",
  "write_mode": "upsert",
  "dedupe_keys": ["detail_url"],
  "resume": {
    "enabled": true,
    "job_id": "eworldship-products",
    "checkpoint_mode": "page"
  }
}
```

What this pass must add or preserve:

- business table writes
- `_sea_runs` metadata table
- `_sea_checkpoints` metadata table
- page-level checkpointing
- dedupe-safe upsert behavior
- replay-safe restart semantics

### Stage 4: Script Evaluation

Input:

- final script candidate
- execution plan
- expected quality rules

Output:

- machine-readable evaluation report

This stage can be LLM-assisted, but should not be LLM-only.

Recommended checks:

- static Python syntax validation
- import sanity
- required helper presence
- output path / SQLite path safety
- resume table presence
- pagination loop safety
- stop condition safety
- field extraction contract coverage
- dangerous pattern detection

### Stage 5: Bounded Runtime Validation

Input:

- final script candidate
- representative target or fixture

Output:

- evidence that the script actually runs in a bounded scenario

Recommended validation levels:

1. unit-like validation
   - syntax compile
   - helper introspection
2. dry-run validation
   - run against mocked fixtures or saved HTML
3. bounded live validation
   - run with low `max_items` / `max_pages`
   - verify records emitted
   - verify SQLite file created when configured
4. resume validation
   - simulate interruption
   - re-run with same `job_id`
   - verify no duplicate rows and checkpoint advance

## Why Not One Giant LLM Prompt

A single prompt that asks for:

- full crawler generation
- SQLite integration
- resume logic
- production hardening
- self-checking

will usually fail in one of two ways:

- it produces a large but inconsistent script
- it hides errors because there is no explicit verification boundary

Multi-pass generation is better because each pass has a narrow contract:

- generate structure
- enhance runtime logic
- add persistence and resume
- verify

This is effectively a constrained form of **ReAct**, but adapted for code generation:

- reason over the current artifact
- take a bounded code rewrite action
- inspect the result
- repeat until quality gates pass

## Recommended ReAct-Style Workflow

Do not expose free-form agent loops directly to the user at first.

Instead, implement a controlled internal workflow:

1. `plan`
   - compile deterministic plan
2. `generate_base`
   - emit skeleton
3. `enhance_runtime`
   - LLM rewrite pass for scraping quality
4. `enhance_persistence`
   - LLM rewrite pass for SQLite and resume
5. `evaluate_static`
   - static checks
6. `repair_if_needed`
   - one bounded retry pass if checks fail
7. `validate_runtime`
   - bounded execution
8. `report`
   - return script plus verification evidence

This is safer than a raw "keep thinking until done" loop because each step has:

- explicit inputs
- explicit outputs
- explicit stopping rules

## Role Of The Existing Platform Runner

The current platform runtime should not be discarded.

Its new role should be:

- a bounded verification harness
- a selector and field debugging environment
- a fast checkpoint logic reference implementation

In other words:

- platform runner validates ideas quickly
- generated script is what we ship

This keeps the existing backend investment valuable even if production delivery shifts toward scripts.

## Suggested Prompt Strategy

### Base system prompt

Keep the current crawler-generation system prompt, but add stronger non-negotiables:

- preserve deterministic execution plan
- preserve output contract
- prefer surgical changes to the provided skeleton
- do not remove persistence helpers when present
- implement resume by page-level checkpoint plus record-level dedupe

### Rewrite prompt for persistence

Add a dedicated rewrite prompt that says:

- here is the current script
- here is the persistence contract
- patch the script to support SQLite output and safe resume
- keep public entrypoints stable
- return only the revised complete script

This is more reliable than asking the initial generation prompt to invent everything.

### Evaluation prompt

Use a separate evaluation prompt that produces structured JSON:

```json
{
  "pass": true,
  "issues": [
    {
      "severity": "high|medium|low",
      "title": "missing checkpoint update after page advance",
      "evidence": "..."
    }
  ],
  "recommended_repairs": [
    "..."
  ]
}
```

This makes the LLM act as a reviewer, not only an author.

## Quality Gates

The platform should not mark a script as production-ready unless it passes all of these:

### Gate 1: Deterministic contract match

- entry URL present
- item selector present
- expected fields appear in extraction logic
- pagination config preserved

### Gate 2: Static code health

- Python syntax valid
- imports resolve
- script has a callable entrypoint

### Gate 3: Persistence integrity

- SQLite path is configurable
- table creation exists
- upsert path exists
- dedupe strategy exists
- `_sea_runs` and `_sea_checkpoints` exist when resume enabled

### Gate 4: Resume integrity

- checkpoint written after successful page completion
- replay of last page is dedupe-safe
- workflow/job fingerprint or equivalent compatibility guard exists

### Gate 5: Bounded live execution

- script can run with small limits
- at least one record is emitted when the page contains data
- SQLite output is physically created when configured

### Gate 6: Interruption recovery

- simulated failure preserves checkpoint
- second run resumes and completes
- no duplicate rows are introduced

## API / Product Direction

## Option A: Keep one-shot `generate-crawler`

Pros:

- smallest API change

Cons:

- hides the multi-stage process
- harder to inspect generation quality

Verdict:

- acceptable only as a short-term compatibility mode

## Option B: Add a production script pipeline endpoint

Recommended endpoint family:

- `POST /api/workflows/generate-production-script`
- `POST /api/workflows/evaluate-script`
- `POST /api/workflows/repair-script`

Recommended behavior:

- `generate-production-script` runs the full multi-stage pipeline
- returns:
  - final script
  - intermediate skeleton
  - evaluation report
  - validation evidence

Verdict:

- **recommended**

## Option C: Explicit workbench pipeline steps

UI could expose:

- Generate Skeleton
- AI Enhance Script
- Add SQLite/Resume
- Evaluate Script
- Validate Script

Pros:

- transparent and controllable

Cons:

- more UX surface area

Verdict:

- best for advanced mode, not necessarily default mode

## Recommended Implementation Phases

### Phase A: Re-anchor generation on skeleton

Scope:

- make deterministic skeleton the mandatory base artifact for LLM generation
- stop treating `generate-crawler` as blank-page generation
- pass skeleton + plan into the LLM prompt

Success criteria:

- generated scripts stay structurally close to the deterministic skeleton

### Phase B: Add persistence rewrite pass

Scope:

- add dedicated LLM pass for SQLite and resume enhancement
- provide persistence contract as structured input

Success criteria:

- generated scripts can emit SQLite and include checkpoint tables

### Phase C: Add script evaluation pipeline

Scope:

- static checks
- LLM reviewer report
- bounded runtime validation

Success criteria:

- every generated production script returns evidence, not just code

### Phase D: Add bounded auto-repair

Scope:

- when evaluation fails, allow one or two constrained rewrite attempts

Success criteria:

- obvious defects are repaired automatically without user hand-holding

### Phase E: Expose workbench UX

Scope:

- add a “生产脚本” workflow in the UI
- show pipeline stages and pass/fail evidence

Success criteria:

- users can request a production-grade script and see why it is trusted

## Concrete Recommendation For This Repository

Given the current codebase, the best next move is not to replace the newly added platform SQLite/resume support.

Instead:

- keep the current runtime implementation as the verification/reference path
- make the deterministic skeleton plus SQLite helpers the base artifact for LLM generation
- add a second-stage LLM rewrite for production hardening
- add a third-stage evaluation and bounded validation pipeline

In short:

- **runtime-native SQLite/resume** is the platform capability
- **script-first SQLite/resume** is the production delivery capability

Both should coexist.

## Final Recommendation

Best long-term model:

- workflow graph defines intent
- deterministic plan defines structure
- skeleton defines the trusted code scaffold
- multi-stage LLM rewriting upgrades the scaffold into a production script
- static + bounded runtime validation decide whether the script is production-ready

Best immediate next step:

1. upgrade `generate-crawler` from one-shot generation to **skeleton-based enhancement**
2. add a dedicated **SQLite/resume rewrite pass**
3. add a **script evaluation report**
4. only after that, expose a “production-ready script” mode in the workbench
