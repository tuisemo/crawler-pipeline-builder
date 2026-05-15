/** AuthProvider — React context that restores auth from sessionStorage. */

import { createContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import {
  fetchMe,
  login as apiLogin,
  type AuthUser,
  type AuthStatus,
} from '../services/authApi'
import { clearStoredSessionId, getStoredSessionId, setOnUnauthorized } from '../services/apiClient'

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

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null)
  const [isLoading, setIsLoading] = useState(() => getStoredSessionId() !== null)
  const [authError, setAuthError] = useState<string | null>(null)

  // Restore auth from stored sessionId
  useEffect(() => {
    let cancelled = false
    const sessionId = getStoredSessionId()
    if (!sessionId) {
      return
    }

    fetchMe().then((me) => {
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
    }).catch(() => {
      if (cancelled) return
      setAuthError('登录状态校验失败，请刷新后重试')
      setIsLoading(false)
    })
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
    apiLogin(nextPath ?? currentPath)
  }, [])

  const logoutFn = useCallback(async () => {
    // Use browser redirect to GET /api/auth/logout so the backend can:
    // 1. Delete the local Redis session
    // 2. Notify user-center /public/logout to clean gateway session
    // 3. Redirect browser to the frontend home page
    //
    // CRITICAL: Clear sessionStorage and navigate away BEFORE any React state
    // update. If we call setUser(null) first, React re-renders and RequireAuth
    // detects !isAuthenticated, which calls login() → overwrites
    // window.location.href with /api/auth/login → auto-re-login because SSO
    // session is still active on the user-center domain.
    const sessionId = getStoredSessionId()

    // Clear sessionStorage first so the reloaded app knows there is no session
    clearStoredSessionId()

    // Navigate away immediately — do NOT call setUser/setAuthStatus here
    // because that would trigger a React re-render before navigation completes.
    // Uses a relative path so it works under any deploy sub-path.
    if (sessionId) {
      window.location.href = `./api/auth/logout?sessionId=${encodeURIComponent(sessionId)}`
    } else {
      window.location.href = './api/auth/logout'
    }
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
