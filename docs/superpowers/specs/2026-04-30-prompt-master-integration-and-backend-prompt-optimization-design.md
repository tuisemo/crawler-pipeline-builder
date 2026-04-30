# Prompt-Master Integration And Backend Prompt Optimization Design

## Goal

Install the external `prompt-master` skill so it is available to Codex locally, then use its prompt-engineering perspective to audit, consolidate, and optimize the backend prompts that are actually sent to large language models in this project.

The primary outcome is not to introduce a new runtime dependency, but to improve the quality, consistency, and maintainability of the repository's model-facing prompts.

## Scope

In scope:

- install `prompt-master` from `https://github.com/nidhinjs/prompt-master`
- make it available as a local Codex skill
- inventory all backend prompts that are actually sent to models
- group prompts by capability family
- reduce duplication and clarify prompt boundaries
- optimize prompts while preserving current API contracts and task intent
- add or update tests that lock prompt expectations where needed

Out of scope:

- changing frontend prompt workspace behavior
- changing public HTTP API contracts
- changing LLM provider transport behavior
- rewriting archive documents to match current implementation

## Installation Strategy

`prompt-master` should be installed as a local Codex skill, but the application itself should not depend on its presence at runtime.

This means:

- Codex can use the skill during prompt design and optimization work
- repository code remains self-contained
- prompt assets still live in `backend/prompts/`, `backend/assist/`, `backend/workflow/`, and `backend/llm/`

The skill is a design aid, not an execution dependency.

## Backend Prompt Inventory

Only prompts that are actually sent to models in the backend are part of this effort.

### Family 1: Crawler generation

Files:

- `backend/prompts/tasks/crawler_system.py`
- `backend/prompts/crawler_prompt.py`
- `backend/prompts/assemblers/workflow.py`
- `backend/workflow/prompting.py`
- `backend/workflow/generation_pipeline.py`

Includes:

- draft-generation system prompt
- review system prompt
- revision system prompt
- deterministic prompt body assembled from graph and execution plan
- quality gate, output strategy, and model guardrails

### Family 2: Assist task prompts

Files:

- `backend/prompts/tasks/assist_tasks.py`
- `backend/prompts/assemblers/assist.py`
- `backend/assist/pagination_recovery.py`

Includes:

- field inference prompt
- selector optimization prompt
- pagination analysis prompt
- pagination evidence packaging helpers

### Family 3: JSON protocol and repair prompts

Files:

- `backend/assist/json_protocol.py`
- `backend/prompts/contracts/assist_contracts.py`

Includes:

- JSON-only system prompt
- JSON repair system prompt
- response contracts for assist tasks

### Family 4: Runtime prompt call sites

Files:

- `backend/assist/services.py`
- `backend/workflow/generation_pipeline.py`
- `backend/llm/client.py`

These are not primarily content-definition files, but they control which prompts are paired together and how they are sent.

## Optimization Principles

The optimization pass should follow these rules:

1. Preserve task intent.
2. Preserve public API contracts and response schemas.
3. Prefer structural cleanup over stylistic rewriting.
4. Remove duplication before adding sophistication.
5. Keep prompt wording concrete and machine-actionable.
6. Prefer clear failure policies over vague “do your best” language.
7. Keep shared rules shared, but keep task objectives task-specific.

## Recommended Approach

### Option A: Rewrite all prompts into a new style

Pros:

- uniform surface style

Cons:

- high regression risk
- likely to break tuned assumptions already captured in tests

Rejected.

### Option B: Family-based optimization with current structure preserved

Pros:

- lowest risk
- compatible with existing test coverage
- improves maintainability without losing established behavior

Cons:

- results are evolutionary, not dramatic

Recommended.

### Option C: Assist-only optimization first

Pros:

- smallest initial surface

Cons:

- leaves generation prompts on a separate optimization track
- duplication across families remains

Rejected for this request.

## Target Design

The current prompt layering is already moving in a good direction. This work should strengthen that direction instead of replacing it.

### Desired boundaries

- `backend/prompts/shared/`
  - shared reusable prompt rules
- `backend/prompts/contracts/`
  - structured output contracts
- `backend/prompts/tasks/`
  - task-specific role/objective prompts
- `backend/prompts/assemblers/`
  - final prompt assembly helpers

### What to improve

#### Crawler generation family

Focus areas:

- reduce repeated guardrail language across generation, review, and revision
- make instruction hierarchy sharper
- ensure pagination-update confirmation requirement is consistently represented
- keep output strategy and quality gate concise but explicit

#### Assist family

Focus areas:

- make task objectives shorter and more comparable across tasks
- ensure evidence-handling and failure-policy sections are consistently structured
- unify confidence and abstention expectations
- keep selector compatibility rules centralized

#### JSON protocol family

Focus areas:

- clarify the distinction between task prompt, output contract, and repair prompt
- avoid duplicated selector rules where one shared statement is enough
- ensure repair prompt preserves contract shape without inventing content

## Implementation Sequence

### Phase 1: Install skill

- install `prompt-master` as a local Codex skill
- verify installation location and availability

### Phase 2: Write prompt inventory notes

- record the prompt families and current responsibilities
- note repetition, ambiguity, and contract boundaries

### Phase 3: Optimize by family

- generation family first
- assist family second
- JSON protocol family third

### Phase 4: Verification

- run prompt-related tests
- inspect changed prompts for accidental contract drift

## Verification Plan

Minimum verification:

- `tests/test_llm_prompts.py`
- `tests/test_assist_services.py`
- `tests/test_workflow_services.py`
- any prompt-regression tests already present

Success criteria:

1. `prompt-master` is installed locally as a Codex skill.
2. Backend prompt inventory is clearly documented.
3. Real backend prompts are grouped by family and optimized.
4. Public response contracts remain unchanged.
5. Prompt-related tests pass.

## Risks And Mitigations

### Risk 1: Over-optimizing prompt language

Mitigation:

- preserve proven task structure
- avoid broad rewrites
- keep tests as guardrails

### Risk 2: Mixing runtime concerns with prompt content concerns

Mitigation:

- keep transport/client logic separate from prompt-content changes

### Risk 3: Treating `prompt-master` as a runtime dependency

Mitigation:

- use it as a design skill only
- do not introduce application code that depends on the skill

## Decision

Install `prompt-master` locally, then optimize only the backend prompts that are actually sent to models, using a family-based structural refinement approach rather than a full rewrite.
