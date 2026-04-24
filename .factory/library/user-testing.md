# User Testing

Guidance for practical validation of the current workflow/API + React workbench stack.

## Validation Surface

- Backend API root: `http://localhost:8000/`
- Workflow API: `/api/workflows/*`
- Assist API: `/api/assist/*`
- React workbench: `http://localhost:3101/`

## Minimum Validation Expectations

- Run backend tests when backend behavior changes
- Run frontend tests/build when workbench behavior changes
- For workflow changes, smoke validation, prompt preview, and bounded execution
- For assist changes, smoke selector extraction or field inference against a small page sample
- For frontend layout changes, verify add-node visibility, property panel behavior, DSL visibility, and result dock behavior in a real browser

## Concurrency Guidance

- Browser-backed validation: max concurrent validators = 1
- API-only validation: limited parallelism is acceptable when no live browser session is involved

## Accepted Limits

- Real LLM generation can be skipped when config is unavailable, but degraded behavior must remain visible and non-crashing
- Complex details-page crawling and deeply nested loop scenarios are still outside the main smoke-test surface
