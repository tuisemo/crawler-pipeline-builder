import type { WorkflowNode } from './workflowState'
import type { WorkflowNodeType } from './workflowContracts'
import type { WorkflowEdge } from './workflowState'

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

export function autoLayoutNodes(
  nodes: WorkflowNode[],
  edges: WorkflowEdge[]
): WorkflowNode[] {
  const inDegree: Record<string, number> = {}
  const adj: Record<string, string[]> = {}

  nodes.forEach((n) => {
    inDegree[n.id] = 0
    adj[n.id] = []
  })

  edges.forEach((e) => {
    if (adj[e.source] && inDegree[e.target] !== undefined) {
      adj[e.source].push(e.target)
      inDegree[e.target]++
    }
  })

  const queue: string[] = []
  nodes.forEach((n) => {
    if (inDegree[n.id] === 0) queue.push(n.id)
  })

  const nodeRank: Record<string, number> = {}
  const layers: string[][] = []
  let currentLayer = queue
  let rank = 0

  while (currentLayer.length > 0) {
    layers.push([...currentLayer])
    const nextLayer: string[] = []

    currentLayer.forEach((id) => {
      nodeRank[id] = rank
      adj[id].forEach((target) => {
        inDegree[target]--
        if (inDegree[target] === 0) {
          nextLayer.push(target)
        }
      })
    })

    currentLayer = nextLayer
    rank++
  }

  nodes.forEach((n) => {
    if (nodeRank[n.id] === undefined) {
      layers.push([n.id])
      nodeRank[n.id] = layers.length - 1
    }
  })

  const startX = 60
  const startY = 140
  const xGap = 280
  const yGap = 160

  const layoutedNodes = nodes.map((node) => ({ ...node }))
  const layoutedMap = new Map(layoutedNodes.map((n) => [n.id, n]))

  layers.forEach((layerNodes, layerIndex) => {
    const x = startX + layerIndex * xGap
    const totalLayerHeight = (layerNodes.length - 1) * yGap
    const layerStartY = startY - totalLayerHeight / 2

    layerNodes.forEach((nodeId, i) => {
      const node = layoutedMap.get(nodeId)
      if (node) {
        node.position = {
          x,
          y: Math.max(80, layerStartY + i * yGap),
        }
      }
    })
  })

  return layoutedNodes
}
