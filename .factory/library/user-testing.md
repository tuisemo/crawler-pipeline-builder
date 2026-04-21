# User Testing

Guidance for practical validation during the compatibility-first migration.

## Validation Surface

- Legacy UI: `http://localhost:8000/`
- Legacy API: `/api/visit`, `/api/auto-detect`, `/api/test-selector`, `/api/test-fields`, `/api/page-html`, `/api/generate-crawler`, `/api/picker-*`, `/api/session/*`
- Workflow API: `/api/workflows/validate`, `/api/workflows/from-legacy-config`, `/api/workflows/to-prompt`, `/api/workflows/test-node`, `/api/workflows/test-subflow`
- Planned React workbench: `http://localhost:3101/` once React/Vite exists
- Prompt and script generation: validate prompt preview always; validate real LLM generation only when configuration is available.

## Validation Concurrency

- Browser-backed validation: max concurrent validators = 1
- API-only validation: max concurrent validators = 2 when tests do not share a live browser session
- Rationale: the backend uses shared Playwright browser/session resources and headful desktop execution; concurrent browser tests risk cross-run interference. Pure API checks can run with limited parallelism as long as they do not start overlapping browser-backed execution.

## Minimum Validation Expectations

- Run the available Python test suite when code changes affect backend behavior.
- Smoke `GET /` to confirm the legacy page remains available.
- Smoke critical legacy error contracts, especially blank URL/selector/config rejection paths.
- Smoke workflow validation/conversion/prompt endpoints for DSL behavior.
- For executor changes, validate bounded `test-node` or `test-subflow` behavior with small limits and inspect structured logs/results.
- For React workbench work, validate that React can fall back to legacy-compatible DSL conversion and that the backend legacy page still works.

## React Workbench Testing Semantics

- During development, React should run on `3101` and call the backend on `8000`.
- React failure must not break `GET /` legacy fallback.
- React route testing should cover canvas/DSL synchronization, legacy config import, validation calls, prompt preview, node test, subflow test, and visible degraded state when LLM generation is unavailable.
- Keep browser tests bounded and serial; prefer small example pages and short max item/page limits.

## Accepted Limitations

- Current mission accepts lower-but-real validation rigor, not exhaustive end-to-end automation.
- LLM real generation can be skipped when no valid config is present, but degraded behavior must remain visible and non-crashing.
- Full frontend automation is not required before React assets exist.
- Complex details-page crawling and nested loops are outside MVP user-testing scope.
