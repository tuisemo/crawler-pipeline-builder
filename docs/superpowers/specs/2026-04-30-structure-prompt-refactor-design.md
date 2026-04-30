# Structure And Prompt Refactor Design

## Goal

Refactor the repository so that the real application code is clearly grouped under `backend/` and `frontend/`, while root-level files are reduced to entrypoints and project-level documents. At the same time, reorganize the prompt system so that shared rules are reused across related capabilities and task-specific prompt pieces can be tuned independently.

This refactor should improve readability and maintainability without changing API contracts, startup commands, or core product behavior.

## Scope

In scope:

- Move backend implementation modules into clearer subpackages under `backend/`
- Keep only minimal compatibility entrypoints at the repository root
- Reorganize frontend source into clearer feature-oriented folders without changing UI behavior
- Move scattered analysis documents from the repository root into `docs/`
- Split prompt definitions into shared rules, contracts, task prompts, and assemblers
- Reuse common prompt rules across generation and assist tasks
- Update imports, package metadata, and documentation to match the new layout

Out of scope:

- Changing public HTTP API payloads or routes
- Rewriting workflow execution behavior
- Redesigning frontend interaction flows
- Replacing the current LLM provider/client behavior
- Broad cleanup unrelated to the structure and prompt refactor

## Target Repository Layout

```text
sea-data/
├── backend/
│   ├── api/
│   ├── assist/
│   ├── core/
│   ├── extraction/
│   ├── llm/
│   ├── prompts/
│   ├── runtime/
│   └── workflow/
├── frontend/
│   └── src/
│       ├── app/
│       ├── features/
│       ├── services/
│       └── shared/
├── docs/
├── tests/
├── server.py
├── README.md
├── AGENTS.md
├── DESIGN.md
└── pyproject.toml
```

## Backend Design

### Package responsibilities

- `backend/api/`
  - HTTP route registration and request/response transport concerns only
  - Owns `assist_routes.py` and `workflow_routes.py`
- `backend/core/`
  - Shared settings, logging, and API response helpers
- `backend/runtime/`
  - Browser session management, async bridge, record sinks, and other runtime infrastructure
- `backend/workflow/`
  - Workflow graph validation, compilation, deterministic code generation, handlers, execution orchestration, and workflow-facing service entrypoints
- `backend/assist/`
  - Assist task orchestration plus assist-specific prompt protocol helpers
- `backend/extraction/`
  - DOM extraction, selector testing, and auto-detection helpers
- `backend/llm/`
  - Real LLM client implementation and stable system prompt definitions
- `backend/prompts/`
  - Prompt fragments, contracts, task prompt builders, and assembly helpers

### Compatibility strategy

- Keep root `server.py` as a thin compatibility entrypoint that imports the actual FastAPI app from the new backend location.
- Avoid long-term duplicate implementations. Compatibility files should only forward imports and entrypoints.

## Frontend Design

### Source layout

- `frontend/src/app/`
  - App shell, layout composition, and top-level workbench assembly
- `frontend/src/features/workflow/`
  - Workflow graph state, contracts, placement, defaults, and workflow-specific components
- `frontend/src/features/assist/`
  - Assist hooks and any assist-specific UI logic
- `frontend/src/features/prompt-workspace/`
  - Prompt draft management and prompt workspace helpers
- `frontend/src/features/results/`
  - Results panel and result detail rendering
- `frontend/src/shared/`
  - Shared utilities, generic UI helpers, and common assets/types that are not feature-specific
- `frontend/src/services/`
  - API client wrappers

### Frontend migration constraints

- `App.tsx` can remain the application shell, but its imports should point at the new locations.
- The goal is file grouping and boundary clarity, not UI redesign.
- Tests should move with their related modules when practical.

## Prompt System Design

### Goal

Separate stable reusable rules from task-specific instructions so that:

- prompt tuning can happen per capability
- related capabilities can inherit the same rule upgrades
- service modules no longer own large prompt string literals

### Target prompt layout

```text
backend/prompts/
├── __init__.py
├── assemblers/
├── contracts/
├── shared/
└── tasks/
```

### Prompt layer responsibilities

- `shared/`
  - reusable cross-task rules such as selector compatibility, JSON-only responses, minimal-change policy, Playwright compatibility constraints, and quality-gate phrasing
- `contracts/`
  - structured output contracts for assist tasks and review stages
- `tasks/`
  - task-specific instructions for crawler generation, crawler review, crawler revision, field inference, selector optimization, and pagination analysis
- `assemblers/`
  - functions that combine shared rules, contracts, deterministic context, and task prompts into final model-facing prompts

### Reuse rules

Shared rules should be reused across these task families:

- Selector stability and compatibility
  - used by crawler generation, field inference, selector optimization, and pagination analysis
- JSON output discipline
  - used by assist tasks and any structured review tasks
- Minimal-change policy
  - used by crawler revision, selector optimization, and any review-driven regeneration
- Low-confidence fallback behavior
  - used by assist tasks that should abstain rather than fabricate

Task-specific goals remain separate even when they share common rules. For example, field inference and pagination analysis should not be merged into one task prompt just because they both return JSON.

## Migration Plan

### Phase 1: Prepare layout and move documentation

- Create the new backend and frontend directories
- Move root analysis documents into `docs/`
- Update `docs/README.md` and `README.md` later after code movement stabilizes

### Phase 2: Move backend implementation

- Move extraction helpers into `backend/extraction/`
- Move route modules into `backend/api/`
- Move workflow modules into `backend/workflow/`
- Move runtime-oriented modules into `backend/runtime/`
- Move LLM implementation into `backend/llm/`
- Add thin compatibility shims only where needed

### Phase 3: Refactor prompt organization

- Move crawler prompt generation logic into `backend/prompts/`
- Extract shared rules and output contracts from service modules
- Replace inline prompt assembly in services with assembler calls
- Keep prompt semantics as close as possible to the current behavior during the first pass

### Phase 4: Reorganize frontend source

- Move workflow-related modules into `features/workflow/`
- Move result and prompt workspace modules into feature folders
- Introduce `app/` and `shared/` boundaries
- Update imports without changing runtime behavior

### Phase 5: Update docs and verify

- Update `README.md`, `docs/README.md`, and `docs/technical-guide.md`
- Update `pyproject.toml` package/module declarations
- Run backend tests, frontend tests, and frontend build

## Validation Plan

The refactor is successful if all of the following are true:

1. `python server.py` still starts the backend.
2. `uvicorn server:app --reload` still works.
3. Backend tests pass.
4. Frontend tests pass.
5. Frontend build passes.
6. Real implementation code primarily lives under `backend/` and `frontend/`.
7. Prompt contracts and shared rules no longer live as scattered string constants inside service modules.
8. Documentation reflects the new structure accurately.

## Risks And Mitigations

- Import breakage
  - Mitigation: migrate in phases and run tests after each major move
- Accidental prompt behavior drift
  - Mitigation: preserve prompt wording closely during the first extraction pass
- Frontend relative import churn
  - Mitigation: move by feature groups and repair imports immediately
- Documentation mismatch
  - Mitigation: update docs after structure settles, not before

## Decision Summary

- Use the medium-strength refactor strategy: keep minimal root entrypoints, move real implementation under `backend/` and `frontend/`
- Consolidate scattered documents under `docs/`
- Reorganize prompts by shared rules, contracts, task prompts, and assemblers
- Preserve runtime behavior and API contracts while improving structure
