# Sea Data

`sea-data` is a DSL-based crawler orchestration workbench. It combines a FastAPI backend, Playwright-backed browser sessions, and a React frontend for visual workflow authoring, bounded execution, and AI-assisted script generation.

## Current Scope

- Workflow DSL validation and graph editing
- Bounded `test-node` / `test-subflow` execution
- Prompt preview, skeleton generation, crawler script generation
- AI assist actions for selector detection, field inference, pagination analysis, and data cleaning
- Editable script and prompt workspaces in the frontend workbench

## Quick Start

### Python backend

```bash
uv sync
python server.py
```

Backend default URL: `http://127.0.0.1:8000`

### React workbench

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3101
```

Frontend default URL: `http://127.0.0.1:3101`

## Key Commands

```bash
# backend tests
.venv\Scripts\python.exe -m pytest tests -v

# frontend tests
cd frontend
npm run test

# frontend build
cd frontend
npm run build
```

## Project Structure

```text
sea-data/
├── server.py                  # FastAPI entrypoint
├── llm_client.py              # OpenAI-compatible LLM client
├── backend/                   # workflow APIs, assist APIs, executor, schemas
├── frontend/                  # React workbench
├── extraction/                # selector and HTML extraction helpers
├── prompts/                   # crawler prompt templates
├── docs/                      # active architecture and UX docs
├── tests/                     # backend and manifest tests
└── .factory/                  # local automation scripts and service manifest
```

## Documentation

- [docs/README.md](/D:/WY-DATASETS/sea-data/docs/README.md)
- [DESIGN.md](/D:/WY-DATASETS/sea-data/DESIGN.md)
- [docs/architecture-review-and-plan.md](/D:/WY-DATASETS/sea-data/docs/architecture-review-and-plan.md)
- [docs/refactor-task-roadmap.md](/D:/WY-DATASETS/sea-data/docs/refactor-task-roadmap.md)
- [docs/ui-ux-multilayer-redesign.md](/D:/WY-DATASETS/sea-data/docs/ui-ux-multilayer-redesign.md)

## Notes

- `GET /` currently returns a simple API message. The main authoring surface is the React workbench.
- Temporary screenshots, debug dumps, and one-off planning notes should not be kept in the repository root.
