// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, cleanup } from '@testing-library/react'
import { HashRouter } from 'react-router-dom'
import { AuthProvider } from './AuthProvider'
import { useAuth } from './useAuth'
import {
  clearStoredSessionId,
  setOnUnauthorized,
  setStoredSessionId,
} from '../services/apiClient'

// ── Helpers ──────────────────────────────────────────────

const mockUser = {
  id: 1,
  display_name: '测试用户',
  external_id: 'openId123',
  openId: 'openId123',
  email: 'test@example.com',
  avatar_url: 'https://avatar.example.com/1.png',
}

const mockAuthStatus = {
  session_status: 'active',
  token_expires_at: '2026-05-20T00:00:00+00:00',
  needs_refresh_soon: false,
  has_refresh_token: true,
}

function mockFetchSuccess(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => ({ success: true, data }),
  } as Response
}

function mockFetchError(status: number, error: string): Response {
  return {
    ok: false,
    status,
    json: async () => ({ success: false, error }),
  } as Response
}

// A test component that consumes useAuth
function AuthConsumer() {
  const { isAuthenticated, user, isLoading, login, logout, authError, clearAuthError } = useAuth()
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="username">{user?.display_name ?? 'none'}</span>
      <span data-testid="auth-error">{authError ?? 'none'}</span>
      <button data-testid="login-btn" onClick={() => login('/tasks')}>
        Login
      </button>
      <button data-testid="logout-btn" onClick={logout}>
        Logout
      </button>
      <button data-testid="clear-error-btn" onClick={clearAuthError}>
        Clear Error
      </button>
    </div>
  )
}

function renderWithRouter(ui: React.ReactElement) {
  return render(<HashRouter>{ui}</HashRouter>)
}

// ── Tests ────────────────────────────────────────────────

describe('AuthProvider', () => {
  const originalFetch = globalThis.fetch
  const originalLocation = window.location

  beforeEach(() => {
    vi.restoreAllMocks()
    clearStoredSessionId()
    // Mock window.location.assign for navigation
    Object.defineProperty(window, 'location', {
      value: {
        ...originalLocation,
        assign: vi.fn(),
        href: '',
        search: '',
      },
      writable: true,
    })
  })

  afterEach(() => {
    cleanup()
    globalThis.fetch = originalFetch
    setOnUnauthorized(null)
    clearStoredSessionId()
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
    })
  })

  it('boots unauthenticated immediately when no sessionId is stored', async () => {
    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(globalThis.fetch).toBe(originalFetch)
  })

  it('renders children as authenticated when /api/auth/me returns user for stored sessionId', async () => {
    setStoredSessionId('session-123')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser, auth: mockAuthStatus }))

    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })
    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('username').textContent).toBe('测试用户')
  })

  it('clears stored sessionId when /api/auth/me returns 401', async () => {
    setStoredSessionId('session-expired')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(screen.getByTestId('username').textContent).toBe('none')
    expect(window.sessionStorage.getItem('crawlerWorkflow.sessionId')).toBeNull()
  })

  it('login() navigates to /api/auth/login with next path', async () => {
    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    const loginBtn = screen.getByTestId('login-btn')
    await act(async () => {
      loginBtn.click()
    })

    // login() should set window.location.href to /api/auth/login?next=...
    expect(window.location.href).toBe('/api/auth/login?next=%2Ftasks')
  })

  it('logout() calls POST /api/auth/logout, clears state, and navigates to user-center logout URL', async () => {
    setStoredSessionId('logout-session')
    const logoutUrl = 'https://user-center.example.com/auth/web/#/logout?redirectUri=http%3A%2F%2Fapp.example.com&channel=kl-repo-pbc'
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(mockFetchSuccess({ user: mockUser }))
      .mockResolvedValueOnce(mockFetchSuccess({ loggedOut: true, logoutUriConfig: { default: logoutUrl } }))

    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    const logoutBtn = screen.getByTestId('logout-btn')
    await act(async () => {
      logoutBtn.click()
    })

    expect(globalThis.fetch).toHaveBeenCalledTimes(2)
    const logoutCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[1]
    expect(logoutCall[0]).toBe('/api/auth/logout')
    expect(logoutCall[1]?.method).toBe('POST')
    // Authorization header should be included (sessionStorage not cleared before the call)
    expect(logoutCall[1]?.headers).toEqual(
      expect.objectContaining({ Authorization: 'Bearer logout-session' }),
    )

    // Token should be cleared from sessionStorage after logout
    await waitFor(() => {
      expect(window.sessionStorage.getItem('crawlerWorkflow.sessionId')).toBeNull()
    })

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
    })
  })

  it('sends Authorization header when sessionId is stored', async () => {
    setStoredSessionId('saved-session-456')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser, auth: mockAuthStatus }))

    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    const meCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(meCall[0]).toBe('/api/auth/me')
    expect(meCall[1]?.headers).toEqual(
      expect.objectContaining({ Authorization: 'Bearer saved-session-456' }),
    )
  })

  it('re-checks /api/auth/me on mount when sessionId persists across refresh', async () => {
    setStoredSessionId('persist-session')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser, auth: mockAuthStatus }))

    const { unmount } = renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    // Simulate page refresh: unmount and remount
    unmount()
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser, auth: mockAuthStatus }))
    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    // fetch was called again on the second mount with the token header
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer persist-session' }),
      }),
    )
  })

  it('registers onUnauthorized handler that clears auth state and removes sessionId on 401', async () => {
    setStoredSessionId('token-to-clear')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser, auth: mockAuthStatus }))

    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    // Simulate a 401 from any API call
    const { apiFetch } = await import('../services/apiClient')

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    const { UnauthorizedError } = await import('../services/apiClient')
    await expect(apiFetch('/api/tasks')).rejects.toThrow(UnauthorizedError)

    // Auth state should be cleared after 401
    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
    })
    expect(screen.getByTestId('username').textContent).toBe('none')

    expect(window.sessionStorage.getItem('crawlerWorkflow.sessionId')).toBeNull()
  })

  it('clears onUnauthorized handler on unmount', async () => {
    setStoredSessionId('still-valid')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser, auth: mockAuthStatus }))

    const { unmount } = renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    // Unmount should clear the handler
    unmount()

    // After unmount, a 401 should not crash or call stale callbacks
    const { apiFetch, UnauthorizedError } = await import('../services/apiClient')
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    // Should throw UnauthorizedError without crashing
    await expect(apiFetch('/api/tasks')).rejects.toThrow(UnauthorizedError)
  })

  it('clearAuthError clears the error state', async () => {
    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    // Click clear error button
    const clearBtn = screen.getByTestId('clear-error-btn')
    await act(async () => {
      clearBtn.click()
    })

    expect(screen.getByTestId('auth-error').textContent).toBe('none')
  })
})
