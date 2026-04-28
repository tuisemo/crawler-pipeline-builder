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
  envelope: ApiEnvelope
}

export type ApiEnvelope = {
  success: boolean
  error_code?: string | null
  error?: string | null
  data?: unknown
  warnings?: unknown[]
  meta?: Record<string, unknown>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function isApiEnvelope(value: unknown): value is ApiEnvelope {
  if (!isRecord(value)) return false
  return typeof value.success === 'boolean' && Object.prototype.hasOwnProperty.call(value, 'data')
}

function normalizeEnvelope(value: unknown): ApiEnvelope {
  if (isApiEnvelope(value)) return value
  return {
    success: false,
    error: getErrorMessage(value),
    data: {},
    warnings: [],
    meta: {},
  }
}

async function parseEnvelope(response: Response): Promise<WorkflowActionResponse> {
  const raw: unknown = await response.json().catch(() => ({}))
  const envelope = normalizeEnvelope(raw)
  const payload = envelope.success && isRecord(envelope.data) ? envelope.data : envelope
  return { response, payload, envelope }
}

export async function validateGraphWithBackend(graph: WorkflowGraph): Promise<void> {
  const response = await fetch('/api/workflows/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ graph }),
  })
  const { envelope } = await parseEnvelope(response)
  if (!response.ok || !envelope.success) {
    throw new Error(getErrorMessage(envelope))
  }
}

export async function postWorkflowAction(path: WorkflowActionPath, body: unknown): Promise<WorkflowActionResponse> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseEnvelope(response)
}

export async function postAssistAction(path: AssistActionPath, body: unknown): Promise<WorkflowActionResponse> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseEnvelope(response)
}
