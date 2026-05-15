// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import { AuthProvider } from '../auth/AuthProvider'
import { clearStoredSessionId, setStoredSessionId } from '../services/apiClient'
import Layout from './Layout'

// ── jsdom polyfills for Antd ──────────────────────────────

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
})

afterEach(() => {
  // Restore matchMedia
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: undefined,
  })
})

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

function HomePage() {
  return <div data-testid="home-page">Home</div>
}

function TasksPage() {
  return <div data-testid="tasks-page">Tasks</div>
}

function renderApp(initialPath: string = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]} initialIndex={0}>
      <AuthProvider>
        <ConfigProvider>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<HomePage />} />
              <Route path="tasks" element={<TasksPage />} />
            </Route>
          </Routes>
        </ConfigProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

// ── Tests ────────────────────────────────────────────────

describe('Layout AppHeader', () => {
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

  it('shows user display_name and 退出 button when authenticated', async () => {
    setStoredSessionId('session-123')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser }))

    renderApp()

    await waitFor(() => {
      expect(screen.getByText('测试用户')).toBeTruthy()
    })
    expect(screen.getByText('退出')).toBeTruthy()
  })

  it('shows 登录 button when unauthenticated', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    renderApp()

    await waitFor(() => {
      // Antd may insert spaces between Chinese characters, so use role + regex
      expect(screen.getByRole('button', { name: /登.*录/ })).toBeTruthy()
    })
  })

  it('clicking 登录 navigates to /api/auth/login', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    renderApp()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /登.*录/ })).toBeTruthy()
    })

    const loginBtn = screen.getByRole('button', { name: /登.*录/ })
    await act(async () => {
      loginBtn.click()
    })

    expect(window.location.href).toContain('/api/auth/login')
  })

  it('clicking 退出 calls logout and navigates home', async () => {
    setStoredSessionId('session-123')
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(mockFetchSuccess({ user: mockUser }))
      .mockResolvedValueOnce(mockFetchSuccess({ loggedOut: true }))

    renderApp()

    await waitFor(() => {
      expect(screen.getByText('退出')).toBeTruthy()
    })

    const logoutBtn = screen.getByText('退出')
    await act(async () => {
      logoutBtn.click()
    })

    // After logout, sessionStorage should be cleared
    expect(window.sessionStorage.getItem('crawlerWorkflow.sessionId')).toBeNull()
  })

  it('renders children content (Outlet)', async () => {
    setStoredSessionId('session-123')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser }))

    renderApp()

    await waitFor(() => {
      expect(screen.getByTestId('home-page')).toBeTruthy()
    })
  })

  it('shows Scraper Flow Studio brand in header', async () => {
    setStoredSessionId('session-123')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser }))

    renderApp()

    await waitFor(() => {
      // Brand text is split across two <span> elements ("Scraper Flow" + "Studio")
      expect(screen.getByText('Scraper Flow')).toBeTruthy()
      expect(screen.getByText('Studio')).toBeTruthy()
    })
  })
})
