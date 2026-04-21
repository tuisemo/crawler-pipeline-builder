import { MarkerType, type Edge, type Node } from '@xyflow/react'

export type DslStatus = 'synced' | 'parse-error' | 'schema-error'
export type WorkflowNodeType =
  | 'open_page'
  | 'select_list'
  | 'loop'
  | 'extract_field'
  | 'condition'
  | 'paginate'
  | 'emit_record'
  | 'end'

export type ExtractionField = {
  name: string
  selector: string
  type: string
}

export type WorkflowNodeData = {
  label?: string
  url?: string
  item_selector?: string
  fields?: ExtractionField[]
  pagination_selector?: string
  pagination_strategy?: string
  max_pages?: number
  max_items?: number
  max_steps?: number
  condition?: string
  [key: string]: unknown
}

export type WorkflowNode = Node<WorkflowNodeData, WorkflowNodeType>
export type WorkflowEdge = Edge
export type CanonicalWorkflowEdge = { id: string; source: string; target: string }
export type CanonicalWorkflowNode = { id: string; type: WorkflowNodeType; data: WorkflowNodeData }

export type WorkflowGraph = {
  nodes: CanonicalWorkflowNode[]
  edges: CanonicalWorkflowEdge[]
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
    return { id: candidate.id, type: candidate.type, data: candidate.data as WorkflowNodeData }
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
    return { id: candidate.id, source: candidate.source, target: candidate.target }
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
