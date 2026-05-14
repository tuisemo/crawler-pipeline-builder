// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import { AuthProvider } from '../auth/AuthProvider'
import { clearStoredSessionId, setStoredSessionId } from '../services/apiClient'

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
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: undefined,
  })
})

// ── Mock TechScene to avoid WebGL issues ────────────────

vi.mock('../components/TechScene', () => ({
  TechScene: () => <div data-testid="tech-scene-mock">TechScene</div>,
}))

// ── Import after mock ──────────────────────────────────

import HomePage from './HomePage'

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

function renderHomePage() {
  return render(
    <MemoryRouter initialEntries={['/']} initialIndex={0}>
      <AuthProvider>
        <ConfigProvider>
          <Routes>
            <Route path="/" element={<HomePage />} />
          </Routes>
        </ConfigProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

// ── Tests ────────────────────────────────────────────────

describe('HomePage auth UX', () => {
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

  it('shows 登录 button in hero section when unauthenticated', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('进入工作站')).toBeTruthy()
    })

    // Should show the login button (there may be one in the header area from Layout
    // but in this test, HomePage renders without Layout, so only the hero button)
    expect(screen.getByText('登录')).toBeTruthy()
  })

  it('does not show 登录 button in hero section when authenticated', async () => {
    setStoredSessionId('session-123')
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchSuccess({ user: mockUser }))

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('进入工作站')).toBeTruthy()
    })

    // When authenticated, the hero login button should NOT render
    expect(screen.queryByText('登录')).toBeNull()
  })

  it('clicking 登录 button in hero triggers login flow', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockFetchError(401, 'Not authenticated'))

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('进入工作站')).toBeTruthy()
    })

    const loginBtn = screen.getByText('登录')
    await act(async () => {
      loginBtn.click()
    })

    // login() should set window.location.href to /api/auth/login?next=...
    expect(window.location.href).toContain('/api/auth/login')
  })
})
