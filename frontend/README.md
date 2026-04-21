# Frontend - React Workbench

Visual DSL workflow designer powered by React, ReactFlow, and Monaco Editor.

## Quick Start

```bash
npm install
npm run dev    # http://127.0.0.1:3101
npm run build  # Production build
npm run test   # Vitest unit tests
```

## Architecture

- **React 19** + **TypeScript** - UI framework
- **@xyflow/react 12** - Visual node graph canvas
- **@monaco-editor/react 4** - JSON DSL editor with live syntax highlighting
- **Zustand** (available) - State management (currently using React hooks)

## Key Files

| File | Purpose |
|------|---------|
| `src/App.tsx` | Workbench shell, toolbar, canvas, property panel, result area |
| `src/App.css` | All workbench styles + compatibility modal CSS |
| `src/workflowState.ts` | DSL types, canvas↔Monaco sync, graph validation |
| `src/main.tsx` | React entry point |
| `vite.config.ts` | Dev server with `/api` proxy to backend |

## Proxy Configuration

The Vite dev server proxies API calls to the backend:

```
/api/*          → http://127.0.0.1:8000
/legacy-health  → http://127.0.0.1:8000 (returns legacy UI root)
```

## DSL State Management

`workflowState.ts` handles bidirectional sync between:
1. **Canvas state**: ReactFlow nodes and edges
2. **DSL text**: Monaco editor JSON representation
3. **Backend validation**: Real-time validation via `/api/workflows/validate`

### Key Functions

- `toCanonicalGraph()` - Convert canvas state to canonical DSL graph
- `graphToFlowState()` - Convert DSL graph back to canvas state
- `validateGraphShape()` - Parse and validate DSL JSON structure
- `applyDslTextChange()` - Apply Monaco edits with backend validation

## Node Types

| Type | Description |
|------|-------------|
| `open_page` | Navigate to URL |
| `select_list` | Select repeated item container |
| `loop` | Bound list iteration |
| `extract_field` | Extract fields from items |
| `condition` | Conditional branch |
| `paginate` | Pagination handling |
| `emit_record` | Output record |
| `end` | Stop workflow |

## Backend Integration

Workflow actions POST to these endpoints:

| Action | Endpoint | Request |
|--------|----------|---------|
| Validate DSL | `POST /api/workflows/validate` | `{ graph }` |
| Preview Prompt | `POST /api/workflows/to-prompt` | `{ graph }` |
| Run Node Test | `POST /api/workflows/test-node` | `{ graph, node_id, max_items, max_steps }` |
| Run Subflow Test | `POST /api/workflows/test-subflow` | `{ graph, boundary }` |
| Import Legacy | `POST /api/workflows/from-legacy-config` | `{ url, item_selector, fields, ... }` |

## Testing

```bash
npm run test        # Run vitest
npm run test:watch  # Watch mode
```

Test files co-located with source:
- `src/workflowState.test.ts`
