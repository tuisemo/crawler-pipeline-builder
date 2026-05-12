// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, cleanup } from '@testing-library/react'
import { AuthProvider } from './AuthProvider'
import { useAuth } from './useAuth'

// ── Helpers ──────────────────────────────────────────────

const mockUser = {
  id: 1,
  display_name: '测试用户',
  external_id: 'openId123',
  openId: 'openId123',
  email: 'test@example.com',
  avatar_url: 'https://avatar.example.com/1.png',
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
  const { isAuthenticated, user, isLoading, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="username">{user?.display_name ?? 'none'}</span>
      <button data-testid="login-btn" onClick={() => login('/tasks')}>
        Login
      </button>
      <button data-testid="logout-btn" onClick={logout}>
        Logout
      </button>
    </div>
  )
}

// ── Tests ────────────────────────────────────────────────

describe('AuthProvider', () => {
  const originalFetch = globalThis.fetch
  const originalLocation = window.location

  beforeEach(() => {
    vi.restoreAllMocks()
    // Mock window.location.assign for navigation
    Object.defineProperty(window, 'location', {
      value: {
        ...originalLocation,
        assign: vi.fn(),
        href: '',
      },
      writable: true,
    })
  })

  afterEach(() => {
    cleanup()
    globalThis.fetch = originalFetch
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
    })
  })

  it('shows loading state while /api/auth/me is in-flight', () => {
    // Return a promise that never resolves
    globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {}))
    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )
    expect(screen.getByTestId('loading').textContent).toBe('true')
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
  })

  it('renders children as authenticated when /api/auth/me returns user', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser }))

    render(
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

  it('sets unauthenticated state when /api/auth/me returns 401', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(screen.getByTestId('username').textContent).toBe('none')
  })

  it('login() navigates to /api/auth/login with next path', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    const loginBtn = screen.getByTestId('login-btn')
    await act(async () => {
      loginBtn.click()
    })

    // login() should set window.location.href to /api/auth/login?next=...
    expect(window.location.href).toBe('/api/auth/login?next=%2Ftasks')
  })

  it('logout() calls POST /api/auth/logout and clears state', async () => {
    // First call: /api/auth/me returns user (authenticated)
    // Second call: POST /api/auth/logout returns logoutUriConfig
    const logoutUrl = 'https://user-center/auth/web/#/logout?redirectUri=%2F&channel=default'
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(mockFetchSuccess({ user: mockUser }))
      .mockResolvedValueOnce(mockFetchSuccess({ logoutUriConfig: { default: logoutUrl } }))

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    // Wait for initial auth check
    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    // Click logout
    const logoutBtn = screen.getByTestId('logout-btn')
    await act(async () => {
      logoutBtn.click()
    })

    // Verify POST /api/auth/logout was called with credentials: 'include'
    expect(globalThis.fetch).toHaveBeenCalledTimes(2)
    const logoutCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[1]
    expect(logoutCall[0]).toBe('/api/auth/logout')
    expect(logoutCall[1]?.method).toBe('POST')
    expect(logoutCall[1]?.credentials).toBe('include')

    // After logout, state should be cleared
    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
    })
  })

  it('fetch calls include credentials: include', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser }))

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    const meCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(meCall[0]).toBe('/api/auth/me')
    expect(meCall[1]?.credentials).toBe('include')
  })

  it('re-checks /api/auth/me on mount (persists across refresh)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser }))

    const { unmount } = render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    // Simulate page refresh: unmount and remount
    unmount()
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser }))
    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    // fetch was called again on the second mount
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({ credentials: 'include' }),
    )
  })
})
