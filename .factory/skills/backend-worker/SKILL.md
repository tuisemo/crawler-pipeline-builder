---
name: backend-worker
description: Build and verify FastAPI, DSL, compatibility, and workflow-executor backend features.
---

# backend-worker

## When to Use This Skill
Use for backend modularization, DSL validation/conversion, workflow execution APIs, legacy adapter work, and generation-path changes.

## Required Skills
- `python-patterns`: use for Python module/service design and clean refactors
- `python-testing`: use when adding backend tests or regression coverage

## Work Procedure
1. Read `mission.md`, `AGENTS.md`, `.factory/library/*.md`, and the assigned feature carefully.
2. Identify the minimum failing backend test or verification needed before implementation; add tests first when practical.
3. Implement through clear service/schema/router boundaries rather than adding new monolith logic.
4. Preserve legacy route behavior unless the feature explicitly changes it.
5. Run scoped backend validation first, then project validation commands from `.factory/services.yaml`.
6. If browser-backed execution is involved, verify session safety and bounded execution semantics.
7. Record exact commands, outputs, and any discovered compatibility risks in the handoff.

## Example Handoff
```json
{
  "salientSummary": "Extracted session and extraction logic into services, added DSL validation endpoint, and kept legacy visit/test endpoints behavior-compatible.",
  "whatWasImplemented": "Created modular backend services and schemas for session lifecycle and workflow validation, added regression coverage for invalid DSL and legacy conversion behavior, and preserved existing route contracts for the legacy flow.",
  "whatWasLeftUndone": "React integration for the new workflow endpoints is not part of this backend feature.",
  "verification": {
    "commandsRun": [
      {"command": ".venv\\Scripts\\python.exe -m pytest tests/test_workflow_validate.py -v", "exitCode": 0, "observation": "DSL validation scenarios passed."},
      {"command": ".venv\\Scripts\\python.exe -m py_compile server.py", "exitCode": 0, "observation": "Server module compiled successfully."}
    ],
    "interactiveChecks": [
      {"action": "POST /api/workflows/validate with missing false branch", "observed": "Returned structured validation error without server crash."}
    ]
  },
  "tests": {
    "added": [
      {"file": "tests/test_workflow_validate.py", "cases": [{"name": "condition_requires_true_false_edges", "verifies": "Invalid graph returns actionable validation errors."}]}
    ]
  },
  "discoveredIssues": []
}
``\

## When to Return to Orchestrator
- The feature requires changing approved DSL semantics or milestone scope
- LLM/provider availability blocks a feature that explicitly requires live generation validation
- Shared browser/session behavior creates a broader architectural issue beyond the assigned feature
