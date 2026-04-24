import { describe, expect, it } from 'vitest'
import { resolveNextNodeId, resolveNextNodePosition } from './workflowNodePlacement'
import type { WorkflowNode } from './workflowState'

const baseNodes: WorkflowNode[] = [
  {
    id: 'open-page-1',
    type: 'open_page',
    data: { label: 'open' },
    position: { x: 60, y: 120 },
  },
  {
    id: 'select-list-1',
    type: 'select_list',
    data: { label: 'list' },
    position: { x: 320, y: 120 },
  },
]

describe('resolveNextNodeId', () => {
  it('increments suffix for same type', () => {
    const id = resolveNextNodeId(baseNodes, 'open_page')
    expect(id).toBe('open-page-2')
  })

  it('skips duplicate id collisions', () => {
    const nodes: WorkflowNode[] = [
      ...baseNodes,
      {
        id: 'loop-1',
        type: 'loop',
        data: { label: 'loop' },
        position: { x: 100, y: 100 },
      },
      {
        id: 'loop-2',
        type: 'open_page',
        data: { label: 'other' },
        position: { x: 200, y: 100 },
      },
    ]
    const id = resolveNextNodeId(nodes, 'loop')
    expect(id).toBe('loop-3')
  })
})

describe('resolveNextNodePosition', () => {
  it('places new nodes away from left palette when palette is open', () => {
    const pos = resolveNextNodePosition(baseNodes, true)
    expect(pos.x).toBeGreaterThanOrEqual(360)
  })

  it('uses compact start position when palette is closed', () => {
    const pos = resolveNextNodePosition(baseNodes, false)
    expect(pos.x).toBe(120 + (baseNodes.length % 3) * 240)
    expect(pos.y).toBe(80 + Math.floor(baseNodes.length / 3) * 120)
  })
})
