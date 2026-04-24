import { MarkerType, type Edge, type Node } from '@xyflow/react'
import type {
  CanonicalWorkflowEdge,
  WorkflowGraph,
  WorkflowBranch,
  WorkflowNodeData,
  WorkflowNodeType,
} from './workflowContracts'

export type DslStatus = 'synced' | 'parse-error' | 'schema-error'

export type WorkflowNode = Node<WorkflowNodeData, WorkflowNodeType>
export type WorkflowEdge = Edge & {
  branch?: WorkflowBranch
  order?: number
}

export type DslApplyState = {
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  selectedNodeId: string
}

export type DslApplyResult = DslApplyState & {
  dslText: string
  dslStatus: DslStatus
  dslFeedback: string
  applied: boolean
  requestId: number
}

export type DslRequestTracker = {
  current: number
}

export const workflowNodeTypes = new Set<WorkflowNodeType>([
  'open_page',
  'select_list',
  'loop',
  'extract_field',
  'condition',
  'paginate',
  'emit_record',
  'end',
])

export function toCanonicalGraph(nodes: WorkflowNode[], edges: WorkflowEdge[]): WorkflowGraph {
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type ?? 'open_page',
      data: node.data,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      branch: edge.branch,
      label: typeof edge.label === 'string' ? edge.label : undefined,
      order: typeof edge.order === 'number' ? edge.order : undefined,
    })),
  }
}

export function getErrorMessage(payload: unknown) {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    if (typeof record.error === 'string') return record.error
    if (typeof record.detail === 'string') return record.detail
    if (Array.isArray(record.detail)) return record.detail.map((item) => JSON.stringify(item)).join('; ')
  }
  return 'Workflow schema validation failed.'
}

export function isWorkflowNodeType(value: unknown): value is WorkflowNodeType {
  return typeof value === 'string' && workflowNodeTypes.has(value as WorkflowNodeType)
}

export function validateGraphShape(value: unknown): WorkflowGraph {
  if (!value || typeof value !== 'object') {
    throw new Error('DSL must be a JSON object with nodes and edges arrays.')
  }

  const graph = value as { nodes?: unknown; edges?: unknown }
  if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
    throw new Error('DSL graph requires nodes and edges arrays.')
  }

  const nodes = graph.nodes.map((node, index) => {
    if (!node || typeof node !== 'object') {
      throw new Error(`Node ${index + 1} must be an object.`)
    }
    const candidate = node as Record<string, unknown>
    if (typeof candidate.id !== 'string' || !candidate.id.trim()) {
      throw new Error(`Node ${index + 1} requires a non-empty string id.`)
    }
    if (!isWorkflowNodeType(candidate.type)) {
      throw new Error(`Node ${candidate.id} has unsupported type ${String(candidate.type)}.`)
    }
    if (!candidate.data || typeof candidate.data !== 'object' || Array.isArray(candidate.data)) {
      throw new Error(`Node ${candidate.id} requires object data.`)
    }
    const data = candidate.data as WorkflowNodeData
    if (candidate.type === 'extract_field' && data.fields) {
      for (const [fieldIndex, field] of data.fields.entries()) {
        const resolvedName = typeof field.name === 'string' && field.name.trim()
          ? field.name
          : typeof field.field_name === 'string' && field.field_name.trim()
            ? field.field_name
            : ''
        const resolvedSelector = typeof field.selector === 'string' && field.selector.trim()
          ? field.selector
          : typeof field.css === 'string' && field.css.trim()
            ? field.css
            : ''
        if (!resolvedName) {
          throw new Error(`Node ${candidate.id} field ${fieldIndex + 1} requires a name or field_name.`)
        }
        if (!resolvedSelector) {
          throw new Error(`Node ${candidate.id} field ${fieldIndex + 1} requires a selector or css.`)
        }
      }
    }
    return { id: candidate.id, type: candidate.type, data }
  })

  const edges = graph.edges.map((edge, index) => {
    if (!edge || typeof edge !== 'object') {
      throw new Error(`Edge ${index + 1} must be an object.`)
    }
    const candidate = edge as Record<string, unknown>
    if (typeof candidate.id !== 'string' || !candidate.id.trim()) {
      throw new Error(`Edge ${index + 1} requires a non-empty string id.`)
    }
    if (typeof candidate.source !== 'string' || !candidate.source.trim()) {
      throw new Error(`Edge ${candidate.id} requires a non-empty string source.`)
    }
    if (typeof candidate.target !== 'string' || !candidate.target.trim()) {
      throw new Error(`Edge ${candidate.id} requires a non-empty string target.`)
    }
    const parsed: CanonicalWorkflowEdge = {
      id: candidate.id,
      source: candidate.source,
      target: candidate.target,
    }
    if (
      typeof candidate.branch === 'boolean' ||
      candidate.branch === 'true' ||
      candidate.branch === 'false' ||
      candidate.branch === 'default'
    ) {
      parsed.branch = candidate.branch as WorkflowBranch
    }
    if (typeof candidate.label === 'string' && candidate.label.trim()) {
      parsed.label = candidate.label
    }
    if (typeof candidate.order === 'number' && Number.isFinite(candidate.order)) {
      parsed.order = candidate.order
    }
    return parsed
  })

  return { nodes, edges }
}

export function graphToFlowState(graph: WorkflowGraph, previousNodes: WorkflowNode[]): { nodes: WorkflowNode[]; edges: WorkflowEdge[] } {
  const previousById = new Map(previousNodes.map((node) => [node.id, node]))
  return {
    nodes: graph.nodes.map((node, index) => ({
      id: node.id,
      type: node.type,
      data: node.data,
      position: previousById.get(node.id)?.position ?? { x: 80 + (index % 4) * 230, y: 100 + Math.floor(index / 4) * 150 },
    })),
    edges: graph.edges.map((edge) => ({ ...edge, markerEnd: { type: MarkerType.ArrowClosed } })),
  }
}

export async function applyDslTextChange(
  state: DslApplyState,
  nextText: string,
  requestTracker: DslRequestTracker,
  validateGraphWithBackend: (graph: WorkflowGraph) => Promise<void>,
): Promise<DslApplyResult> {
  let nextGraph: WorkflowGraph
  try {
    nextGraph = validateGraphShape(JSON.parse(nextText))
  } catch (error) {
    return {
      ...state,
      dslText: nextText,
      dslStatus: error instanceof SyntaxError ? 'parse-error' : 'schema-error',
      dslFeedback: error instanceof Error ? error.message : 'Invalid DSL JSON.',
      applied: false,
      requestId: requestTracker.current,
    }
  }

  const requestId = requestTracker.current + 1
  requestTracker.current = requestId

  try {
    await validateGraphWithBackend(nextGraph)
  } catch (error) {
    if (requestId !== requestTracker.current) {
      return { ...state, dslText: nextText, dslStatus: 'synced', dslFeedback: 'Stale DSL validation ignored.', applied: false, requestId }
    }
    return {
      ...state,
      dslText: nextText,
      dslStatus: 'schema-error',
      dslFeedback: error instanceof Error ? error.message : 'Backend validation rejected this workflow graph.',
      applied: false,
      requestId,
    }
  }

  if (requestId !== requestTracker.current) {
    return { ...state, dslText: nextText, dslStatus: 'synced', dslFeedback: 'Stale DSL validation ignored.', applied: false, requestId }
  }

  const nextFlowState = graphToFlowState(nextGraph, state.nodes)
  const selectedNodeId = nextFlowState.nodes.some((node) => node.id === state.selectedNodeId)
    ? state.selectedNodeId
    : nextFlowState.nodes[0]?.id ?? ''

  return {
    nodes: nextFlowState.nodes,
    edges: nextFlowState.edges,
    selectedNodeId,
    dslText: JSON.stringify(nextGraph, null, 2),
    dslStatus: 'synced',
    dslFeedback: 'Valid DSL applied to the canvas and property panel.',
    applied: true,
    requestId,
  }
}
