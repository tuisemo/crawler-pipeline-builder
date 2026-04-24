import { getErrorMessage } from '../workflowState'
import type { WorkflowGraph } from '../workflowContracts'

export type WorkflowActionPath =
  | '/api/workflows/validate'
  | '/api/workflows/to-prompt'
  | '/api/workflows/test-node'
  | '/api/workflows/test-subflow'
  | '/api/workflows/compile-plan'
  | '/api/workflows/generate-skeleton'
  | '/api/workflows/generate-crawler'
  | '/api/workflows/format-script'
  | '/api/workflows/save-script'

export type AssistActionPath =
  | '/api/assist/auto-detect'
  | '/api/assist/extract-html'
  | '/api/assist/infer-fields'
  | '/api/assist/optimize-selector'
  | '/api/assist/analyze-pagination'
  | '/api/assist/clean-data'

export type WorkflowActionResponse = {
  response: Response
  payload: unknown
}

export async function validateGraphWithBackend(graph: WorkflowGraph): Promise<void> {
  const response = await fetch('/api/workflows/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ graph }),
  })
  const payload: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(getErrorMessage(payload))
  }
}

export async function postWorkflowAction(path: WorkflowActionPath, body: unknown): Promise<WorkflowActionResponse> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload: unknown = await response.json().catch(() => ({}))
  return { response, payload }
}

export async function postAssistAction(path: AssistActionPath, body: unknown): Promise<WorkflowActionResponse> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload: unknown = await response.json().catch(() => ({}))
  return { response, payload }
}
