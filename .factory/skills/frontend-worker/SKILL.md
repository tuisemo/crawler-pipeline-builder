---
name: frontend-worker
description: Build and verify the React workbench, compatibility UI, and browser-facing workflow interactions.
---

# frontend-worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the work procedure.

## When to Use This Skill

Use for the React workbench shell, route/fallback behavior, canvas authoring, property panels, DSL editor synchronization, results rendering, compatibility-mode flows, and browser-facing workflow actions.

## Required Skills

- `frontend-patterns`: use when defining React state, component boundaries, async data flows, and error-handling patterns.
- `agent-browser`: required for browser verification of every user-visible flow you implement on the React or fallback UI surface.
- `coding-standards`: use when introducing new TypeScript/React files so project conventions stay consistent and minimal.

## Work Procedure

1. Read `mission.md`, mission `AGENTS.md`, `.factory/services.yaml`, and `.factory/library/*.md` before changing frontend code.
2. Restate the exact validation assertion IDs your feature fulfills. Keep the implementation scoped to those browser-visible behaviors.
3. Preserve a visible legacy fallback path whenever the feature touches the primary authoring route. React failure must not break the legacy page on `http://localhost:8000`.
4. Treat the workflow graph as canonical UI state. Canvas, DSL editor, property panel, prompt preview inputs, and result views must stay synchronized.
5. Add targeted frontend tests where the stack supports them. If the stack is still being introduced, rely on explicit `agent-browser` checks plus minimal non-watch build/test commands.
6. Validate both happy paths and failure paths: invalid DSL, missing URL/item selector, backend 400/422/500 responses, unsupported legacy compatibility inputs, session-expired responses, and generation-unavailable states.
7. Keep browser checks bounded. Use simple example workflows and small max item/page/step values to avoid stressing the shared backend browser runtime.
8. Run applicable frontend build or test commands, then repo validation commands from `.factory/services.yaml` where relevant to the touched surface.
9. Record exact browser flows, screenshots/observations, request/response outcomes, and any fallback breakage or synchronization drift in the handoff.

## Example Handoff

```json
{
  "salientSummary": "Built the initial React workbench route with canvas, property panel, DSL editor, and a visible link back to the legacy fallback, then wired prompt preview and validation error rendering.",
  "whatWasImplemented": "Added the React workspace shell, synchronized canvas edits with DSL state, surfaced backend validation and prompt preview results, and preserved a user-visible route back to the legacy FastAPI page so fallback behavior remains reachable during takeover.",
  "whatWasLeftUndone": "Node and subflow execution wiring are handled by a later React integration feature.",
  "verification": {
    "commandsRun": [
      {
        "command": "npm run build",
        "exitCode": 0,
        "observation": "React bundle built successfully with the new workbench route."
      }
    ],
    "interactiveChecks": [
      {
        "action": "Open the React workbench, add open_page -> select_list -> extract_field, and edit the URL and selectors in the property panel",
        "observed": "Canvas labels and the DSL editor updated immediately and stayed in sync."
      },
      {
        "action": "Break the DSL JSON and attempt validation",
        "observed": "An inline error appeared and the last valid canvas state remained visible."
      },
      {
        "action": "Use the fallback navigation to open the legacy page on localhost:8000",
        "observed": "Legacy visit/auto-detect/generate controls remained reachable and usable."
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "src/workbench/__tests__/state-sync.test.ts",
        "cases": [
          {
            "name": "invalid_dsl_preserves_last_valid_graph",
            "verifies": "Parse errors do not destroy the last runnable authoring state."
          },
          {
            "name": "fallback_link_stays_visible_on_workbench_route",
            "verifies": "Users can still reach the legacy flow during React takeover."
          }
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- The feature needs a new node type, generation flow, or compatibility behavior not covered by the approved MVP.
- DSL/state synchronization semantics are ambiguous or contradict the mission contract.
- Browser verification reveals systemic backend/session issues that prevent reliable React validation.
- The required fallback route or takeover path needs a product decision that is not already specified in mission artifacts.
