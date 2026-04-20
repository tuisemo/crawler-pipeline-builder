# Architecture

How the system works: legacy FastAPI inspection flow remains available while a React workbench, modular FastAPI services, and a Python workflow executor are introduced behind a compatibility-first DSL layer.

## Major components
- Legacy UI and routes: existing visit/detect/test/generate flow remains as fallback and regression baseline.
- Modular FastAPI API layer: feature-grouped routers for sessions, inspection, extraction, workflows, generation, and legacy compatibility.
- Workflow DSL: canonical graph model with nodes, edges, metadata, and conversion from legacy config.
- Workflow executor: scoped node/subflow execution over Playwright-backed browser sessions, with structured logs/results.
- React workbench: visual canvas, DSL editor, property panel, and results surface synchronized to one canonical workflow state.

## Invariants
- Legacy fallback must stay usable throughout migration.
- DSL is the canonical representation for new workflow authoring.
- Browser-backed validation is serialized to avoid shared-context interference.
- LLM unavailability must not block workflow authoring/testing.
