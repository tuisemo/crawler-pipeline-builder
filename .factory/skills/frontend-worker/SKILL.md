---
name: frontend-worker
description: Build and verify the React workbench, compatibility UI, and browser-facing workflow interactions.
---

# frontend-worker

## When to Use This Skill
Use for React workbench shell, canvas editing, DSL editor sync, property panels, results UI, and compatibility-mode browser flows.

## Required Skills
- `frontend-patterns`: use for React component/state patterns
- `agent-browser`: use for browser verification of the implemented user flows

## Work Procedure
1. Read `mission.md`, `AGENTS.md`, `.factory/library/*.md`, and the assigned feature.
2. Respect the canonical workflow state model: visual canvas, DSL, config panel, and results must stay synchronized.
3. Add or update targeted frontend tests where the stack supports them; otherwise perform explicit browser checks with `agent-browser`.
4. Preserve a visible fallback path to the legacy-compatible flow when the feature touches primary authoring paths.
5. Validate required-field and error states, not only the happy path.
6. Run applicable frontend/build checks plus project validation commands before finishing.
7. Capture screenshots/observations for each user-facing flow you verified.

## Example Handoff
```json
{
  "salientSummary": "Built the React workbench shell with canvas, property panel, and DSL editor sync; validated node selection and DSL error handling in the browser.",
  "whatWasImplemented": "Added the initial React layout and synchronized editor state so node selection updates the property panel and valid DSL edits rehydrate the canvas while invalid DSL preserves the last runnable state.",
  "whatWasLeftUndone": "Backend execution wiring for node/subflow tests is handled by separate features.",
  "verification": {
    "commandsRun": [
      {"command": "npm run build", "exitCode": 0, "observation": "React bundle built successfully."}
    ],
    "interactiveChecks": [
      {"action": "Load workbench and create open_page -> end flow", "observed": "Canvas rendered both nodes and the DSL updated immediately."},
      {"action": "Introduce invalid DSL in editor", "observed": "Inline validation error appeared and prior valid graph remained visible."}
    ]
  },
  "tests": {
    "added": [
      {"file": "src/workbench/__tests__/dsl-sync.test.ts", "cases": [{"name": "invalid_dsl_preserves_last_valid_state", "verifies": "Bidirectional sync is non-destructive on parse errors."}]}
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator
- The feature needs a new node type or UX pattern not covered by the approved MVP
- DSL/state synchronization semantics are ambiguous
- Browser validation reveals systemic session/runtime issues that require backend changes outside feature scope
