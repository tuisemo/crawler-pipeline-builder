/**
 * AuthProvider — React context that loads auth state on mount.
 *
 * On mount it calls `GET /api/auth/me` via `fetchMe()`.  If the
 * session cookie is valid the user object is stored in context;
 * otherwise the state is unauthenticated.
 *
 * The `useAuth()` hook exposes: isAuthenticated, user, login,
 * logout, isLoading.
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
 */

import { createContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react'
import { fetchMe, login as apiLogin, logout as apiLogout, type AuthUser } from '../services/authApi'
import { setOnUnauthorized } from '../services/apiClient'

// ── Context shape ────────────────────────────────────────

export interface AuthState {
  isAuthenticated: boolean
  user: AuthUser | null
  isLoading: boolean
  login: (nextPath?: string) => void
  logout: () => Promise<void>
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
  // Use a ref so the 401 callback always reads the latest login function
  const loginRef = useRef<(nextPath?: string) => void>(undefined as unknown as (nextPath?: string) => void)

  useEffect(() => {
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

  const value: AuthState = {
    isAuthenticated: user !== null,
    user,
    isLoading,
    login,
    logout: logoutFn,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ── Hook ─────────────────────────────────────────────────
// useAuth is defined in useAuth.ts to satisfy react-refresh/only-export-components.
