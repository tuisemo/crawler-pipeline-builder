import { describe, expect, test, vi } from 'vitest'
import {
  applyDslTextChange,
  toCanonicalGraph,
  type DslApplyState,
  type WorkflowEdge,
  type WorkflowGraph,
  type WorkflowNode,
} from './workflowState'

const baseNodes: WorkflowNode[] = [
  {
    id: 'open-page-1',
    type: 'open_page',
    position: { x: 10, y: 20 },
    data: { label: 'Open Page', url: 'https://quotes.toscrape.com/' },
  },
]

const baseEdges: WorkflowEdge[] = []

function createState(overrides: Partial<DslApplyState> = {}): DslApplyState {
  return {
    nodes: baseNodes,
    edges: baseEdges,
    selectedNodeId: 'open-page-1',
    ...overrides,
  }
}

describe('workflow DSL synchronization state', () => {
  test('preserves the last valid graph when Monaco contains malformed JSON', async () => {
    const state = createState()

    const result = await applyDslTextChange(state, '{"nodes": [', { current: 0 }, async () => undefined)

    expect(result.dslStatus).toBe('parse-error')
    expect(result.dslFeedback).toContain('Unexpected')
    expect(result.nodes).toBe(state.nodes)
    expect(result.edges).toBe(state.edges)
    expect(result.selectedNodeId).toBe('open-page-1')
  })

  test('preserves the last valid graph when schema validation rejects parsed JSON', async () => {
    const state = createState()
    const schemaInvalidText = JSON.stringify({ nodes: [], edges: [] }, null, 2)

    const result = await applyDslTextChange(state, schemaInvalidText, { current: 0 }, async () => {
      throw new Error('Workflow must contain at least one node.')
    })

    expect(result.dslStatus).toBe('schema-error')
    expect(result.dslFeedback).toBe('Workflow must contain at least one node.')
    expect(result.nodes).toBe(state.nodes)
    expect(result.edges).toBe(state.edges)
    expect(result.dslText).toBe(schemaInvalidText)
  })

  test('applies only the newest async validation result when older validation resolves later', async () => {
    const staleGraph: WorkflowGraph = {
      nodes: [{ id: 'open-page-stale', type: 'open_page', data: { label: 'Stale', url: 'https://stale.example' } }],
      edges: [],
    }
    const currentGraph: WorkflowGraph = {
      nodes: [{ id: 'open-page-current', type: 'open_page', data: { label: 'Current', url: 'https://current.example' } }],
      edges: [],
    }
    let resolveStaleValidation!: () => void
    const requestTracker = { current: 0 }
    const validate = vi
      .fn<() => Promise<void>>()
      .mockImplementationOnce(() => new Promise<void>((resolve) => {
        resolveStaleValidation = resolve
      }))
      .mockResolvedValueOnce(undefined)

    const stalePromise = applyDslTextChange(createState(), JSON.stringify(staleGraph), requestTracker, validate)
    const currentResult = await applyDslTextChange(createState(), JSON.stringify(currentGraph), requestTracker, validate)
    resolveStaleValidation()
    const staleResult = await stalePromise

    expect(currentResult.applied).toBe(true)
    expect(currentResult.nodes[0]?.id).toBe('open-page-current')
    expect(currentResult.selectedNodeId).toBe('open-page-current')
    expect(staleResult.applied).toBe(false)
    expect(staleResult.nodes).toBe(baseNodes)
    expect(requestTracker.current).toBe(2)
  })

  test('canvas-to-editor synchronization emits stable canonical node and edge JSON', () => {
    const nodes: WorkflowNode[] = [
      ...baseNodes,
      {
        id: 'select-list-1',
        type: 'select_list',
        position: { x: 200, y: 20 },
        data: { label: 'Select List', item_selector: '.quote' },
      },
    ]
    const edges: WorkflowEdge[] = [{ id: 'edge-open-select', source: 'open-page-1', target: 'select-list-1' }]

    expect(toCanonicalGraph(nodes, edges)).toEqual({
      nodes: [
        { id: 'open-page-1', type: 'open_page', data: { label: 'Open Page', url: 'https://quotes.toscrape.com/' } },
        { id: 'select-list-1', type: 'select_list', data: { label: 'Select List', item_selector: '.quote' } },
      ],
      edges: [{ id: 'edge-open-select', source: 'open-page-1', target: 'select-list-1' }],
    })
  })
})
