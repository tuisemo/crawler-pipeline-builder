/**
 * Shared API client — provides a fetch wrapper that:
 *
 * 1. Automatically includes `Authorization: Bearer <sessionId>` from sessionStorage.
 * 2. Detects 401 responses and invokes a registered callback
 *    to clear auth state.
 *
 * Usage:
 *   import { apiFetch } from './apiClient'
 *   const response = await apiFetch('/api/tasks', { method: 'POST', body: ... })
 */

// ── Types ────────────────────────────────────────────────

export type ApiEnvelope = {
  success: boolean
  error_code?: string | null
  error?: string | null
  data?: unknown
}

export const SESSION_STORAGE_KEY = 'crawlerWorkflow.sessionId'
const API_BASE_STORAGE_KEY = 'crawlerWorkflow.apiBase'

// ── Helpers ──────────────────────────────────────────────

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function isApiEnvelope(value: unknown): value is ApiEnvelope {
  if (!isRecord(value)) return false
  return typeof value.success === 'boolean' && Object.prototype.hasOwnProperty.call(value, 'data')
}

// ── 401 handler registry ─────────────────────────────────

let onUnauthorizedCallback: (() => void) | null = null

/**
 * Register a callback that fires when any API call returns 401.
 * Called by AuthProvider on mount.
 */
export function setOnUnauthorized(cb: (() => void) | null): void {
  onUnauthorizedCallback = cb
}

export function getStoredSessionId(): string | null {
  return window.sessionStorage.getItem(SESSION_STORAGE_KEY)
}

export function setStoredSessionId(sessionId: string): void {
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId)
}

export function clearStoredSessionId(): void {
  window.sessionStorage.removeItem(SESSION_STORAGE_KEY)
}

function getStoredApiBase(): string | null {
  return window.sessionStorage.getItem(API_BASE_STORAGE_KEY)
}

function setStoredApiBase(apiBase: string): void {
  window.sessionStorage.setItem(API_BASE_STORAGE_KEY, apiBase)
}

// ── Unauthorized error ───────────────────────────────────

/**
 * Thrown when a request receives a 401 response.
 */
export class UnauthorizedError extends Error {
  constructor() {
    super('Unauthorized — session may have expired')
    this.name = 'UnauthorizedError'
  }
}

// ── Deploy path resolution ──────────────────────────────

/**
 * Derives the deploy base path from the current page URL.
 *
 * HashRouter keeps `window.location.pathname` stable at the deploy
 * directory (e.g. `/<deploy-base>/`). We use it as the prefix for
 * API calls so that a single build works under any sub-path without
 * environment-specific configuration.
 *
 * In local dev (Vite proxy, root path) this returns "".
 */
export function getDeployBase(): string {
  const { pathname } = window.location
  // pathname is "/" for local dev → base is ""
  // pathname is "/<deploy-base>/" for subpath deploys → base is "/<deploy-base>"
  return pathname === "/" ? "" : pathname.replace(/\/$/, "")
}

export function getApiPathCandidates(path: string): string[] {
  if (!path.startsWith('/')) {
    return [path]
  }

  const candidates = new Set<string>()
  const storedBase = getStoredApiBase()
  const deployBase = getDeployBase()

  if (storedBase !== null) {
    candidates.add(`${storedBase}${path}`)
  }
  if (deployBase) {
    candidates.add(`${deployBase}${path}`)
  }
  candidates.add(path)

  return [...candidates]
}

function extractApiBase(candidate: string, path: string): string {
  if (!path.startsWith('/') || !candidate.endsWith(path)) {
    return ''
  }
  return candidate.slice(0, candidate.length - path.length)
}

export async function fetchApiPath(path: string, init?: RequestInit): Promise<Response> {
  const candidates = getApiPathCandidates(path)

  for (let index = 0; index < candidates.length; index += 1) {
    const response = await fetch(candidates[index], init)
    if (response.status !== 404 && path.startsWith('/')) {
      setStoredApiBase(extractApiBase(candidates[index], path))
    }
    if (response.status !== 404 || index === candidates.length - 1) {
      return response
    }
  }

  throw new Error('Unreachable API fetch fallback state')
}

// ── apiFetch ─────────────────────────────────────────────

/**
 * Drop-in replacement for `fetch()` that:
 * - Resolves API paths relative to the deploy base (works under any sub-path)
 * - Adds the stored app session bearer token when present
 * - Detects 401 and fires the onUnauthorized callback
 * - Throws `UnauthorizedError` on 401
 *
 * Returns the raw Response so callers can handle the body
 * themselves.
 */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const sessionId = getStoredSessionId()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(sessionId ? { Authorization: `Bearer ${sessionId}` } : {}),
    ...(init?.headers as Record<string, string> || {}),
  }

  const response = await fetchApiPath(path, {
    ...init,
    headers,
  })

  if (response.status === 401) {
    onUnauthorizedCallback?.()
    throw new UnauthorizedError()
  }

  return response
}
