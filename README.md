# Sea Data - AI-Powered Web Scraping & Workflow Designer

A dual-interface web scraping tool combining a legacy inspector UI with a modern React-based DSL workflow designer. Supports visual workflow authoring, DSL validation, prompt preview, and bounded execution testing.

## Two Interfaces

| Interface | URL | Purpose |
|-----------|-----|---------|
| **Legacy Inspector** | `http://localhost:8000` | Original page inspection, auto-detection, crawler generation via LLM |
| **React Workbench** | `http://localhost:3101` | Visual DSL workflow designer with canvas, Monaco editor, and execution testing |

Both interfaces share the same FastAPI backend (`server.py`) on port 8000. The React workbench proxies API calls to the backend via Vite's dev server.

---

## Quick Start

### 1. Install Dependencies

```bash
# Using uv (recommended for Python >= 3.13)
uv sync

# Or use the venv directly
.venv\Scripts\pip install -e .
```

### 2. Configure LLM (Optional)

Create or update `.env` in the project root:

```env
API_BASE_URL=http://172.16.2.62:38092/llm-gateway/v1
API_TOKEN=sk-your-token-here
MODEL_NAME=qwen3-30b-a3b-instruct-2507
```

Supported providers: `auto` (reads `.env`), `openai`, `anthropic`, `vllm`.

### 3. Start Backend

```bash
# Option A: Direct Python
python server.py

# Option B: Uvicorn with hot-reload
uvicorn server:app --reload

# Option C: Windows background script (for automation/validation)
powershell -NoProfile -ExecutionPolicy Bypass -File .factory\start_backend.ps1
```

Backend runs at `http://127.0.0.1:8000`.

### 4. Start React Workbench (Optional)

```bash
cd frontend
npm install
npm run dev
```

React workbench runs at `http://127.0.0.1:3101` and proxies `/api` and `/legacy-health` requests to the backend.

---

## Project Structure

```
sea-data/
├── server.py                    # FastAPI entry point, mounts legacy + DSL routers
├── backend/
│   ├── browser_session.py       # Playwright singleton, PageSession, SessionManager
│   ├── legacy_routes.py          # /api/* legacy inspector endpoints
│   ├── legacy_services.py       # Legacy business logic (visit, detect, generate)
│   ├── workflow_routes.py       # /api/workflows/* DSL endpoints
│   ├── workflow_services.py     # DSL validation, conversion, prompt generation
│   ├── workflow_executor.py      # Bounded workflow execution engine
│   ├── workflow_schemas.py       # Pydantic request/response schemas
│   ├── schemas.py               # Legacy Pydantic schemas
│   ├── js_snippets.py           # JavaScript snippets for browser injection
│   └── __init__.py
├── frontend/
│   ├── src/
│   │   ├── App.tsx               # React workbench shell
│   │   ├── App.css               # Workbench styles + compatibility modal
│   │   ├── workflowState.ts      # DSL state management, canvas↔Monaco sync
│   │   ├── main.tsx              # React entry point
│   │   └── index.css
│   ├── vite.config.ts            # Dev server config, proxy to backend
│   ├── package.json
│   └── tsconfig.json
├── extraction/
│   ├── auto_detector.py          # List/pagination auto-detection (JS injection)
│   ├── selector_tester.py        # CSS selector validation
│   └── html_extractor.py         # HTML fragment extraction
├── prompts/
│   └── crawler_prompt.py         # LLM prompt templates for crawler generation
├── tests/
│   ├── test_workflow_api.py      # DSL API endpoint tests
│   ├── test_workflow_dsl_validation.py  # DSL structural validation tests
│   ├── test_workflow_executor.py  # Workflow executor tests
│   ├── test_legacy_api_regression.py   # Legacy API regression tests
│   ├── test_async_bridge.py       # Blocking/async bridge tests
│   └── test_mission_services_manifest.py  # services.yaml test
├── templates/
│   └── index.html               # Legacy inspector HTML (served at /)
├── static/                       # Static assets for legacy UI
├── .factory/
│   ├── start_backend.ps1        # Windows background backend start script
│   └── services.yaml            # Service manifest (ports, commands)
├── llm_client.py                # OpenAI/Anthropic/vLLM client
├── inspector.py                  # Page inspection core
├── main.py                      # CLI entry
└── pyproject.toml               # Python dependencies
```

---

## API Reference

### Legacy Inspector Endpoints (`/api/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/visit` | Navigate to URL and scan elements |
| `POST` | `/api/auto-detect` | Auto-detect list container, fields, pagination |
| `POST` | `/api/test-selector` | Validate a CSS selector against the current page |
| `POST` | `/api/test-fields` | Test extraction fields |
| `POST` | `/api/page-html` | Extract HTML fragment |
| `POST` | `/api/generate-crawler` | Generate Playwright crawler script via LLM |
| `POST` | `/api/picker-enable` | Enable interactive element picker |
| `POST` | `/api/picker-read` | Read picked element |
| `POST` | `/api/picker-disable` | Disable picker |
| `POST` | `/api/clear-highlights` | Remove page highlights |
| `POST` | `/api/session/close` | Close a browser session |
| `POST` | `/api/session/keep-alive` | Keep session alive |

### DSL Workflow Endpoints (`/api/workflows/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/workflows/validate` | Validate a workflow graph structure |
| `POST` | `/api/workflows/from-legacy-config` | Convert legacy config to DSL graph |
| `POST` | `/api/workflows/to-prompt` | Generate crawler prompt from DSL graph |
| `POST` | `/api/workflows/test-node` | Test a single node with prerequisites |
| `POST` | `/api/workflows/test-subflow` | Test a bounded subflow within graph |

---

## DSL Node Types (MVP)

| Node Type | Description |
|-----------|-------------|
| `open_page` | Navigate to URL (`url`, `max_pages`, `max_steps`) |
| `select_list` | Select repeated item container (`item_selector`, `max_items`) |
| `extract_field` | Extract fields from selected items (`fields[]`) |
| `paginate` | Handle pagination (`pagination_selector`, `pagination_strategy`, `max_pages`) |
| `loop` | Bound list iteration (`max_items`) |
| `condition` | Branch by expression (`condition`) |
| `emit_record` | Output extracted record |
| `end` | Stop workflow |

### Example Graph

```json
{
  "nodes": [
    { "id": "open-page-1", "type": "open_page", "data": { "url": "https://quotes.toscrape.com/" } },
    { "id": "select-list-1", "type": "select_list", "data": { "item_selector": ".quote" } },
    { "id": "extract-field-1", "type": "extract_field", "data": { "fields": [{ "name": "text", "selector": ".text", "type": "text" }] } }
  ],
  "edges": [
    { "id": "e1", "source": "open-page-1", "target": "select-list-1" },
    { "id": "e2", "source": "select-list-1", "target": "extract-field-1" }
  ]
}
```

### Extraction Field Types

| Type | Description |
|------|-------------|
| `text` | Inner text content |
| `attr:href` | Link attribute value |
| `attr:src` | Image src attribute |
| `attr:href:abs` | Resolved absolute URL |
| `html` | Inner HTML |
| `all(text)` | All matching texts |
| `all(@href)` | All matching href values |

---

## React Workbench Features

The workbench (port 3101) provides:

- **Visual Canvas** (`@xyflow/react`): Drag-and-drop node graph editing
- **Monaco Editor**: JSON DSL editor with live validation
- **Bidirectional Sync**: Canvas and Monaco editor stay in sync
- **Workflow Actions**:
  - **Validate DSL**: Structural validation against schema
  - **Preview Prompt**: Generate crawler prompt from graph
  - **Run Node Test**: Execute single node with prerequisites
  - **Run Subflow Test**: Execute bounded subflow with execution limits
- **Import Legacy Config**: Modal to paste legacy config and convert to DSL graph
- **Backend Status Banner**: Shows whether backend is reachable
- **Property Panel**: Edit selected node properties
- **Result Panel**: Shows action output (logs, records, raw JSON)

---

## Commands

### Python

```bash
# Run tests
.venv\Scripts\python.exe -m pytest tests\ -v

# Run specific test suite
.venv\Scripts\python.exe -m pytest tests\test_workflow_api.py -v
.venv\Scripts\python.exe -m pytest tests\test_legacy_api_regression.py -v

# Lint / compile check
.venv\Scripts\python.exe -m py_compile server.py backend\workflow_*.py

# Install
.venv\Scripts\pip install -e .
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Development server (port 3101, proxies to backend:8000)
npm run dev

# Production build
npm run build

# TypeScript type check
tsc -b

# Run unit tests (vitest)
npm run test
```

---

## Configuration

### Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE_URL` | (none) | LLM gateway base URL |
| `API_TOKEN` | (none) | LLM API token |
| `MODEL_NAME` | (none) | Model name |
| `PROVIDER` | `auto` | Provider: `auto`, `openai`, `anthropic`, `vllm` |

### Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Backend | 8000 | FastAPI server (legacy UI + API) |
| React Workbench | 3101 | Vite dev server (workflow designer) |

---

## Architecture Notes

### Browser Management

`backend/browser_session.py` manages a singleton Playwright Chromium instance with:
- **Shared context**: All sessions share one browser context (new tabs per session)
- **TTL cleanup**: Sessions auto-expire after 600 seconds of inactivity
- **Thread-safe**: Uses locks for concurrent access

### DSL Workflow Executor

`backend/workflow_executor.py` executes workflow graphs with bounded safety:
- **max_steps**: Bounded loop iterations (prevents infinite loops)
- **max_items**: Limits extracted records
- **max_pages**: Limits pagination
- **Revisit detection**: Skips re-execution when state hasn't advanced

### React↔Backend Communication

The React workbench uses:
- `fetch('/api/workflows/*')` → proxied by Vite to `http://127.0.0.1:8000`
- `fetch('/legacy-health')` → probes whether backend is reachable
- Backend returns structured JSON with logs, records, and error details

### Legacy Compatibility

The system maintains two modes:
1. **Legacy mode**: Direct crawler configuration, LLM script generation
2. **DSL mode**: Visual workflow authoring, execution testing

Users can import legacy configurations into the DSL canvas via the "Import Legacy Config" modal.

---

## Testing

```bash
# All tests (45+ tests)
.venv\Scripts\python.exe -m pytest tests\ -v

# With coverage
.venv\Scripts\python.exe -m pytest tests\ -v --tb=short

# Specific areas
.venv\Scripts\python.exe -m pytest tests\test_workflow_api.py -v
.venv\Scripts\python.exe -m pytest tests\test_workflow_executor.py -v
```

---

## Extraction Syntax (Dex)

Fields use the format `name: selector > extraction_type`:

```
title: h2.product > text
image: img.cover > @src:abs
link: a.detail > @href:abs
tags: ul.tags > li > all(text)
```

### Syntax Summary

| Pattern | Meaning |
|---------|---------|
| `text` | Extract inner text |
| `@attr` | Extract attribute |
| `:abs` | Resolve to absolute URL |
| `:strip` | Strip whitespace |
| `all(text)` | Extract all matches |
| `first(text)` | Extract first match |
| `nth(N, text)` | Extract Nth match |
| `{ sub: sel > text }` | Nested field extraction |

See `PLAN.md` for the full Dex specification.
