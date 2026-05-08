# Stateless Workbench Bridge Design

Date: 2026-05-08
Status: Approved in chat, pending user review of written spec
Scope: Phase 1 vertical slice for workbench assist interactions

## Summary

This design defines the first implementation phase of the Sea Data stateless architecture refactor. The goal is to replace the current backend-mediated browser control path with a direct frontend-to-extension path for workbench assist interactions, while keeping the backend focused on pure computation and LLM analysis.

Phase 1 is intentionally narrow. It does not attempt to delete every legacy execution path up front. Instead, it cuts over the most important assist workflow first, validates the new boundaries in a real browser, and only then unlocks larger cleanup.

## Product Decisions

- The first phase targets local development only.
- The supported browser environment is Chrome or Chromium with an unpacked extension.
- The workbench acts on the current active tab only.
- Backward compatibility with the old workbench execution flow is not a goal.
- The first vertical slice must fully support:
  - selector test
  - selector highlight
  - HTML extraction for item samples
  - pagination context extraction
  - pagination analysis via backend LLM API

## Problem Statement

The current architecture still mixes three responsibilities:

- The frontend orchestrates assist actions.
- The backend owns runtime session state and browser mediation.
- The extension speaks WebSocket relay RPC to the backend.

This creates unnecessary state coupling, slower feedback loops, and a fragile chain for actions that should be local and immediate. It also keeps outdated concepts alive in the workbench UI, such as execution mode switching, agent IDs, and workflow test actions that are being removed from the product direction.

## Goals

- Make workbench assist interactions run through a direct frontend-to-extension channel.
- Remove backend responsibility for driving browser state during the workbench phase.
- Preserve a thin backend API for pure text analysis where LLMs are still useful.
- Reduce UI and codebase concepts to the new intended model instead of preserving obsolete compatibility.
- Establish stable message contracts that can be extended later without another rewrite.

## Non-Goals

- Full deletion of every runtime, relay, and executor artifact in this phase.
- Extension marketplace readiness.
- Multi-browser support.
- Multi-tab targeting or explicit tab management.
- Retry orchestration, reconnect loops, or a general event bus.
- Reworking every assist action in one pass.

## Proposed Architecture

The system is split into three explicit responsibilities:

### Frontend

The frontend owns user interaction, workflow state updates, and presentation of assist results. It does not manage browser sessions, relay connections, agent IDs, or backend browser state. It talks to the extension through a typed local bridge and talks to the backend only for pure computation endpoints.

### Browser Extension

The extension is the only layer allowed to touch the live DOM of the current page. It receives requests from the frontend, executes page scripts against the current active tab, and returns normalized results. It does not maintain a WebSocket connection to the backend.

### Backend

The backend provides pure HTTP APIs for LLM-backed analysis. For Phase 1, the key remaining assist endpoint is pagination analysis. The backend receives HTML evidence from the frontend and returns analysis results. It does not fetch, navigate, or inspect the live page on behalf of the frontend.

## Phase 1 Data Flow

### Selector Test

1. The user clicks a selector test action in the workbench.
2. The frontend calls `extensionBridge.testSelector`.
3. The extension resolves the current active tab.
4. The extension executes selector query and highlight scripts in that tab.
5. The extension returns a normalized result with match counts and any structured error.
6. The frontend shows feedback and does not contact the backend.

### Pagination Analysis

1. The user clicks pagination analysis in the workbench.
2. The frontend calls `extensionBridge.extractPaginationContext`.
3. The extension returns:
   - item sample HTML when available
   - pagination component HTML when found
   - pruned body HTML
4. The frontend constructs the backend payload from those fields and posts it to `/api/assist/analyze-pagination`.
5. The backend performs text-only analysis and returns:
   - `pagination_strategy`
   - `next_button_selector`
   - reason and confidence fields
6. The frontend applies the result to the selected workflow node.

## Component Design

### `frontend/src/features/runtime/extensionBridge.ts`

This file becomes the canonical frontend SDK for extension access. It must hide raw `chrome.runtime.sendMessage` behavior and expose typed methods:

- `detectExtension()`
- `testSelector({ selector, clearAfterMs })`
- `highlightSelector({ selector, clearAfterMs })`
- `extractHtml({ itemSelector, maxItems })`
- `extractPaginationContext({ itemSelector, maxItems })`

It is responsible for:

- timeout control
- unavailable extension handling
- normalization of response envelopes
- stable frontend-facing error codes

### `packages/browser-bridge-extension/src/background/worker.ts`

This file becomes a local command executor rather than a relay client. It listens through `chrome.runtime.onMessageExternal`, validates action names, resolves the current active tab, executes registered page scripts, and returns a standard response envelope.

The extension should support this request shape:

```ts
type ExtensionRequest =
  | { type: 'SEA_RPC'; action: 'ping' }
  | { type: 'SEA_RPC'; action: 'testSelector'; payload: { selector: string; clearAfterMs?: number; maxSamples?: number } }
  | { type: 'SEA_RPC'; action: 'highlightSelector'; payload: { selector: string; clearAfterMs?: number } }
  | { type: 'SEA_RPC'; action: 'extractHtml'; payload: { itemSelector: string; maxItems?: number } }
  | { type: 'SEA_RPC'; action: 'extractPaginationContext'; payload: { itemSelector?: string; maxItems?: number } }
```

The extension should return:

```ts
type ExtensionResponse<T> =
  | { ok: true; data: T }
  | { ok: false; error: { code: string; message: string } }
```

For pagination extraction, the success payload should expose separate named fields rather than one opaque blob. The intended shape is:

```ts
type PaginationContextResult = {
  htmlFragment: string
  paginationComponentHtml: string
  prunedBodyHtml: string
  itemCount: number
}
```

The frontend may preserve these fields separately in memory, but the backend request must always include `html_fragment` and `pruned_body_html` explicitly.

### `frontend/src/features/assist/useAssistWorkbenchActions.ts`

This hook stops orchestrating browser actions through the backend for the Phase 1 flow. It should:

- switch selector test to extension-first execution
- switch pagination analysis to extension extraction plus backend analysis
- centralize frontend error handling for extension failures
- prepare HTML extraction reuse so later assist actions can move without another structural rewrite

`infer-fields` and `optimize-selector` are outside the required vertical slice, but their HTML acquisition path should be shaped so they can migrate to extension extraction next.

### Backend pagination analysis

`backend/api/assist_routes.py` and `backend/assist/services.py` should treat pagination analysis as a pure text-analysis endpoint. The request contract should carry extracted evidence directly instead of session metadata.

Minimum intended request fields:

- `html_fragment`
- `pruned_body_html`
- optional `pagination_component_html`
- optional `item_selector`

The backend must not:

- load or create browser sessions
- validate against a live page
- depend on `session_id`
- depend on `agent_id`

## UI Changes

Phase 1 also removes outdated workbench concepts from the user-facing interface:

- remove execution mode switching between cloud and extension
- remove agent ID input
- remove node test action
- remove subflow test action
- replace connection UI with a simple extension-ready state

The workbench should present the extension as the default and only local acceleration path for assist operations.

## Error Handling

The frontend-extension contract should normalize failures into a small fixed set:

- `extension_not_installed`
- `extension_unreachable`
- `no_active_tab`
- `script_execution_failed`
- `invalid_selector`
- `timeout`

Rules:

- The extension returns structured errors, not raw stack traces.
- The frontend maps those errors into concise user-facing messages.
- Pagination analysis backend errors stay focused on invalid input, oversize input, or model response failure.
- Phase 1 does not add automatic retries.

## Rollout Strategy

Phase 1 should be implemented in this order:

1. Convert the extension background worker from relay RPC to local RPC.
2. Build the typed frontend extension bridge.
3. Move selector test and pagination analysis to the new path.
4. Simplify the workbench UI around extension-only behavior.
5. Shrink the backend pagination endpoint to pure analysis.
6. After the vertical slice is stable, remove legacy workbench runtime and test endpoints in a follow-up cleanup phase.

This order keeps risk low because the main user path is validated before the broader deletion work begins.

## Acceptance Criteria

- Testing a selector produces no backend network request.
- Selector highlight appears on the current active page with near-immediate feedback.
- Pagination analysis produces exactly one backend request to `/api/assist/analyze-pagination`.
- That request contains extracted HTML evidence rather than `session_id` or `agent_id`.
- The workbench no longer exposes cloud versus extension mode switching.
- The workbench no longer exposes node test or subflow test actions.
- When the extension is missing, the UI shows a clear blocked state instead of failing silently.

## Risks And Mitigations

### Local URL authorization mismatch

Risk: the extension `externally_connectable.matches` list may not align with the actual frontend dev URL.

Mitigation: explicitly verify the local workbench URL used in development, with `127.0.0.1:3101` treated as the primary supported address in Phase 1.

### Wrong active tab

Risk: the user may trigger an assist action while a different tab is active.

Mitigation: make the active-tab assumption explicit in the workbench UX and error messaging. Do not add hidden tab discovery in this phase.

### Oversized HTML evidence

Risk: pagination analysis prompts may become too large.

Mitigation: keep pruning and truncation inside the extension extraction layer and keep backend request sizes bounded by design.

## Deferred Cleanup

These items are intentionally deferred until after the Phase 1 vertical slice is working:

- remove backend relay routes
- remove backend runtime session management
- remove workflow executor node-test and subflow-test paths
- delete obsolete extension WebSocket relay files
- remove stale tests that only validate the old runtime path

This keeps the first cutover focused and makes later deletion safer.

## Success Definition

Phase 1 is successful when the workbench can complete selector testing and pagination analysis through a frontend-to-extension direct path, with the backend used only for HTML-based LLM analysis and no runtime browser state living on the server.
