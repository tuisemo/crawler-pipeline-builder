import { describe, expect, it, vi } from 'vitest'
import {
  applyDslTextChange,
  graphToFlowState,
  validateGraphShape,
  type WorkflowNode,
} from './workflowState'
import type { WorkflowGraph } from './workflowContracts'

describe('validateGraphShape', () => {
  it('accepts a valid workflow graph', () => {
    const graph = validateGraphShape({
      nodes: [{ id: 'n1', type: 'open_page', data: { url: 'https://example.com' } }],
      edges: [],
    })

    expect(graph.nodes[0].id).toBe('n1')
    expect(graph.nodes[0].type).toBe('open_page')
  })

  it('rejects unsupported node types', () => {
    expect(() =>
      validateGraphShape({
        nodes: [{ id: 'n1', type: 'custom_node', data: {} }],
        edges: [],
      }),
    ).toThrow('unsupported type')
  })

  it('accepts condition edge metadata', () => {
    const graph = validateGraphShape({
      nodes: [{ id: 'n1', type: 'open_page', data: { url: 'https://example.com' } }],
      edges: [{ id: 'e1', source: 'n1', target: 'n1', branch: 'default', label: 'fallback', order: 1 }],
    })
    expect(graph.edges[0].branch).toBe('default')
    expect(graph.edges[0].label).toBe('fallback')
    expect(graph.edges[0].order).toBe(1)
  })
})

describe('graphToFlowState', () => {
  it('preserves previous positions when node ids match', () => {
    const previousNodes: WorkflowNode[] = [
      {
        id: 'n1',
        type: 'open_page',
        position: { x: 420, y: 180 },
        data: { url: 'https://example.com' },
      },
    ]
    const graph: WorkflowGraph = {
      nodes: [{ id: 'n1', type: 'open_page', data: { url: 'https://example.com' } }],
      edges: [],
    }

    const state = graphToFlowState(graph, previousNodes)

    expect(state.nodes[0].position).toEqual({ x: 420, y: 180 })
  })
})

describe('applyDslTextChange', () => {
  const baseState = {
    nodes: [
      {
        id: 'n1',
        type: 'open_page',
        position: { x: 0, y: 0 },
        data: { url: 'https://example.com' },
      } as WorkflowNode,
    ],
    edges: [],
    selectedNodeId: 'n1',
  }

  it('applies valid DSL after backend validation', async () => {
    const nextText = JSON.stringify({
      nodes: [
        { id: 'n1', type: 'open_page', data: { url: 'https://example.com' } },
        { id: 'n2', type: 'select_list', data: { item_selector: '.item' } },
      ],
      edges: [{ id: 'e1', source: 'n1', target: 'n2' }],
    })
    const validateGraphWithBackend = vi.fn().mockResolvedValue(undefined)
    const requestTracker = { current: 0 }

    const result = await applyDslTextChange(baseState, nextText, requestTracker, validateGraphWithBackend)

    expect(result.applied).toBe(true)
    expect(result.dslStatus).toBe('synced')
    expect(result.nodes).toHaveLength(2)
    expect(validateGraphWithBackend).toHaveBeenCalledTimes(1)
  })

  it('returns parse-error for invalid JSON', async () => {
    const validateGraphWithBackend = vi.fn()
    const requestTracker = { current: 0 }

    const result = await applyDslTextChange(baseState, '{', requestTracker, validateGraphWithBackend)

    expect(result.applied).toBe(false)
    expect(result.dslStatus).toBe('parse-error')
    expect(validateGraphWithBackend).not.toHaveBeenCalled()
  })

  it('returns schema-error when backend validation rejects the graph', async () => {
    const nextText = JSON.stringify({
      nodes: [{ id: 'n1', type: 'open_page', data: { url: 'https://example.com' } }],
      edges: [],
    })
    const validateGraphWithBackend = vi.fn().mockRejectedValue(new Error('Backend rejected graph'))
    const requestTracker = { current: 0 }

    const result = await applyDslTextChange(baseState, nextText, requestTracker, validateGraphWithBackend)

    expect(result.applied).toBe(false)
    expect(result.dslStatus).toBe('schema-error')
    expect(result.dslFeedback).toContain('Backend rejected graph')
  })

  it('ignores stale backend validation responses', async () => {
    const nextText = JSON.stringify({
      nodes: [{ id: 'n1', type: 'open_page', data: { url: 'https://example.com' } }],
      edges: [],
    })
    const requestTracker = { current: 0 }
    const validateGraphWithBackend = vi.fn().mockImplementation(async () => {
      requestTracker.current = 2
    })

    const result = await applyDslTextChange(baseState, nextText, requestTracker, validateGraphWithBackend)

    expect(result.applied).toBe(false)
    expect(result.requestId).toBe(1)
    expect(result.dslFeedback).toContain('Stale DSL validation ignored.')
  })
})
