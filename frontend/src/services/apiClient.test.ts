// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { apiFetch, setOnUnauthorized, UnauthorizedError } from './apiClient'

describe('apiClient', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.restoreAllMocks()
    setOnUnauthorized(null)
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    setOnUnauthorized(null)
  })

  // ── credentials: 'include' ──────────────────────────────

  it('includes credentials: include on all requests', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, data: {} }),
    } as Response)

    await apiFetch('/api/tasks')

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/tasks',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('includes credentials: include on POST requests', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, data: {} }),
    } as Response)

    await apiFetch('/api/tasks', { method: 'POST', body: JSON.stringify({ name: 'test' }) })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/tasks',
      expect.objectContaining({
        credentials: 'include',
        method: 'POST',
      }),
    )
  })

  it('includes Content-Type: application/json by default', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, data: {} }),
    } as Response)

    await apiFetch('/api/tasks')

    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' }),
    )
  })

  it('allows overriding headers', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, data: {} }),
    } as Response)

    await apiFetch('/api/tasks', {
      headers: { 'Content-Type': 'text/plain', 'X-Custom': 'yes' },
    })

    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({
        'Content-Type': 'text/plain',
        'X-Custom': 'yes',
      }),
    )
  })

  // ── 401 handling ────────────────────────────────────────

  it('throws UnauthorizedError on 401 response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    await expect(apiFetch('/api/tasks')).rejects.toThrow(UnauthorizedError)
  })

  it('calls onUnauthorized callback on 401', async () => {
    const onUnauthorized = vi.fn()
    setOnUnauthorized(onUnauthorized)

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    await expect(apiFetch('/api/tasks')).rejects.toThrow(UnauthorizedError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('does not call onUnauthorized for non-401 errors', async () => {
    const onUnauthorized = vi.fn()
    setOnUnauthorized(onUnauthorized)

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ success: false, error: 'Internal error' }),
    } as Response)

    // Should not throw UnauthorizedError for 500
    const response = await apiFetch('/api/tasks')
    expect(response.status).toBe(500)
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('does not call onUnauthorized for successful responses', async () => {
    const onUnauthorized = vi.fn()
    setOnUnauthorized(onUnauthorized)

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, data: {} }),
    } as Response)

    const response = await apiFetch('/api/tasks')
    expect(response.ok).toBe(true)
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('does not call onUnauthorized when no callback is registered', async () => {
    setOnUnauthorized(null)

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    // Should throw but not crash
    await expect(apiFetch('/api/tasks')).rejects.toThrow(UnauthorizedError)
  })

  it('clears the onUnauthorized callback when set to null', async () => {
    const onUnauthorized = vi.fn()
    setOnUnauthorized(onUnauthorized)

    // Clear the callback
    setOnUnauthorized(null)

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    await expect(apiFetch('/api/tasks')).rejects.toThrow(UnauthorizedError)
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  // ── Return value ────────────────────────────────────────

  it('returns the Response object for successful requests', async () => {
    const mockResponse = {
      ok: true,
      status: 200,
      json: async () => ({ success: true, data: { items: [] } }),
    } as Response

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse)

    const response = await apiFetch('/api/tasks')
    expect(response).toBe(mockResponse)
  })
})
