# User Testing

## Validation Surface
- Legacy browser UI at `http://localhost:8000`
- Future React workbench UI )development expected on `http://localhost:3101`)
- FastAPI endpoints for sessions, inspection, extraction, workflows, and generation

## Validation Concurrency
- Browser-backed validation: max concurrent validators = 1
- Rationale: shared Playwright browser/context and headful desktop execution create high cross-run interference risk.

## Notes
- Prefer browser automation for UI assertions and curl/API verification for backend assertions.
- Treat LLM generation as degraded-capable; do not block authoring/testing on model availability.
