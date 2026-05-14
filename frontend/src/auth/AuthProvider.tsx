/** AuthProvider — React context that restores auth from sessionStorage. */

import { createContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import {
  fetchMe,
  login as apiLogin,
  logout as apiLogout,
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
    // Call backend to delete server-side session first
    const result = await apiLogout()

    // Only clear local state after the backend confirms logout (or if it fails, clear anyway)
    clearStoredSessionId()
    setUser(null)
    setAuthStatus(null)

    // If user center returned a logout URL, redirect there; otherwise go home
    if (result?.logoutUriConfig) {
      const urls = Object.values(result.logoutUriConfig)
      if (urls.length > 0) {
        window.location.href = urls[0]
        return
      }
    }
    window.location.href = window.location.origin + window.location.pathname
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
