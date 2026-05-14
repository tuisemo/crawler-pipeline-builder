// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { RequireAuth } from './RequireAuth'
import { AuthProvider } from './AuthProvider'
import { clearStoredSessionId, setStoredSessionId } from '../services/apiClient'

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

// Simple page components for testing
function PublicPage() {
  return <div data-testid="public-page">Public Home</div>
}

function ProtectedPage() {
  return <div data-testid="protected-page">Tasks Page</div>
}

function TaskDetailPage() {
  return <div data-testid="task-detail-page">Task Detail</div>
}

function WorkbenchPage() {
  return <div data-testid="workbench-page">Workbench</div>
}

/**
 * Renders the app with MemoryRouter starting at `initialPath`.
 * The routes match the production layout:
 *   /          → PublicPage (no RequireAuth)
 *   /tasks     → ProtectedPage (RequireAuth)
 *   /tasks/:id → TaskDetailPage (RequireAuth)
 *   /tasks/:id/workbench → WorkbenchPage (RequireAuth)
 */
function renderApp(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]} initialIndex={0}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<PublicPage />} />
          <Route
            path="/tasks"
            element={
              <RequireAuth>
                <ProtectedPage />
              </RequireAuth>
            }
          />
          <Route
            path="/tasks/:taskId"
            element={
              <RequireAuth>
                <TaskDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/tasks/:taskId/workbench"
            element={
              <RequireAuth>
                <WorkbenchPage />
              </RequireAuth>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

// ── Tests ────────────────────────────────────────────────

describe('RequireAuth', () => {
  const originalFetch = globalThis.fetch
  const originalLocation = window.location

  beforeEach(() => {
    vi.restoreAllMocks()
    clearStoredSessionId()
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
    clearStoredSessionId()
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
    })
  })

  it('shows loading indicator while auth is being checked', () => {
    setStoredSessionId('session-123')
    // Never resolves — simulates in-flight /api/auth/me
    globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {}))

    renderApp('/tasks')

    // Should NOT show the protected content or login redirect
    expect(screen.queryByTestId('protected-page')).toBeNull()
    // Should show a loading indicator (Spin or similar)
    expect(document.querySelector('.ant-spin') || screen.getByRole('status')).toBeTruthy()
  })

  it('renders protected content when authenticated', async () => {
    setStoredSessionId('session-123')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser }))

    renderApp('/tasks')

    await waitFor(() => {
      expect(screen.getByTestId('protected-page')).toBeTruthy()
    })
  })

  it('redirects to login when unauthenticated on /tasks', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    renderApp('/tasks')

    await waitFor(() => {
      // login() should set window.location.href to /api/auth/login?next=/tasks
      expect(window.location.href).toBe('/api/auth/login?next=%2Ftasks')
    })

    // Protected content should NOT be rendered
    expect(screen.queryByTestId('protected-page')).toBeNull()
  })

  it('redirects to login with next=/tasks/:taskId when unauthenticated on task detail', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    renderApp('/tasks/42')

    await waitFor(() => {
      expect(window.location.href).toBe('/api/auth/login?next=%2Ftasks%2F42')
    })

    expect(screen.queryByTestId('task-detail-page')).toBeNull()
  })

  it('redirects to login with next=/tasks/:taskId/workbench when unauthenticated', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    renderApp('/tasks/42/workbench')

    await waitFor(() => {
      expect(window.location.href).toBe('/api/auth/login?next=%2Ftasks%2F42%2Fworkbench')
    })

    expect(screen.queryByTestId('workbench-page')).toBeNull()
  })

  it('homepage is accessible without authentication', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    renderApp('/')

    // Public page should render immediately (no RequireAuth wrapping)
    await waitFor(() => {
      expect(screen.getByTestId('public-page')).toBeTruthy()
    })

    // No login redirect should happen
    expect(window.location.href).toBe('')
  })

  it('does not flash login redirect while auth is loading', () => {
    setStoredSessionId('session-123')
    // Auth check never resolves
    globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {}))

    renderApp('/tasks')

    // Should NOT have redirected to login
    expect(window.location.href).toBe('')
    // Should NOT show protected content
    expect(screen.queryByTestId('protected-page')).toBeNull()
    // Should show loading indicator instead
    expect(document.querySelector('.ant-spin') || screen.getByRole('status')).toBeTruthy()
  })

  it('after auth resolves as authenticated, protected content shows', async () => {
    setStoredSessionId('session-123')
    // Start with loading, then resolve as authenticated
    let resolveMe: (value: unknown) => void
    const mePromise = new Promise((resolve) => {
      resolveMe = resolve
    })
    globalThis.fetch = vi.fn().mockReturnValue(mePromise)

    renderApp('/tasks')

    // Still loading — no content yet
    expect(screen.queryByTestId('protected-page')).toBeNull()

    // Resolve auth as authenticated
    await resolveMe!(mockFetchSuccess({ user: mockUser }))

    await waitFor(() => {
      expect(screen.getByTestId('protected-page')).toBeTruthy()
    })
  })
})
