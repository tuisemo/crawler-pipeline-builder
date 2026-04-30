# Pagination Update Confirmation Design

## Goal

Prevent duplicate data extraction after pagination by ensuring the system does not continue scraping until the page's list data has actually updated after a pagination action.

This applies to both:

- runtime workflow execution (`test-node` / `test-subflow`)
- generated crawler scripts from deterministic skeletons and LLM-enhanced outputs

## Problem Statement

In real collection scenarios, clicking the next-page control is not enough to prove that the list data has updated.

Observed failure mode:

1. pagination control is found
2. click succeeds
3. URL may stay the same
4. item count may stay the same
5. old list DOM may remain briefly before asynchronous replacement
6. extraction runs too early
7. previous-page records are extracted again

Current implementation risk:

- runtime pagination in `backend/workflow/handlers.py` waits with `networkidle` and a fixed timeout, then only checks URL or item count changes
- deterministic script generation in `backend/workflow/codegen.py` waits for `domcontentloaded` after pagination click, but does not confirm that list content itself changed

These checks are too weak for pagination patterns where:

- URL does not change
- each page has the same number of items
- data is refreshed asynchronously inside the same container

## Scope

In scope:

- add content-update confirmation for runtime pagination
- add equivalent content-update confirmation to deterministic generated scripts
- strengthen prompt guidance so LLM-generated scripts preserve this behavior
- add tests for repeated-page and delayed-update scenarios

Out of scope:

- full redesign of pagination strategy detection
- unrelated executor refactors
- general-purpose mutation-observer infrastructure

## Design Summary

Treat pagination as successful only when at least one reliable signal shows that the list content has changed after the pagination action.

Do not treat the following as sufficient on their own:

- click success
- load-state completion
- fixed sleep

Use a multi-signal confirmation model:

1. list content fingerprint changed
2. URL changed
3. item count changed
4. list temporarily disappeared and reappeared with different content

If none of these can be confirmed within timeout, treat pagination as not advanced and stop downstream re-queueing or next-page extraction.

## Runtime Design

Target file:

- `backend/workflow/handlers.py`

### New helper responsibilities

#### `_collect_pagination_snapshot(page) -> dict[str, Any]`

Capture the current visible list state before and after pagination actions.

Snapshot fields:

- current URL
- active item selector from `page._last_item_selector`
- current item count when available
- stable fingerprints for the first 1-3 items

Fingerprint inputs should prefer:

- normalized item text
- stable href or src values when available
- short combined record preview rather than full DOM

The snapshot is not for persistence or dedupe. It is only for detecting whether the page content still looks like the previous page.

#### `_wait_for_pagination_update(page, before_snapshot, *, timeout_ms=...) -> tuple[bool, dict[str, Any] | None]`

After a pagination action:

1. perform lightweight built-in waits
2. poll for updated snapshots until timeout
3. return success only if `_pagination_state_changed(before, after)` is true

Polling strategy:

- try `wait_for_load_state("networkidle")` as a soft signal
- use short interval polling, not a single fixed sleep
- keep timeout bounded and deterministic

#### `_pagination_state_changed(before, after) -> bool`

Return true when any of these are true:

- URL changed
- item count changed
- fingerprint of first item changed
- combined fingerprint of first few items changed

This function is the main semantic boundary for deciding when pagination has truly advanced.

### Runtime behavior changes

`handle_paginate(...)` should:

1. collect pre-click snapshot
2. perform click or scroll action
3. wait for confirmed list update
4. set `ctx.state["last_pagination_advanced"] = True` only if update was confirmed
5. return a message that distinguishes:
   - control found but not advanced
   - control advanced and content updated
   - timeout while waiting for list update

### Runtime orchestration behavior

No major orchestration redesign is needed.

Existing behavior in `backend/workflow/executor_orchestration.py` already stops re-queueing successors when `last_pagination_advanced` is false.

This refactor improves the correctness of that boolean.

## Generated Script Design

Target file:

- `backend/workflow/codegen.py`

### New deterministic helpers in generated scripts

Generated skeletons should include:

- `collect_list_snapshot(page, item_selector)`
- `pagination_state_changed(before, after)`
- `wait_for_list_update(page, item_selector, before_snapshot, timeout_ms=...)`

### Updated `click_next_page(page)` behavior

The generated script should:

1. collect a snapshot before clicking
2. click the pagination control
3. do a lightweight load-state wait
4. poll until list-update confirmation succeeds
5. return `True` only after confirmed update

This keeps deterministic skeleton behavior aligned with runtime behavior.

## Prompting Design

Target files:

- `backend/workflow/prompting.py`
- `backend/prompts/assemblers/workflow.py`
- prompt fragments used by crawler generation

Prompt constraints should explicitly require:

- pagination clicks must not be treated as complete until list data updates
- do not rely only on fixed sleeps
- use content-change confirmation around pagination when URL may remain stable
- verify that the extracted list is not still showing the previous page

This keeps LLM-generated scripts from regressing to brittle `click + sleep` behavior.

## Alternatives Considered

### Option A: Longer fixed sleeps

Pros:

- simplest change

Cons:

- still fails when asynchronous replacement is slower or faster than expected
- unnecessary latency on fast pages
- does not prove data actually changed

Rejected.

### Option B: Multi-signal snapshot confirmation

Pros:

- directly addresses same-URL same-count pagination
- bounded complexity
- testable in executor and skeleton generation

Cons:

- requires extra helper logic

Recommended.

### Option C: DOM mutation observer

Pros:

- potentially more reactive

Cons:

- higher complexity
- more site-specific edge cases
- harder to keep deterministic and easy to test

Rejected for now.

## Testing Plan

Update `tests/test_workflow_executor.py` to cover:

1. URL unchanged, count unchanged, first item changes
   - pagination should succeed
2. URL unchanged, count unchanged, content unchanged
   - pagination should fail confirmation
3. content updates only after a short delay
   - polling should wait long enough and then continue
4. load-more behavior where count increases
   - pagination should succeed

Update `tests/test_workflow_services.py` to assert generated scripts include:

- pre-click snapshot collection
- wait-for-update polling
- list-update confirmation logic

Preserve current workflow API and service behavior except for stronger pagination correctness.

## Failure Handling

If pagination control is found but no update can be confirmed:

- runtime executor should not requeue downstream extraction nodes
- result payload should clearly report that update confirmation failed
- generated scripts should stop pagination rather than risk duplicate extraction

This intentionally prefers under-fetching over duplicate collection.

## Risks And Mitigations

### Risk 1: False negatives

Some sites may update content subtly and still be judged unchanged.

Mitigation:

- compare multiple signals, not just one
- use first few items rather than a single item when possible

### Risk 2: False positives

Minor cosmetic changes could be mistaken for page advancement.

Mitigation:

- prefer fingerprints derived from item text and hrefs over transient DOM noise

### Risk 3: Longer pagination latency

Polling adds wait time.

Mitigation:

- keep polling intervals short and bounded
- still use load-state signals opportunistically

## Acceptance Criteria

This change is complete when:

1. runtime pagination no longer advances based solely on click success plus fixed wait
2. generated deterministic scripts confirm list updates before next-page extraction
3. prompt guidance explicitly instructs update confirmation after pagination
4. tests cover unchanged-URL unchanged-count but changed-content scenarios
5. tests cover unchanged-content no-advance scenarios

## Decision

Adopt multi-signal snapshot-based pagination update confirmation for both runtime execution and generated scripts.
