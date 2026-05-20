/** AuthProvider — React context that restores auth from sessionStorage. */

import { createContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import {
  fetchMe,
  authorize,
  exchangeCode,
  detectOAuthCallback,
  cleanOAuthCallbackParams,
  type AuthUser,
  type AuthStatus,
} from '../services/authApi'
import { clearStoredSessionId, getApiPathCandidates, getStoredSessionId, setStoredSessionId, setOnUnauthorized } from '../services/apiClient'

// ── Context shape ────────────────────────────────────────

export interface AuthState {
  isAuthenticated: boolean
  user: AuthUser | null
  authStatus: AuthStatus | null
  isLoading: boolean
  login: (nextPath?: string) => void
  logout: () => Promise<void>
  authError: string | null
  clearAuthError: () => void
}

const AuthContext = createContext<AuthState | null>(null)

// Exported for useAuth hook — do not consume directly in components.
export { AuthContext }

// ── Provider ─────────────────────────────────────────────

interface AuthProviderProps {
  children: ReactNode
}

let oauthCallbackRequest:
  | { key: string; promise: Promise<Awaited<ReturnType<typeof exchangeCode>>> }
  | null = null

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null)
  const [isLoading, setIsLoading] = useState(() => {
    // Loading if we have a stored session OR an OAuth callback in the URL
    const hasSession = getStoredSessionId() !== null
    const hasCallback = detectOAuthCallback() !== null
    return hasSession || hasCallback
  })
  const [authError, setAuthError] = useState<string | null>(null)

  // Handle OAuth callback (code exchange) or restore session from storage
  useEffect(() => {
    let cancelled = false

    async function initAuth() {
      // Priority 1: Check for OAuth callback in URL (?code=xxx&state=yyy)
      const callback = detectOAuthCallback()
      if (callback) {
        try {
          const requestKey = `${callback.code}:${callback.state}`
          if (!oauthCallbackRequest || oauthCallbackRequest.key !== requestKey) {
            oauthCallbackRequest = {
              key: requestKey,
              promise: exchangeCode(callback.code, callback.state).finally(() => {
                if (oauthCallbackRequest?.key === requestKey) {
                  oauthCallbackRequest = null
                }
              }),
            }
          }

          const result = await oauthCallbackRequest.promise
          if (cancelled) return
          setStoredSessionId(result.session_id)
          setUser(result.user)
          setAuthStatus(result.auth)
          setIsLoading(false)
          // Clean up URL — remove code/state params, keep hash route
          cleanOAuthCallbackParams()
          // Navigate to the stored next_path if not root
          if (result.next_path && result.next_path !== '/') {
            window.location.hash = '#' + result.next_path
          }
        } catch (err) {
          if (cancelled) return
          cleanOAuthCallbackParams()
          setAuthError(err instanceof Error ? err.message : '登录失败，请重试')
          setIsLoading(false)
        }
        return
      }

      // Priority 2: Restore session from sessionStorage
      const sessionId = getStoredSessionId()
      if (!sessionId) {
        return
      }

      try {
        const me = await fetchMe()
        if (cancelled) return
        if (!me) {
          clearStoredSessionId()
          setUser(null)
          setAuthStatus(null)
        } else {
          setUser(me.user)
          setAuthStatus(me.auth)
        }
        setIsLoading(false)
      } catch {
        if (cancelled) return
        setAuthError('登录状态校验失败，请刷新后重试')
        setIsLoading(false)
      }
    }

    initAuth()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setOnUnauthorized(() => {
      clearStoredSessionId()
      setUser(null)
      setAuthStatus(null)
      setIsLoading(false)
    })
    return () => {
      setOnUnauthorized(null)
    }
  }, [])

  const login = useCallback((nextPath?: string) => {
    const currentPath = window.location.hash.replace('#', '') || '/'
    authorize(nextPath ?? currentPath).catch((err) => {
      setAuthError(err instanceof Error ? err.message : '登录失败，请重试')
    })
  }, [])

  const logoutFn = useCallback(async () => {
    // CRITICAL: Clear sessionStorage and navigate away BEFORE any React state
    // update. If we call setUser(null) first, React re-renders and RequireAuth
    // may trigger login() unexpectedly while SSO session is still active.
    const sessionId = getStoredSessionId()

    // Clear sessionStorage first so the reloaded app knows there is no session
    clearStoredSessionId()

    // Best-effort server logout (keepalive) without relying on backend redirects.
    if (sessionId) {
      for (const path of getApiPathCandidates('/api/auth/logout')) {
        void fetch(path, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${sessionId}`,
          },
          keepalive: true,
        }).catch(() => {
          // Ignore network failures; client-side logout must still complete.
        })
      }
    }

    // Force a full-page reload back to the app root so all in-memory auth
    // state is discarded immediately instead of relying on a hash-only
    // navigation that may keep the SPA mounted.
    window.location.replace(window.location.pathname + window.location.search)
  }, [])

  const clearAuthErrorFn = useCallback(() => {
    setAuthError(null)
  }, [])

  const value: AuthState = {
    isAuthenticated: user !== null,
    user,
    authStatus,
    isLoading,
    login,
    logout: logoutFn,
    authError,
    clearAuthError: clearAuthErrorFn,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
