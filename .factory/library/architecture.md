# Architecture

Compatibility-first migration guide for `sea-data`: preserve the legacy FastAPI inspector and generation flow while progressively adding a DSL-backed workflow executor and React workbench.

## Current Surfaces

- Legacy UI: `GET /` serves `templates/index.html` from `server.py` and remains the fallback page.
- Legacy API: `backend/legacy_routes.py` exposes `/api/visit`, `/api/auto-detect`, `/api/test-selector`, `/api/test-fields`, `/api/page-html`, `/api/generate-crawler`, `/api/picker-*`, and `/api/session/*`.
- Workflow API: `backend/workflow_routes.py` exposes `/api/workflows/validate`, `/api/workflows/from-legacy-config`, `/api/workflows/to-prompt`, `/api/workflows/test-node`, and `/api/workflows/test-subflow`.
- Browser runtime: `backend/browser_session.py` owns shared Playwright browser/session lifecycle.
- Extraction and prompt helpers: `extraction/*` performs detection/testing/html extraction; `prompts/crawler_prompt.py` builds legacy-compatible crawler prompts.
- Static frontend assets are minimal today; no React/Vite workbench exists yet in the current repo.

## Target Components

- Legacy fallback: existing template UI and legacy endpoints stay black-box compatible during the migration.
- Workflow DSL: canonical graph with nodes, edges, and node data; legacy config converts into this graph through `/api/workflows/from-legacy-config`.
- Workflow executor: Python executor supports bounded `test-node` and `test-subflow` runs with structured logs, node results, sample records, and session-expired reporting.
- React workbench: planned React + TypeScript + Vite UI on port `3101`, with canvas, node palette, property panel, DSL editor, prompt preview, and execution result panes.
- Generation path: prompt preview should work without LLM; real script generation uses LLM only when configured.

## Planned React Route And Fallback Semantics

- Keep `/` as the legacy fallback page until the React workbench is explicitly promoted.
- Mount or proxy the React workbench separately during development, expected at `http://localhost:3101`.
- React must consume existing workflow APIs rather than replacing legacy APIs.
- React should support opening legacy configs by converting them to DSL; unsupported MVP features should warn or degrade rather than breaking fallback.
- If React build/dev server is unavailable, backend legacy UI and APIs must remain usable at `http://localhost:8000`.
- Do not remove or rename legacy endpoint contracts while React is being introduced.

## Compatibility Invariants

- Legacy field config, old UI, old prompt preview, and old generate-crawler flow remain available.
- DSL is the new internal authoring model, but legacy config conversion remains first-class.
- MVP does not require details-page crawling, complex nested loops, database, queue, cache, or external runtime services.
- LLM availability is optional for real generation and must not block validation, prompt preview, or workflow authoring.
- Browser execution must avoid cross-session contamination and preserve inspectable structured output.
