/**
 * Shared API client — provides a fetch wrapper that:
 *
 * 1. Always includes `credentials: 'include'` so the HttpOnly
 *    session cookie is sent with every request (VAL-FE-003).
 * 2. Detects 401 responses and invokes a registered callback
 *    to clear auth state and trigger re-login (VAL-FE-004,
 *    VAL-FLOW-003).
 *
 * Usage:
 *   import { apiFetch } from './apiClient'
 *   const response = await apiFetch('/api/tasks', { method: 'POST', body: ... })
 *
 * The AuthProvider registers an `onUnauthorized` handler on mount
 * so that 401s automatically clear user state and redirect to login.
 */

// ── 401 handler registry ─────────────────────────────────

let onUnauthorizedCallback: (() => void) | null = null

/**
 * Register a callback that fires when any API call returns 401.
 * Called by AuthProvider on mount.
 */
export function setOnUnauthorized(cb: (() => void) | null): void {
  onUnauthorizedCallback = cb
}

// ── Unauthorized error ───────────────────────────────────

/**
 * Thrown when a request receives a 401 response.
 * Callers can catch this specifically if they want to handle
 * auth failures differently from other errors.
 */
export class UnauthorizedError extends Error {
  constructor() {
    super('Unauthorized — session may have expired')
    this.name = 'UnauthorizedError'
  }
}

// ── apiFetch ─────────────────────────────────────────────

/**
 * Drop-in replacement for `fetch()` that:
 * - Always sets `credentials: 'include'`
 * - Detects 401 and fires the onUnauthorized callback
 * - Throws `UnauthorizedError` on 401
 *
 * Returns the raw Response so callers can handle the body
 * themselves (e.g. parse as JSON, read as text, etc.).
 */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const mergedInit: RequestInit = {
    credentials: 'include',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  }

  const response = await fetch(path, mergedInit)

  if (response.status === 401) {
    // Fire the registered callback — this clears auth state
    // and triggers re-login redirect.
    onUnauthorizedCallback?.()
    throw new UnauthorizedError()
  }

  return response
}
