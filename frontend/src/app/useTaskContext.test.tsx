// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import { AuthProvider } from '../auth/AuthProvider'
import { useTaskContext } from './useTaskContext'
import { NotFoundError } from '../services/taskApi'

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

function mockFetch404(): Response {
  return {
    ok: false,
    status: 404,
    json: async () => ({ success: false, error: 'Task not found' }),
  } as Response
}

// A test component that uses useTaskContext and displays its state
// It's rendered as the Route element so useParams works
function TaskContextViewer() {
  const { loading, error, errorKind, task, taskId } = useTaskContext()
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="error">{error ?? 'none'}</span>
      <span data-testid="errorKind">{errorKind ?? 'none'}</span>
      <span data-testid="taskName">{task?.name ?? 'none'}</span>
      <span data-testid="taskId">{String(taskId)}</span>
    </div>
  )
}

function renderWithRoute(taskId: string) {
  return render(
    <MemoryRouter initialEntries={[`/tasks/${taskId}`]} initialIndex={0}>
      <AuthProvider>
        <ConfigProvider>
          <Routes>
            <Route path="/tasks/:taskId" element={<TaskContextViewer />} />
          </Routes>
        </ConfigProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

// ── Tests ────────────────────────────────────────────────

describe('useTaskContext 404 handling', () => {
  const originalFetch = globalThis.fetch
  const originalLocation = window.location

  beforeEach(() => {
    vi.restoreAllMocks()
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

  it('sets errorKind=not_found when task returns 404', async () => {
    // Note: useTaskContext's useEffect fires BEFORE AuthProvider's useEffect,
    // so the first fetch call is for the task, not for auth/me.
    // We need to handle both orders, so we use a URL-based mock.
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/auth/me')) {
        return Promise.resolve(mockFetchSuccess({ user: mockUser }))
      }
      if (url.includes('/api/tasks/')) {
        return Promise.resolve(mockFetch404())
      }
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}) } as Response)
    })

    renderWithRoute('999')

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('errorKind').textContent).toBe('not_found')
    expect(screen.getByTestId('error').textContent).toBe('任务不存在')
    expect(screen.getByTestId('taskName').textContent).toBe('none')
  })

  it('loads task successfully when found', async () => {
    const mockTask = {
      id: 1,
      name: '测试任务',
      description: '这是一个测试任务',
      target_url: 'https://example.com',
      status: 'active',
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
    }

    // Use URL-based mock since fetch call order is not guaranteed
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/auth/me')) {
        return Promise.resolve(mockFetchSuccess({ user: mockUser }))
      }
      if (url.includes('/api/tasks/')) {
        return Promise.resolve(mockFetchSuccess({ task: mockTask, assets: [] }))
      }
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}) } as Response)
    })

    renderWithRoute('1')

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('errorKind').textContent).toBe('none')
    expect(screen.getByTestId('taskName').textContent).toBe('测试任务')
  })
})

describe('NotFoundError', () => {
  it('is throwable and catchable', () => {
    try {
      throw new NotFoundError('Task not found')
    } catch (err) {
      expect(err).toBeInstanceOf(NotFoundError)
      expect((err as NotFoundError).name).toBe('NotFoundError')
      expect((err as NotFoundError).message).toBe('Task not found')
    }
  })

  it('has default message', () => {
    const err = new NotFoundError()
    expect(err.message).toBe('Not found')
  })
})
