import { useCallback, useMemo, useState } from 'react'
import {
  extractEditablePrompt,
  loadSavedPromptDrafts,
  persistSavedPromptDrafts,
  type SavedPromptDraftMap,
} from '../promptDrafts'

type UsePromptWorkspaceArgs = {
  onSaveSuccess: () => void
  onResetSuccess: () => void
  onEmptySave: () => void
}

export function usePromptWorkspace({
  onSaveSuccess,
  onResetSuccess,
  onEmptySave,
}: UsePromptWorkspaceArgs) {
  const [savedPromptDrafts, setSavedPromptDrafts] = useState<SavedPromptDraftMap>(() => loadSavedPromptDrafts())
  const [promptDraftByGraph, setPromptDraftByGraph] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(loadSavedPromptDrafts()).map(([key, value]) => [key, value.text])),
  )
  const [promptBaseByGraph, setPromptBaseByGraph] = useState<Record<string, string>>({})

  const getPromptOverride = useCallback((targetGraphKey: string) => {
    const draft = promptDraftByGraph[targetGraphKey]?.trim() ?? ''
    if (!draft) return ''
    const base = promptBaseByGraph[targetGraphKey]?.trim() ?? ''
    return draft !== base ? draft : ''
  }, [promptBaseByGraph, promptDraftByGraph])

  const syncPromptFromResult = useCallback((resultGraphKey: string | undefined, payload: unknown) => {
    const prompt = extractEditablePrompt(payload)
    if (!prompt || !resultGraphKey) return
    setPromptBaseByGraph((current) => (
      current[resultGraphKey] === prompt
        ? current
        : { ...current, [resultGraphKey]: prompt }
    ))
    setPromptDraftByGraph((current) => (
      typeof current[resultGraphKey] === 'string'
        ? current
        : { ...current, [resultGraphKey]: prompt }
    ))
  }, [])

  const updatePromptDraft = useCallback((targetGraphKey: string, nextValue: string) => {
    setPromptDraftByGraph((current) => ({ ...current, [targetGraphKey]: nextValue }))
  }, [])

  const savePromptDraft = useCallback((targetGraphKey: string) => {
    const text = promptDraftByGraph[targetGraphKey] ?? promptBaseByGraph[targetGraphKey] ?? ''
    if (!text.trim()) {
      onEmptySave()
      return
    }
    const nextDrafts: SavedPromptDraftMap = {
      ...savedPromptDrafts,
      [targetGraphKey]: {
        text,
        savedAt: Date.now(),
      },
    }
    setSavedPromptDrafts(nextDrafts)
    persistSavedPromptDrafts(nextDrafts)
    onSaveSuccess()
  }, [onEmptySave, onSaveSuccess, promptBaseByGraph, promptDraftByGraph, savedPromptDrafts])

  const resetPromptDraft = useCallback((targetGraphKey: string) => {
    const basePrompt = promptBaseByGraph[targetGraphKey] ?? ''
    setPromptDraftByGraph((current) => ({ ...current, [targetGraphKey]: basePrompt }))
    if (savedPromptDrafts[targetGraphKey]) {
      const nextDrafts = { ...savedPromptDrafts }
      delete nextDrafts[targetGraphKey]
      setSavedPromptDrafts(nextDrafts)
      persistSavedPromptDrafts(nextDrafts)
    }
    onResetSuccess()
  }, [onResetSuccess, promptBaseByGraph, savedPromptDrafts])

  const buildPromptWorkspace = useCallback((resultGraphKey: string | undefined, payload: unknown) => {
    if (!resultGraphKey) return null
    const basePrompt = promptBaseByGraph[resultGraphKey] ?? extractEditablePrompt(payload)
    if (!basePrompt) return null
    const draft = promptDraftByGraph[resultGraphKey] ?? basePrompt
    const savedMeta = savedPromptDrafts[resultGraphKey]
    return {
      graphKey: resultGraphKey,
      value: draft,
      baseValue: basePrompt,
      savedAt: savedMeta?.savedAt,
      hasSavedDraft: Boolean(savedMeta?.text),
      isDirty: draft !== basePrompt,
      onChange: (nextValue: string) => updatePromptDraft(resultGraphKey, nextValue),
      onSave: () => savePromptDraft(resultGraphKey),
      onReset: () => resetPromptDraft(resultGraphKey),
    }
  }, [
    promptBaseByGraph,
    promptDraftByGraph,
    resetPromptDraft,
    savePromptDraft,
    savedPromptDrafts,
    updatePromptDraft,
  ])

  return useMemo(() => ({
    getPromptOverride,
    syncPromptFromResult,
    buildPromptWorkspace,
  }), [buildPromptWorkspace, getPromptOverride, syncPromptFromResult])
}
