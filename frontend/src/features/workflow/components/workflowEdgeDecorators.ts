import { MarkerType } from '@xyflow/react'
import type { WorkflowEdge } from '../workflowState'
import type { WorkflowBranch, WorkflowNodeType } from '../workflowContracts'

type NormalizedBranch = 'true' | 'false' | 'default' | null

const BRANCH_COLOR: Record<Exclude<NormalizedBranch, null>, string> = {
  true: '#16a34a',
  false: '#dc2626',
  default: '#64748b',
}

function normalizeBranch(branch: WorkflowBranch | undefined): NormalizedBranch {
  if (branch === true || branch === 'true') return 'true'
  if (branch === false || branch === 'false') return 'false'
  if (branch === 'default') return 'default'
  return null
}

function composeEdgeLabel(edge: WorkflowEdge, branch: Exclude<NormalizedBranch, null>): string {
  const baseLabel = typeof edge.label === 'string' && edge.label.trim() ? edge.label.trim() : branch.toUpperCase()
  if (typeof edge.order === 'number' && Number.isFinite(edge.order)) {
    return `${baseLabel} · ${edge.order}`
  }
  return baseLabel
}

const SOURCE_EDGE_COLOR: Partial<Record<WorkflowNodeType, string>> = {
  open_page: '#3b82f6',
  select_list: '#0ea5e9',
  loop: '#06b6d4',
  extract_field: '#14b8a6',
  paginate: '#f59e0b',
  emit_record: '#16a34a',
  end: '#64748b',
}

function resolveSemanticLabel(edge: WorkflowEdge, sourceType?: WorkflowNodeType) {
  const explicitLabel = typeof edge.label === 'string' ? edge.label.trim() : ''
  if (explicitLabel) return explicitLabel
  if (sourceType === 'paginate') return 'NEXT PAGE'
  if (sourceType === 'loop') return 'ITERATE'
  if (sourceType === 'emit_record') return 'FLUSH'
  return ''
}

export function decorateWorkflowEdges(
  edges: WorkflowEdge[],
  sourceNodeTypeById: Partial<Record<string, WorkflowNodeType>> = {},
): WorkflowEdge[] {
  return edges.map((edge) => {
    const branch = normalizeBranch(edge.branch)
    if (!branch) {
      const sourceType = sourceNodeTypeById[edge.source]
      const semanticLabel = resolveSemanticLabel(edge, sourceType)
      const semanticColor = sourceType ? SOURCE_EDGE_COLOR[sourceType] ?? '#60a5fa' : '#60a5fa'
      return {
        ...edge,
        label: semanticLabel || edge.label,
        style: semanticColor === '#60a5fa'
          ? edge.style
          : { ...(edge.style ?? {}), stroke: semanticColor, strokeWidth: 2.4, strokeDasharray: sourceType === 'paginate' ? '8 4' : undefined },
        labelStyle: semanticLabel
          ? { fill: '#0f172a', fontWeight: 700, fontSize: 10.5, letterSpacing: 0.2 }
          : edge.labelStyle,
        labelBgStyle: semanticLabel
          ? { fill: 'rgba(255,255,255,0.9)', stroke: semanticColor, strokeWidth: 1, rx: 8, ry: 8 }
          : edge.labelBgStyle,
        labelBgPadding: semanticLabel ? [8, 4] : edge.labelBgPadding,
        markerEnd: edge.markerEnd ?? { type: MarkerType.ArrowClosed, color: semanticColor },
      }
    }

    const color = BRANCH_COLOR[branch]
    return {
      ...edge,
      label: composeEdgeLabel(edge, branch),
      animated: branch !== 'default',
      style: { ...(edge.style ?? {}), stroke: color, strokeWidth: 2.8 },
      labelStyle: { fill: '#0f172a', fontWeight: 700, fontSize: 11 },
      labelBgStyle: { fill: 'rgba(255,255,255,0.94)', stroke: color, strokeWidth: 1.2, rx: 8, ry: 8 },
      labelBgPadding: [8, 4],
      markerEnd: { type: MarkerType.ArrowClosed, color },
    }
  })
}
