# Architecture

Current architecture summary for `sea-data`.

## Current Surfaces

- Backend API: `server.py` mounts `backend/workflow_routes.py` and `backend/assist_routes.py`
- Workflow API: `/api/workflows/*` covers validation, conversion, prompt generation, plan compilation, bounded execution, skeleton generation, crawler generation, formatting, and saving
- Assist API: `/api/assist/*` covers auto-detect, HTML extraction, field inference, selector optimization, pagination analysis, and data cleaning
- Browser runtime: `backend/browser_session.py` manages Playwright browser and page sessions
- Frontend workbench: `frontend/` contains the React + Vite authoring UI
- Active design and architecture documents live in `README.md`, `DESIGN.md`, and `docs/`

## Active Components

- Workflow DSL as the primary authoring model
- Bounded workflow executor with structured logs and records
- React workbench with canvas, property panel, prompt/script workspaces, and diagnostics dock
- LLM-backed generation and assist actions that degrade gracefully when config is unavailable

## Runtime Semantics

- Backend default URL: `http://127.0.0.1:8000`
- Frontend dev default URL: `http://127.0.0.1:3101`
- `GET /` returns a simple API message; the React workbench is the main authoring surface during development

## Invariants

- DSL is the source of truth for workflow authoring
- Browser-backed execution must remain bounded and observable
- Prompt preview and editor workflows must work even when LLM generation is unavailable
- Temporary screenshots, response dumps, and migration-era notes should not accumulate in the repository root
