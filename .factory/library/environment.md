# Environment

Worker-facing environment notes for local development and validation.

## Runtime

- Repo root: `D:\WY-DATASETS\sea-data`
- Python version: `>=3.13`
- Backend entrypoints: `python server.py` or `uvicorn server:app --reload`
- Backend default URL: `http://localhost:8000`
- Frontend dev default URL: `http://localhost:3101`

## Dependencies And Services

- Backend stack: FastAPI, Playwright, Pydantic, BeautifulSoup, requests, uvicorn
- Frontend stack: React, Vite, Ant Design, React Flow, Monaco
- Browser automation is managed by the backend through Playwright-backed page sessions
- No database, queue, or external worker service is required for the current local workflow

## LLM Configuration

- `.env` may provide `API_BASE_URL`, `API_TOKEN`, `MODEL_NAME`, and optional `PROVIDER`
- LLM-backed generation is optional for validation; prompt preview and UI authoring should remain usable without a working model

## Validation Limits

- Browser-backed checks should run serially
- API-only checks can run with limited parallelism as long as they do not overlap browser-backed execution
