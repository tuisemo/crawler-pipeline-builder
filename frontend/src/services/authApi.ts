/**
 * API client for auth endpoints.
 *
 * All calls go through the shared apiClient which automatically
 * adds the app sessionId bearer token when present.
 */

import { apiFetch, getDeployBase, isRecord, isApiEnvelope, UnauthorizedError, type ApiEnvelope } from './apiClient'

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

export interface AuthorizeResponse {
  authorize_url: string
  state: string
}

export interface TokenExchangeResponse {
  session_id: string
  next_path: string
  user: AuthUser
  auth: AuthStatus
}

const OAUTH_META_STORAGE_KEY = 'crawlerWorkflow.oauthMeta'

function summarizeState(state: string | null | undefined): string {
  if (!state) return 'missing'
  return `${state.substring(0, 12)}...`
}

// ── OAuth callback detection ─────────────────────────────

/**
 * Check whether the current page URL contains an OAuth callback
 * (code + state query params from the user center redirect).
 */
export function detectOAuthCallback(): { code: string; state: string } | null {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  const state = params.get('state')
  if (code && state) {
    return { code, state }
  }
  return null
}

/**
 * Remove OAuth callback query params from the browser URL.
 */
export function cleanOAuthCallbackParams(): void {
  const url = new URL(window.location.href)
  if (url.searchParams.has('code') || url.searchParams.has('state')) {
    url.searchParams.delete('code')
    url.searchParams.delete('state')
    window.history.replaceState(null, '', url.pathname + window.location.hash)
  }
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
 * Initiate the frontend-driven OAuth login flow.
 *
 * 1. Calls POST /api/auth/authorize to get an authorize URL + state.
 * 2. Stores state + nextPath in sessionStorage.
 * 3. Redirects the browser to the user center authorize URL.
 *
 * After the user authenticates, the user center redirects back to
 * the frontend URL with ?code=xxx&state=yyy, which is detected by
 * the AuthProvider on the next page load.
 */
export async function authorize(nextPath: string = '/'): Promise<void> {
  const deployBase = getDeployBase()
  const redirectUri = window.location.origin + deployBase + '/'

  console.info('[auth] authorize: calling POST /api/auth/authorize', {
    redirectUri,
    nextPath,
    deployBase,
  })

  const response = await apiFetch('/api/auth/authorize', {
    method: 'POST',
    body: JSON.stringify({
      next_path: nextPath,
      redirect_uri: redirectUri,
    }),
  })

  const raw: unknown = await response.json().catch(() => ({}))
  const envelope: ApiEnvelope = isApiEnvelope(raw)
    ? raw
    : { success: false, error: 'Invalid response' }

  if (!response.ok || !envelope.success || !isRecord(envelope.data)) {
    console.error('[auth] authorize failed:', { status: response.status, envelope })
    throw new Error((envelope.error as string) || 'Failed to initiate login')
  }

  const data = envelope.data as unknown as AuthorizeResponse

  console.info('[auth] authorize success:', {
    state: summarizeState(data.state),
    authorizeUrl: data.authorize_url?.substring(0, 80) + '...',
  })

  // Persist state and next_path in sessionStorage for CSRF verification
  const oauthMeta = JSON.stringify({ state: data.state, nextPath })
  window.sessionStorage.setItem(OAUTH_META_STORAGE_KEY, oauthMeta)

  // Redirect browser to the user center authorize URL
  window.location.href = data.authorize_url
}

/**
 * Exchange an OAuth authorization code for a session.
 *
 * Called by AuthProvider after detecting ?code=xxx&state=yyy in the URL.
 *
 * IMPORTANT: The `state` parameter from the URL may differ from the one we
 * sent — some OAuth providers (user centers) modify or replace the state.
 * We always use the state we stored in sessionStorage for the backend call,
 * because that's the one stored in Redis. The URL state is only used as a
 * signal that the OAuth flow completed.
 */
export async function exchangeCode(code: string, _urlState: string): Promise<TokenExchangeResponse> {
  // Retrieve the state we stored BEFORE the redirect — this is the one in Redis
  const storedMeta = window.sessionStorage.getItem(OAUTH_META_STORAGE_KEY)
  let nextPath = '/'

  console.info('[auth] exchangeCode called:', {
    codeLength: code?.length,
    urlState: summarizeState(_urlState),
    hasStoredMeta: !!storedMeta,
  })

  if (!storedMeta) {
    throw new Error('登录状态已丢失，请重新登录')
  }

  let backendState: string
  try {
    const parsed = JSON.parse(storedMeta) as { state: string; nextPath: string }
    backendState = parsed.state
    nextPath = parsed.nextPath || '/'

    console.info('[auth] stored state:', {
      storedState: summarizeState(parsed.state),
      urlState: summarizeState(_urlState),
      match: parsed.state === _urlState,
    })

    if (!parsed.state || parsed.state !== _urlState) {
      window.sessionStorage.removeItem(OAUTH_META_STORAGE_KEY)
      throw new Error('登录状态校验失败，请重新登录')
    }
  } catch (error) {
    if (error instanceof Error) {
      throw error
    }
    window.sessionStorage.removeItem(OAUTH_META_STORAGE_KEY)
    throw new Error('登录状态校验失败，请重新登录')
  }

  console.info('[auth] sending state to backend:', summarizeState(backendState))

  const response = await apiFetch('/api/auth/token', {
    method: 'POST',
    body: JSON.stringify({ code, state: backendState }),
  })

  const raw: unknown = await response.json().catch(() => ({}))
  const envelope: ApiEnvelope = isApiEnvelope(raw)
    ? raw
    : { success: false, error: 'Invalid response' }

  if (!response.ok || !envelope.success || !isRecord(envelope.data)) {
    console.error('[auth] token exchange failed:', { status: response.status, envelope })
    throw new Error((envelope.error as string) || 'Login failed')
  }

  const result = envelope.data as unknown as TokenExchangeResponse
  window.sessionStorage.removeItem(OAUTH_META_STORAGE_KEY)
  // Use nextPath from sessionStorage if the backend didn't return one
  if (!result.next_path || result.next_path === '/') {
    result.next_path = nextPath
  }
  return result
}

/**
 * Legacy login — redirects to backend BFF login endpoint.
 * Kept for backward compatibility; prefer `authorize()`.
 */
export function login(nextPath: string = '/'): void {
  window.location.href = `./api/auth/login?next=${encodeURIComponent(nextPath)}`
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
