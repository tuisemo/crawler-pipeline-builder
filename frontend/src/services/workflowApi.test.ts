// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { postAssistAction, postWorkflowAction, validateGraphWithBackend, UnauthorizedError } from './workflowApi'

const originalFetch = globalThis.fetch

describe('workflowApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('validateGraphWithBackend resolves for successful responses', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: {}, warnings: [], meta: {} }),
    } as Response)

    await expect(
      validateGraphWithBackend({ nodes: [{ id: 'n1', type: 'open_page', data: { url: 'https://example.com' } }], edges: [] }),
    ).resolves.toBeUndefined()
  })

  it('validateGraphWithBackend throws normalized backend errors', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ success: false, error: 'Graph invalid', data: {}, warnings: [], meta: {} }),
    } as Response)

    await expect(
      validateGraphWithBackend({ nodes: [{ id: 'n1', type: 'open_page', data: { url: 'https://example.com' } }], edges: [] }),
    ).rejects.toThrow('Graph invalid')
  })

  it('postWorkflowAction returns the parsed payload', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { prompt: 'ok' }, warnings: [], meta: {} }),
    } as Response)

    const result = await postWorkflowAction('/api/workflows/to-prompt', { graph: { nodes: [], edges: [] } })

    expect(result.response.ok).toBe(true)
    expect(result.envelope.success).toBe(true)
    expect(result.payload).toEqual({ prompt: 'ok' })
  })

  it('postAssistAction returns the parsed payload', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { result: { item_selector: '.item' } }, warnings: [], meta: {} }),
    } as Response)

    const result = await postAssistAction('/api/assist/infer-fields', { html_fragment: '<div class="item">ok</div>' })

    expect(result.response.ok).toBe(true)
    expect(result.payload).toEqual({ result: { item_selector: '.item' } })
  })

  it('all fetch calls include Content-Type header via apiFetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: {}, warnings: [], meta: {} }),
    } as Response)

    await validateGraphWithBackend({ nodes: [{ id: 'n1', type: 'open_page', data: { url: 'https://example.com' } }], edges: [] })

    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' }),
    )
  })

  it('401 response throws UnauthorizedError', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    await expect(
      postWorkflowAction('/api/workflows/to-prompt', { graph: { nodes: [], edges: [] } }),
    ).rejects.toThrow(UnauthorizedError)
  })
})
