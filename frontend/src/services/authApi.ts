/**
 * API client for auth endpoints.
 *
 * All calls include `credentials: 'include'` so the HttpOnly session
 * cookie is sent automatically.  The frontend never sees the
 * user-center access_token — only the BFF session cookie.
 */

// ── Types ────────────────────────────────────────────────

export interface AuthUser {
  id: number
  display_name: string
  external_id: string
  openId: string
  email: string | null
  avatar_url: string | null
}

export interface LogoutResponse {
  logoutUriConfig: Record<string, string>
}

// ── Helpers ──────────────────────────────────────────────

interface ApiEnvelope {
  success: boolean
  error?: string | null
  error_code?: string | null
  data?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function parseEnvelope(raw: unknown): ApiEnvelope {
  if (isRecord(raw) && typeof raw.success === 'boolean') return raw as unknown as ApiEnvelope
  return { success: false, error: 'Invalid response' }
}

// ── Public API ───────────────────────────────────────────

/**
 * Fetch the currently authenticated user.
 *
 * Calls `GET /api/auth/me`.  Returns the user object when the
 * session cookie is valid, or `null` when unauthenticated (401).
 */
export async function fetchMe(): Promise<AuthUser | null> {
  try {
    const response = await fetch('/api/auth/me', { credentials: 'include' })
    if (response.status === 401) return null

    const raw: unknown = await response.json().catch(() => ({}))
    const envelope = parseEnvelope(raw)
    if (!envelope.success || !isRecord(envelope.data)) return null

    const user = (envelope.data as Record<string, unknown>).user
    if (!isRecord(user)) return null
    return user as unknown as AuthUser
  } catch {
    return null
  }
}

/**
 * Initiate the login flow.
 *
 * Navigates the browser to the BFF login endpoint which will
 * redirect to the user-center OAuth2 authorize URL.  The `next`
 * parameter tells the BFF where to redirect after successful
 * authentication.
 */
export function login(nextPath: string = '/'): void {
  window.location.href = `/api/auth/login?next=${encodeURIComponent(nextPath)}`
}

/**
 * Log out the current user.
 *
 * Calls `POST /api/auth/logout` to destroy the server-side session
 * and clear the cookie, then returns the logoutUriConfig for
 * user-center redirect.
 */
export async function logout(): Promise<LogoutResponse | null> {
  try {
    const response = await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    })

    const raw: unknown = await response.json().catch(() => ({}))
    const envelope = parseEnvelope(raw)
    if (!envelope.success || !isRecord(envelope.data)) return null

    return envelope.data as unknown as LogoutResponse
  } catch {
    return null
  }
}
