# Environment

Worker-facing environment notes for local development, validation, and migration work.

## Runtime

- Repo root: `D:\WY-DATASETS\sea-data`
- Python project: Python `>=3.13`, using the repo `.venv` when available.
- Backend entrypoints: `python server.py` or `uvicorn server:app --reload`.
- Backend default URL: `http://localhost:8000`
- Planned React dev URL: `http://localhost:3101`
- Current repo has no React/Vite assets yet; treat `3101` as reserved for future workbench development.

## Dependencies And Services

- Backend stack: FastAPI, Playwright, Pydantic, BeautifulSoup, requests, uvicorn.
- Browser automation is managed by the backend through Playwright and shared session state.
- No database, message queue, cache, or separate worker service is required for MVP.
- Do not introduce new infrastructure unless the mission scope changes.

## LLM Configuration

- Existing `.env` may provide LLM settings for real crawler script generation.
- LLM-backed generation is optional for validation; prompt preview and workflow APIs should remain usable without a working model.
- If LLM config is missing or unavailable, verify degraded behavior and JSON error handling rather than blocking the mission.

## Environment Limitations

- Browser-backed validation should run serially because the backend uses shared Playwright browser/session resources.
- Desktop/headful browser behavior may vary by machine; prefer bounded smoke checks over broad concurrent browser runs.
- Current validation rigor is intentionally lower-but-real: verify backend tests, key APIs, and one browser/UI smoke where applicable.
- Ports `8000` and `3101` are the mission defaults; avoid adding alternate services unless explicitly required.
