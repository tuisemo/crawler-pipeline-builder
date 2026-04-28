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

  it('postAssistAction supports clean-data endpoint', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { result: { cleaned_value: 12000 } }, warnings: [], meta: {} }),
    } as Response)

    const result = await postAssistAction('/api/assist/clean-data', { raw_data: '1.2万', data_type: 'count' })

    expect(result.response.ok).toBe(true)
    expect(result.payload).toEqual({ result: { cleaned_value: 12000 } })
  })
})
