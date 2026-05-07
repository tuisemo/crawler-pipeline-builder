import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { postAssistAction, postWorkflowAction, validateGraphWithBackend } from './workflowApi'

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

    const result = await postAssistAction('/api/assist/auto-detect', { url: 'https://example.com' })

    expect(result.response.ok).toBe(true)
    expect(result.payload).toEqual({ result: { item_selector: '.item' } })
  })

  it('postWorkflowAction preserves ext-prefixed agent ids', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { ok: true }, warnings: [], meta: {} }),
    } as Response)

    await postWorkflowAction('/api/workflows/test-node', {
      graph: { nodes: [], edges: [] },
      node_id: 'node-1',
      agent_id: 'ext:desktop-a',
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/workflows/test-node',
      expect.objectContaining({
        body: JSON.stringify({
          graph: { nodes: [], edges: [] },
          node_id: 'node-1',
          agent_id: 'ext:desktop-a',
        }),
      }),
    )
  })
})
