---
name: backend-worker
description: Build and verify FastAPI, DSL, compatibility, and workflow-executor backend features.
---

# backend-worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the work procedure.

## When to Use This Skill

Use for backend modularization, legacy compatibility contracts, workflow schema validation, legacy-to-DSL conversion, prompt preview endpoints, workflow executor features, and backend generation-path changes.

## Required Skills

- `python-patterns`: use when reshaping Python services, routers, schemas, or executor code so the design stays modular and idiomatic.
- `python-testing`: use before and during implementation to define failing backend tests first and keep coverage targeted to the assigned contract.
- `agent-browser`: invoke only when the assigned backend feature changes browser-observable behavior that cannot be trusted from API tests alone.

## Work Procedure

1. Read `mission.md`, mission `AGENTS.md`, `.factory/services.yaml`, and `.factory/library/*.md` before editing code.
2. Map the assigned feature to the exact validation assertion IDs it fulfills and restate those behaviors in your own words before coding.
3. Add failing backend tests first when the repo supports it. Prefer targeted `pytest` tests for route contracts, schema validation, executor result shapes, and compatibility behavior.
4. Preserve legacy route behavior unless the feature explicitly changes that contract. If you must change a legacy contract, stop and return to the orchestrator.
5. Implement through clear module boundaries. Prefer routers, schemas, services, and executor helpers over adding new monolithic logic to `server.py`.
6. When touching workflow execution, verify all bounds and safety rules the feature claims: required node data, step/item/page limits, session-expired behavior, partial failure preservation, and structured logs/results.
7. When touching prompt preview or generation, keep LLM-unavailable behavior non-blocking for authoring/test flows and preserve JSON error contracts.
8. Run feature-scoped tests first, then repo validation commands from `.factory/services.yaml`. If the feature changes browser-visible behavior, add one bounded live smoke or `agent-browser` check.
9. Record exact commands, observed results, assertion coverage, and any discovered compatibility risks in the handoff. Vague statements like "tested it" are not acceptable.

## Example Handoff

```json
{
  "salientSummary": "Tightened workflow validation to reject dangling edges and duplicate node ids, and updated prompt preview to derive fields only from the runnable path.",
  "whatWasImplemented": "Added failing pytest coverage for disconnected graphs, duplicate ids, and unsupported node types; updated workflow validation and prompt preview logic so invalid or ambiguous graphs now fail with structured errors while legacy routes remain unchanged.",
  "whatWasLeftUndone": "React workbench wiring for the new validation errors is handled by a separate frontend feature.",
  "verification": {
    "commandsRun": [
      {
        "command": ".venv\\Scripts\\python.exe -m pytest tests/test_workflow_api.py -v",
        "exitCode": 0,
        "observation": "Workflow API validation and prompt preview cases passed, including the new invalid-graph checks."
      },
      {
        "command": ".venv\\Scripts\\python.exe -m pytest tests/test_legacy_api_regression.py -v",
        "exitCode": 0,
        "observation": "Legacy fallback regression tests still passed after backend changes."
      },
      {
        "command": ".venv\\Scripts\\python.exe -m py_compile server.py inspector.py llm_client.py main.py backend/workflow_routes.py backend/workflow_executor.py",
        "exitCode": 0,
        "observation": "Python modules compiled successfully."
      }
    ],
    "interactiveChecks": [
      {
        "action": "POST /api/workflows/validate with a graph containing a dangling edge",
        "observed": "Returned a structured validation error instead of accepting the graph."
      },
      {
        "action": "POST /api/workflows/to-prompt using a disconnected extract_field node",
        "observed": "Prompt preview rejected the graph as non-runnable instead of generating a misleading prompt."
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "tests/test_workflow_api.py",
        "cases": [
          {
            "name": "validate_rejects_dangling_edges",
            "verifies": "Graphs with edges pointing to missing nodes fail validation."
          },
          {
            "name": "to_prompt_rejects_disconnected_extract_path",
            "verifies": "Prompt preview only derives output from a runnable workflow path."
          }
        ]
      }
    ]
  },
  "discoveredIssues": [
    {
      "severity": "medium",
      "description": "Workflow test responses still do not return a new session id when one is created implicitly, so frontend recovery remains constrained.",
      "suggestedFix": "Add session id propagation in executor response schemas and wire it in the React client feature."
    }
  ]
}
```

## When to Return to Orchestrator

- The feature requires changing approved DSL semantics, milestone scope, or fallback route ownership.
- LLM/provider availability blocks a feature that explicitly requires live generation validation.
- Shared browser/session behavior creates a broader architectural issue beyond the assigned feature.
- The contract implies support for an MVP node type or compatibility behavior that the current milestone cannot implement without scope renegotiation.
