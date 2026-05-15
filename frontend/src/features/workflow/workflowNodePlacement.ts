import dagre from 'dagre'
import type { WorkflowNode, WorkflowEdge } from './workflowState'
import type { WorkflowNodeType } from './workflowContracts'

const NODE_WIDTH = 230
const NODE_HEIGHT = 100

// Existing grid-based placement logic for newly added nodes
const GRID_COLUMNS = 3
const GRID_X_GAP = 240
const GRID_Y_GAP = 120
const GRID_START_Y = 80

function toNodeIdPrefix(type: WorkflowNodeType): string {
  return type.replaceAll('_', '-')
}

function parseNodeSuffix(id: string): number | null {
  const match = id.match(/-(\d+)$/)
  if (!match) return null
  const parsed = Number(match[1])
  return Number.isFinite(parsed) ? parsed : null
}

export function resolveNextNodeId(currentNodes: WorkflowNode[], type: WorkflowNodeType): string {
  const prefix = toNodeIdPrefix(type)
  const used = new Set(currentNodes.map((node) => node.id))
  const maxSuffix = currentNodes
    .filter((node) => node.type === type)
    .map((node) => parseNodeSuffix(node.id))
    .filter((value): value is number => typeof value === 'number')
    .reduce((max, value) => Math.max(max, value), 0)

  let nextSuffix = maxSuffix + 1
  let candidate = `${prefix}-${nextSuffix}`
  while (used.has(candidate)) {
    nextSuffix += 1
    candidate = `${prefix}-${nextSuffix}`
  }
  return candidate
}

export function resolveNextNodePosition(currentNodes: WorkflowNode[], paletteOpen: boolean) {
  const safeStartX = paletteOpen ? 360 : 120
  const index = currentNodes.length
  const col = index % GRID_COLUMNS
  const row = Math.floor(index / GRID_COLUMNS)
  return {
    x: safeStartX + col * GRID_X_GAP,
    y: GRID_START_Y + row * GRID_Y_GAP,
  }
}

/**
 * Automatically optimize the layout of nodes using the dagre library.
 * This provides a cleaner hierarchical layout than basic grid or topological sorting.
 */
export function autoLayoutNodes(
  nodes: WorkflowNode[],
  edges: WorkflowEdge[],
  direction = 'LR'
): WorkflowNode[] {
  if (nodes.length === 0) return []

  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))
  dagreGraph.setGraph({ rankdir: direction, nodesep: 70, ranksep: 120 })

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  })

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })

  dagre.layout(dagreGraph)

  return nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id)
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - NODE_WIDTH / 2,
        y: nodeWithPosition.y - NODE_HEIGHT / 2,
      },
    }
  })
}
