import type { WorkflowGraph } from './workflowContracts'

export const PROMPT_DRAFTS_STORAGE_KEY = 'crawler-workflow.prompt-drafts.v1'
export const LEGACY_PROMPT_DRAFTS_STORAGE_KEY = `${['sea', 'data'].join('-')}.prompt-drafts.v1`

export type SavedPromptDraft = {
  text: string
  savedAt: number
}

export type SavedPromptDraftMap = Record<string, SavedPromptDraft>

export function buildWorkflowGraphKey(graph: WorkflowGraph): string {
  const serialized = JSON.stringify(graph)
  let hash = 2166136261
  for (let i = 0; i < serialized.length; i += 1) {
    hash ^= serialized.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return `graph-${(hash >>> 0).toString(16)}`
}

export function loadSavedPromptDrafts(): SavedPromptDraftMap {
  if (typeof window === 'undefined' || !window.localStorage) return {}
  try {
    const raw = window.localStorage.getItem(PROMPT_DRAFTS_STORAGE_KEY)
      ?? window.localStorage.getItem(LEGACY_PROMPT_DRAFTS_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, SavedPromptDraft>
    if (!parsed || typeof parsed !== 'object') return {}
    return Object.entries(parsed).reduce<SavedPromptDraftMap>((acc, [key, value]) => {
      if (!value || typeof value !== 'object') return acc
      const text = typeof value.text === 'string' ? value.text : ''
      const savedAt = typeof value.savedAt === 'number' ? value.savedAt : 0
      if (!text.trim()) return acc
      acc[key] = { text, savedAt }
      return acc
    }, {})
  } catch {
    return {}
  }
}

export function persistSavedPromptDrafts(drafts: SavedPromptDraftMap) {
  if (typeof window === 'undefined' || !window.localStorage) return
  window.localStorage.setItem(PROMPT_DRAFTS_STORAGE_KEY, JSON.stringify(drafts))
}

export function extractEditablePrompt(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return ''
  const record = payload as Record<string, unknown>
  if (typeof record.editable_prompt === 'string' && record.editable_prompt.trim()) {
    return record.editable_prompt
  }
  if (typeof record.prompt === 'string' && record.prompt.trim()) {
    return record.prompt
  }
  return ''
}

export function extractEffectivePrompt(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return ''
  const record = payload as Record<string, unknown>
  if (typeof record.effective_prompt === 'string' && record.effective_prompt.trim()) {
    return record.effective_prompt
  }
  if (typeof record.prompt === 'string' && record.prompt.trim()) {
    return record.prompt
  }
  return ''
}

export function normalizeMultilineText(value: string): string {
  return value.replace(/\r\n/g, '\n').replace(/\t/g, '  ').trim()
}

export function summarizeText(value: string) {
  const normalized = normalizeMultilineText(value)
  const lines = normalized ? normalized.split('\n').length : 0
  return {
    chars: normalized.length,
    lines,
  }
}
