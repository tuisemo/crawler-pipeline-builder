import { describe, expect, it } from 'vitest'
import { decorateWorkflowEdges } from './workflowEdgeDecorators'
import type { WorkflowEdge } from '../workflowState'

describe('decorateWorkflowEdges', () => {
  it('adds condition branch visual metadata for true branch', () => {
    const edges: WorkflowEdge[] = [
      { id: 'e1', source: 'c1', target: 'n1', branch: 'true', order: 0 },
    ]
    const [decorated] = decorateWorkflowEdges(edges)

    expect(decorated.label).toBe('TRUE · 0')
    expect(decorated.animated).toBe(true)
    expect(decorated.style?.stroke).toBe('#16a34a')
    expect((decorated.markerEnd as { color?: string })?.color).toBe('#16a34a')
  })

  it('normalizes boolean branch and keeps custom label', () => {
    const edges: WorkflowEdge[] = [
      { id: 'e2', source: 'c1', target: 'n2', branch: false, label: 'Reject' },
    ]
    const [decorated] = decorateWorkflowEdges(edges)

    expect(decorated.label).toBe('Reject')
    expect(decorated.style?.stroke).toBe('#dc2626')
  })

  it('keeps non-condition edges with default marker', () => {
    const edges: WorkflowEdge[] = [
      { id: 'e3', source: 'n1', target: 'n2' },
    ]
    const [decorated] = decorateWorkflowEdges(edges)

    expect(decorated.style).toBeUndefined()
    expect((decorated.markerEnd as { color?: string })?.color).toBe('#60a5fa')
  })

  it('adds semantic label and stroke for pagination edges', () => {
    const edges: WorkflowEdge[] = [
      { id: 'e4', source: 'p1', target: 's1' },
    ]
    const [decorated] = decorateWorkflowEdges(edges, { p1: 'paginate' })

    expect(decorated.label).toBe('NEXT PAGE')
    expect(decorated.style?.stroke).toBe('#f59e0b')
    expect((decorated.markerEnd as { color?: string })?.color).toBe('#f59e0b')
  })
})
