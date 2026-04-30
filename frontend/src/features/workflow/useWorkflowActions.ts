import { useMemo, useState } from 'react'
import { getErrorMessage } from './workflowState'
import type { ScriptGenerationMode, WorkflowGraph } from './workflowContracts'
import { postWorkflowAction } from '../../services/workflowApi'
import type { WorkbenchAction } from '../../app/components/WorkbenchToolbar'

type ResultTone = 'idle' | 'loading' | 'success' | 'validation-error' | 'runtime-error' | 'partial' | 'session-expired'

export type ResultState = {
  tone: ResultTone
  title: string
  message: string
  payload?: unknown
  action?: WorkbenchAction
  graphKey?: string
}

type UseWorkflowActionsArgs = {
  canonicalGraph: WorkflowGraph
  selectedNodeId: string
  graphKey: string
  getPromptOverride: (graphKey: string) => string
  generationMode: ScriptGenerationMode
}

const actionLabels: Record<WorkbenchAction, string> = {
  validate: 'Validate DSL',
  prompt: 'Preview Prompt',
  'compile-plan': 'Compile Plan',
  'generate-skeleton': 'Generate Skeleton',
  'test-node': 'Run Node Test',
  'test-subflow': 'Run Subflow Test',
  'generate-script': 'Generate Script',
  'auto-layout': 'Auto Layout',
}

function classifyResult(action: WorkbenchAction, responseOk: boolean, payload: unknown): ResultTone {
  const record = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {}
  if (record.session_expired === true) return 'session-expired'
  if (record.partial === true) return 'partial'
  if (responseOk && record.success !== false) return 'success'
  if (action === 'validate' || action === 'prompt' || action === 'compile-plan') return 'validation-error'
  return 'runtime-error'
}

function resolveResultMessage(action: WorkbenchAction, responseOk: boolean, payload: unknown, tone: ResultTone): string {
  if (tone === 'success') {
    return 'Workflow action completed. Inspect the structured output below.'
  }
  if (tone === 'partial') {
    return 'Workflow action partially completed. Inspect logs and sample output below.'
  }

  const parsedError = getErrorMessage(payload)
  if (parsedError && parsedError !== 'Workflow schema validation failed.') {
    return parsedError
  }

  if (!responseOk) {
    return `${actionLabels[action]} request failed.`
  }
  return `${actionLabels[action]} failed. Inspect the structured output below.`
}

export function useWorkflowActions({ canonicalGraph, selectedNodeId, graphKey, getPromptOverride, generationMode }: UseWorkflowActionsArgs) {
  const [resultState, setResultState] = useState<ResultState>({
    tone: 'idle',
    title: 'Idle',
    message: 'Select an action from the toolbar to show validation, prompt preview, node test, or subflow output here.',
  })
  const [runningAction, setRunningAction] = useState<WorkbenchAction | null>(null)

  const selectedOrEntryNodeId = useMemo(
    () => selectedNodeId || canonicalGraph.nodes[0]?.id || '',
    [canonicalGraph.nodes, selectedNodeId],
  )

  async function runWorkflowAction(action: WorkbenchAction) {
    if ((action === 'test-node' || action === 'test-subflow') && runningAction) return

    const previousPayload = resultState.payload
    setRunningAction(action)
    setResultState({
      tone: 'loading',
      title: `${actionLabels[action]} running`,
      message: previousPayload
        ? `Loading new result; previous output remains below.${action === 'generate-script' ? ` Current mode: ${generationMode}.` : ''}`
        : action === 'generate-script'
          ? `Loading workflow result... Current mode: ${generationMode}.`
          : 'Loading workflow result...',
      payload: previousPayload,
      action,
      graphKey,
    })

    try {
      const promptOverride = action === 'generate-script' ? getPromptOverride(graphKey) : ''
      const requestBody = action === 'test-node'
        ? { graph: canonicalGraph, node_id: selectedOrEntryNodeId }
        : action === 'test-subflow'
          ? { graph: canonicalGraph, boundary: { start_node_id: selectedNodeId || undefined } }
          : action === 'generate-script' && promptOverride
            ? { graph: canonicalGraph, prompt_override: promptOverride, generation_mode: generationMode }
            : action === 'generate-script'
              ? { graph: canonicalGraph, generation_mode: generationMode }
            : { graph: canonicalGraph }
      const path = action === 'validate'
        ? '/api/workflows/validate'
        : action === 'prompt'
          ? '/api/workflows/to-prompt'
          : action === 'compile-plan'
            ? '/api/workflows/compile-plan'
          : action === 'generate-skeleton'
            ? '/api/workflows/generate-skeleton'
          : action === 'test-node'
            ? '/api/workflows/test-node'
            : action === 'generate-script'
              ? '/api/workflows/generate-crawler'
              : '/api/workflows/test-subflow'
      const { response, payload } = await postWorkflowAction(path, requestBody)
      const tone = classifyResult(action, response.ok, payload)
      setResultState({
        tone,
        title: actionLabels[action],
        message: resolveResultMessage(action, response.ok, payload, tone),
        payload,
        action,
        graphKey,
      })
    } catch (error) {
      setResultState({
        tone: 'runtime-error',
        title: `${actionLabels[action]} failed`,
        message: error instanceof Error ? error.message : 'Workflow action failed.',
        payload: previousPayload,
        action,
        graphKey,
      })
    } finally {
      setRunningAction(null)
    }
  }

  return {
    resultState,
    runningAction,
    runWorkflowAction,
  }
}
