/**
 * AuthProvider — React context that loads auth state on mount.
 *
 * On mount it calls `GET /api/auth/me` via `fetchMe()`.  If the
 * session cookie is valid the user object is stored in context;
 * otherwise the state is unauthenticated.
 *
 * The `useAuth()` hook exposes: isAuthenticated, user, login,
 * logout, isLoading, authError, clearAuthError.
 *
 * Design notes (VAL-FE-006):
 *   - No access_token is ever stored in JS.  Auth state comes
 *     exclusively from the HttpOnly session cookie validated by
 *     `/api/auth/me`.
 *   - On page refresh the provider re-checks `/api/auth/me`,
 *     so login state persists as long as the cookie is valid
 *     (VAL-FE-008).
 *
 * 401 handling (VAL-FE-004, VAL-FLOW-003):
 *   - The provider registers an `onUnauthorized` callback with
 *     the shared apiClient.  When any API call returns 401, the
 *     callback clears user state and triggers the login redirect
 *     so the user can re-authenticate and return to their page.
 *
 * User-center error handling (VAL-FLOW-008):
 *   - On mount, the provider checks URL query parameters for
 *     `auth_error` which the backend may set when the OAuth
 *     callback fails.  The error is stored in context so the
 *     UI can display a friendly Chinese message.
 */

import { createContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react'
import { fetchMe, login as apiLogin, logout as apiLogout, type AuthUser } from '../services/authApi'
import { setOnUnauthorized } from '../services/apiClient'

// ── Auth error messages (Chinese) ────────────────────────

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  invalid_oauth_callback: '登录回调参数异常，请重试',
  invalid_oauth_state: '登录状态已过期，请重新登录',
  user_center_unavailable: '登录服务暂不可用，请稍后重试',
  access_denied: '授权被拒绝，请重试',
  account_disabled: '账号已被禁用，请联系管理员',
  default: '登录失败，请重试',
}

function getAuthErrorMessage(errorCode: string | null): string | null {
  if (!errorCode) return null
  return AUTH_ERROR_MESSAGES[errorCode] ?? AUTH_ERROR_MESSAGES.default
}

// ── Context shape ────────────────────────────────────────

export interface AuthState {
  isAuthenticated: boolean
  user: AuthUser | null
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

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [authError, setAuthError] = useState<string | null>(null)
  // Use a ref so the 401 callback always reads the latest login function
  const loginRef = useRef<(nextPath?: string) => void>(undefined as unknown as (nextPath?: string) => void)

  useEffect(() => {
    // Check for auth error in URL query params (from OAuth callback failure)
    const params = new URLSearchParams(window.location.search)
    const errorCode = params.get('auth_error')
    if (errorCode) {
      setAuthError(getAuthErrorMessage(errorCode))
      // Clean up the URL to prevent the error from showing on refresh
      const url = new URL(window.location.href)
      url.searchParams.delete('auth_error')
      window.history.replaceState({}, '', url.pathname + url.search)
    }

    let cancelled = false
    fetchMe().then((u) => {
      if (!cancelled) {
        setUser(u)
        setIsLoading(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback((nextPath?: string) => {
    apiLogin(nextPath ?? window.location.pathname)
  }, [])

  // Keep the ref in sync with the latest login function
  useEffect(() => {
    loginRef.current = login
  }, [login])

  // Register the 401 handler with apiClient so that any API call
  // returning 401 automatically clears auth state and triggers
  // re-login (VAL-FE-004, VAL-FLOW-003).
  useEffect(() => {
    setOnUnauthorized(() => {
      setUser(null)
      // Redirect to login with the current page as the return path
      loginRef.current?.()
    })
    return () => {
      setOnUnauthorized(null)
    }
  }, [])

  const logoutFn = useCallback(async () => {
    const result = await apiLogout()
    setUser(null)
    // If the backend returned a user-center logout URL, redirect there;
    // otherwise go to the app homepage.
    if (result?.logoutUriConfig?.default) {
      window.location.href = result.logoutUriConfig.default
    } else {
      window.location.href = '/'
    }
  }, [])

  const clearAuthErrorFn = useCallback(() => {
    setAuthError(null)
  }, [])

  const value: AuthState = {
    isAuthenticated: user !== null,
    user,
    isLoading,
    login,
    logout: logoutFn,
    authError,
    clearAuthError: clearAuthErrorFn,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ── Hook ─────────────────────────────────────────────────
// useAuth is defined in useAuth.ts to satisfy react-refresh/only-export-components.
