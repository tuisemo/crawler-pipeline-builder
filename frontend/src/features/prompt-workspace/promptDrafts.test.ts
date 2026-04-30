import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildWorkflowGraphKey,
  extractEditablePrompt,
  extractEffectivePrompt,
  loadSavedPromptDrafts,
  normalizeMultilineText,
  persistSavedPromptDrafts,
  PROMPT_DRAFTS_STORAGE_KEY,
  summarizeText,
} from './promptDrafts'

describe('promptDrafts utilities', () => {
  beforeEach(() => {
    const store = new Map<string, string>()
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => { store.set(key, value) },
        clear: () => { store.clear() },
      },
    })
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('buildWorkflowGraphKey is stable for the same graph', () => {
    const graph = {
      nodes: [{ id: 'n1', type: 'open_page' as const, data: { url: 'https://example.com' } }],
      edges: [],
    }

    expect(buildWorkflowGraphKey(graph)).toBe(buildWorkflowGraphKey(graph))
  })

  it('persists and reloads prompt drafts from localStorage', () => {
    persistSavedPromptDrafts({
      'graph-1': { text: 'custom prompt', savedAt: 123 },
    })

    expect(window.localStorage.getItem(PROMPT_DRAFTS_STORAGE_KEY)).toContain('custom prompt')
    expect(loadSavedPromptDrafts()).toEqual({
      'graph-1': { text: 'custom prompt', savedAt: 123 },
    })
  })

  it('extracts editable and effective prompt from payload', () => {
    const payload = {
      prompt: 'final prompt',
      editable_prompt: 'editable prompt',
      effective_prompt: 'effective prompt',
    }

    expect(extractEditablePrompt(payload)).toBe('editable prompt')
    expect(extractEffectivePrompt(payload)).toBe('effective prompt')
  })

  it('normalizes multiline text and summarizes size', () => {
    const normalized = normalizeMultilineText('line1\r\n\tline2\r\n')
    expect(normalized).toBe('line1\n  line2')
    expect(summarizeText(normalized)).toEqual({ chars: 13, lines: 2 })
  })
})
