# Repository Guidelines

## Project Overview

`crawler-workflow` is a browser crawler workflow system. It uses FastAPI for workflow and assist APIs, Playwright for browser-backed execution, and a React frontend for visual workflow authoring.

## Project Structure

```text
crawler-workflow/
├── server.py         # FastAPI application entrypoint
├── llm_client.py     # OpenAI-compatible LLM client
├── backend/          # workflow routes, assist routes, executor, schemas
├── frontend/         # React workbench
├── extraction/       # auto-detection and selector/html helpers
├── prompts/          # prompt templates
├── docs/             # active architecture and UX docs
└── tests/            # backend and manifest tests
```

## Build, Test & Development Commands

| Command | Description |
|---------|-------------|
| `uv sync` | Install Python dependencies |
| `python server.py` | Start the FastAPI backend |
| `uvicorn server:app --reload` | Start backend with reload |
| `cd frontend && npm install && npm run dev -- --host 127.0.0.1 --port 3101` | Start the React workbench |
| `.venv\Scripts\python.exe -m pytest tests -v` | Run backend tests |
| `cd frontend && npm run test` | Run frontend tests |
| `cd frontend && npm run build` | Run frontend build/type check |

## Coding Style

- Python version: `>=3.13`
- Prefer explicit Pydantic models for structured data
- Keep workflow API and assist API contracts stable
- Avoid leaving temporary screenshots, response dumps, or stale planning files in the repo root

## Testing Guidelines

- Backend tests live in `tests/`
- Frontend tests live in `frontend/src/*.test.ts`
- For UI changes, validate the React workbench in a real browser after running tests/build

## Architecture Notes

- `server.py` mounts `/api/workflows/*` and `/api/assist/*`
- `backend/browser_session.py` manages Playwright browser and page sessions
- `frontend/src/App.tsx` is the workbench shell for canvas, property panel, result dock, and DSL editor
- `docs/README.md` is the curated index for active repository documentation
