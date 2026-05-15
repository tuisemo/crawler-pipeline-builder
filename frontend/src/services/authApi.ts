/**
 * API client for auth endpoints.
 *
 * All calls go through the shared apiClient which automatically
 * adds the app sessionId bearer token when present.
 */

import { apiFetch, isRecord, isApiEnvelope, UnauthorizedError, type ApiEnvelope } from './apiClient'

// ── Types ────────────────────────────────────────────────

export interface AuthUser {
  id: number
  display_name: string
  external_id: string
  openId: string
  email: string | null
  avatar_url: string | null
}

export interface AuthStatus {
  session_status: string
  token_expires_at: string | null
  needs_refresh_soon: boolean
  has_refresh_token: boolean
}

export interface MeResponse {
  user: AuthUser
  auth: AuthStatus
}

export interface LogoutResponse {
  loggedOut: boolean
}

// ── Public API ───────────────────────────────────────────

/**
 * Fetch the currently authenticated user.
 *
 * Calls `GET /api/auth/me`. Returns the user object when the
 * sessionId is valid, or `null` when unauthenticated (401).
 */
export async function fetchMe(): Promise<MeResponse | null> {
  try {
    const response = await apiFetch('/api/auth/me')

    const raw: unknown = await response.json().catch(() => ({}))
    const envelope: ApiEnvelope = isApiEnvelope(raw)
      ? raw
      : { success: false, error: 'Invalid response' }

    if (!response.ok || !envelope.success || !isRecord(envelope.data)) {
      throw new Error(envelope.error || 'Failed to fetch current user')
    }

    if (!isRecord(envelope.data.user)) {
      throw new Error('Invalid current user payload')
    }
    return envelope.data as unknown as MeResponse
  } catch (error) {
    if (error instanceof UnauthorizedError) {
      return null
    }
    throw error
  }
}

export async function tryFetchMe(): Promise<MeResponse | null> {
  try {
    return await fetchMe()
  } catch {
    return null
  }
}

/**
 * Initiate the login flow.
 *
 * Navigates the browser to the BFF login endpoint which will
 * redirect to the user-center OAuth2 authorize URL.
 */
export function login(nextPath: string = '/'): void {
  window.location.href = `/api/auth/login?next=${encodeURIComponent(nextPath)}`
}

/**
 * Log out the current user.
 *
 * Calls `POST /api/auth/logout` to destroy the server-side session.
 * The frontend should clear its stored sessionId and navigate home.
 */
export async function logout(): Promise<LogoutResponse | null> {
  try {
    const response = await apiFetch('/api/auth/logout', {
      method: 'POST',
    })

    const raw: unknown = await response.json().catch(() => ({}))
    const envelope: ApiEnvelope = isApiEnvelope(raw)
      ? raw
      : { success: false, error: 'Invalid response' }

    if (!envelope.success || !isRecord(envelope.data)) return null

    return envelope.data as unknown as LogoutResponse
  } catch {
    return null
  }
}
