# Extension Bridge Refactor Design

**Date:** 2026-05-07

**Status:** Approved for implementation after spec review

## Goal

Replace the existing Local CDP bridge with the Chrome Extension JSON-RPC bridge described in `docs/extension-bridge.md` and `docs/extension-bridge-scripts.md`, and make Extension the only local browser bridge implementation in the product.

## Scope

This refactor covers:

- Removing the legacy relay-based CDP forwarding path from backend, frontend, package layout, and docs
- Adding a new backend relay and session layer for Chrome Extension driven tab execution
- Updating assist and workflow execution flows to recognize `agent_id="ext:<agentId>"`
- Adding a new `packages/sea-extension` Chrome Extension workspace
- Replacing the frontend `Local CDP` execution environment with `Extension`

This refactor does not cover:

- Reworking the cloud Playwright execution path
- Broad workflow architecture changes unrelated to browser bridge replacement
- New workflow node types or new assist capabilities beyond bridge parity

## Architecture Summary

The system will support two execution backends:

- `cloud`: existing backend-managed Playwright session created by `page_session_mgr`
- `extension`: Chrome Extension managed browser tabs addressed through `agent_id="ext:<agentId>"`

The old `Local CDP` flow will be removed completely. The backend will no longer call `connect_over_cdp`, and the frontend will no longer expose a `local` execution mode.

For Extension execution, the backend will maintain a WebSocket JSON-RPC connection per agent. Workflow and assist requests will translate browser operations into Extension commands such as `new_tab`, `navigate`, and `exec_script`. Extension-injected scripts will run the same DOM-facing JS logic already used by backend extraction helpers wherever practical.

## Target Backend Design

### 1. Relay layer

Add `backend/api/ext_relay.py` as the only browser bridge relay endpoint.

Responsibilities:

- Accept WebSocket connections from extension agents at `/api/ext-relay/agent/{agent_id}`
- Maintain an in-memory registry of active agent connections
- Support request-response matching with per-request IDs
- Route extension events such as `tab_closed` and `tab_navigated`
- Surface timeouts and extension-side failures as actionable backend errors

Remove `backend/api/relay.py` entirely.

### 2. Session layer

Add:

- `backend/runtime/ext_session.py`
- `backend/runtime/ext_session_mgr.py`

`ExtPageSession` will provide a synchronous API that is compatible with current assist and workflow callers where feasible. It will internally bridge synchronous Python calls to the async WebSocket relay using `asyncio.run_coroutine_threadsafe`.

Required `ExtPageSession` capabilities:

- `navigate(url, timeout=...)`
- `evaluate(js)`
- `query_selector_all(selector)`
- `highlight_selector(selector, clear_after_ms=...)`
- `clear_highlight()`
- `auto_detect()`
- `extract_html(selector, max_items=..., include_pagination=...)`
- `test_selector(selector, max_samples=...)`
- `extract_fields(item_selector, fields)`
- `click_element(selector)`
- `scroll_to_bottom()`
- `is_alive()`, `touch()`, `close()`

`ExtSessionManager` will:

- Create a tab-backed session from an active extension agent
- Track `session_id -> ExtPageSession`
- Track `tab_id -> session_id`
- Mark sessions dead when the extension reports tab removal

### 3. Existing browser session manager

`backend/runtime/browser_session.py` will remain the owner of cloud Playwright sessions only.

Required cleanup:

- Remove the `agent_id` branch that currently calls `connect_over_cdp`
- Keep the existing shared browser lifecycle for cloud execution

## Assist Flow Design

`backend/assist/services.py` will support two concrete session types:

- existing Playwright-backed session
- new `ExtPageSession`

### Session resolution

`_ensure_session()` will:

- detect `agent_id` starting with `ext:`
- create a new extension session through `ext_session_mgr`
- preserve current `session_id` reuse behavior where the session is still alive

### Operation routing

The following assist operations must branch on session type:

- `auto_detect()`
- `run_selector_test()`
- `extract_html_fragment()`

For Playwright sessions, keep current behavior.

For extension sessions:

- call `session.auto_detect()` instead of `AutoDetector().detect(session.page)`
- call `session.test_selector()` and `session.highlight_selector()` instead of `SelectorTester` page methods
- call `session.extract_html()` instead of `HtmlExtractor` page methods

API responses must remain stable so the frontend does not need contract changes.

## Workflow Execution Design

`backend/workflow/executor_helpers.py` will become the gateway for choosing the browser backend.

Rules:

- if `agent_id` starts with `ext:`, create a new `ExtPageSession`
- otherwise use existing `page_session_mgr`
- keep existing expired-session handling behavior for stored `session_id`

The rest of workflow execution should continue to operate through the existing runtime abstractions. Any node logic that depends on page-level helpers must use interfaces available on both session types.

## Frontend Design

### Execution mode

Replace the current union:

- `cloud | local`

with:

- `cloud | extension`

Changes required in:

- `frontend/src/app/App.tsx`
- `frontend/src/app/components/WorkbenchToolbar.tsx`
- `frontend/src/features/assist/useAssistWorkbenchActions.ts`
- `frontend/src/features/workflow/useWorkflowActions.ts`

### Agent ID contract

Frontend behavior:

- `cloud`: omit `agent_id`
- `extension`: send `agent_id = "ext:" + userInput`

The frontend will still persist the selected execution mode and agent input in `localStorage`.

### UI wording

Replace:

- `Local CDP`

with:

- `Extension`

No other front-end API shape changes are required.

## Extension Workspace Design

Create a new `packages/sea-extension` package following the structure documented in `docs/extension-bridge-scripts.md`.

Required contents:

- `manifest.json`
- `package.json`
- `vite.config.ts`
- `extract_js.py`
- `src/background/worker.ts`
- `src/background/tab_queue.ts`
- `src/background/rpc.ts`
- `src/scripts/registry.ts`
- generated or maintained script modules for auto-detect, highlight, and HTML extraction
- `src/scripts/builtins.ts`
- `src/popup/popup.html`
- `src/popup/popup.ts`

Key behaviors:

- connect to backend via WebSocket
- auto-reconnect on disconnect
- create and manage tabs on RPC demand
- execute registered injected functions through `chrome.scripting.executeScript`
- emit lifecycle events for tab close and navigation
- allow popup-based configuration of `serverUrl` and `agentId`

## Migration and Deletion Plan

Delete:

- `backend/api/relay.py`
- `packages/local-bridge/`

Update or replace references in:

- `backend/app.py`
- `backend/runtime/browser_session.py`
- frontend execution-mode code
- docs that still describe Local CDP setup

At minimum, `docs/local-bridge.md` must no longer describe the deleted solution. It should either be removed or replaced with extension setup guidance that matches the new implementation.

## Error Handling

The implementation must preserve user-facing clarity for these scenarios:

- Extension not connected: return a friendly backend error explaining that the extension agent must connect first
- Tab closed by the user: mark session dead and return session-expired style errors on next use
- Script timeout: raise a timeout that is surfaced through existing API error pathways
- Invalid selector: return structured selector failure instead of crashing the session
- WebSocket disconnect: extension reconnects automatically; stale backend requests fail cleanly
- Oversized HTML fragment: truncate to the existing 15 KB limit

## Testing Strategy

### Backend

Add or update tests for:

- extension session selection from `agent_id="ext:..."`
- expired or missing extension agent failures
- tab close invalidation behavior
- stable assist response shaping for extension-backed sessions

### Frontend

Add or update tests for:

- execution mode switching to `extension`
- correct `agent_id` prefixing when sending workflow and assist requests
- absence of `agent_id` in cloud mode

### Manual verification

Validate end-to-end with the built extension:

- connect popup to backend
- open page through workflow test
- run selector test and confirm highlight
- run auto detect
- run extract HTML with pagination context
- close the tab and confirm session-expired handling

## Implementation Notes

- Prefer reusing the existing JS extraction logic instead of rewriting detection behavior in TypeScript from scratch
- Keep backend response contracts stable
- Keep the cloud path untouched except for removing the old local bridge branch
- Do not preserve legacy Local CDP code paths behind hidden flags; this refactor intentionally removes them

## Success Criteria

The refactor is complete when:

- the repository no longer depends on `packages/local-bridge`
- the backend no longer exposes `/api/relay/*`
- the backend no longer uses `connect_over_cdp`
- the frontend no longer exposes `Local CDP`
- extension-backed assist and workflow actions work through `ext:` agent IDs
- manual validation confirms parity for the documented bridge scenarios
