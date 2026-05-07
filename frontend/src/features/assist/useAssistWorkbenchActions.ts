import { useState, type Dispatch, type SetStateAction } from 'react'
import { postAssistAction } from '../../services/workflowApi'
import { getErrorMessage, type WorkflowNode } from '../workflow/workflowState'
import type { ExtractionField, WorkflowNodeData } from '../workflow/workflowContracts'
import { buildRuntimeAgentId, type ExecutionMode } from '../runtime/executionTarget'

export type AssistActionKey =
  | 'auto-detect'
  | 'optimize-selector'
  | 'infer-fields'
  | 'analyze-pagination'
  | 'test-selector'
  | null

export type AssistApplyMode = 'current-only' | 'related-nodes'

type AssistNotifier = {
  success: (content: string) => void
  warning: (content: string) => void
  error: (content: string) => void
}

type UseAssistWorkbenchActionsArgs = {
  nodes: WorkflowNode[]
  selectedNode: WorkflowNode | null
  setNodes: Dispatch<SetStateAction<WorkflowNode[]>>
  updateSelectedNodeData: (patch: Partial<WorkflowNodeData>) => void
  notify: AssistNotifier
  executionMode: ExecutionMode
  agentId: string
}

function normalizeAssistError(payload: unknown, responseOk: boolean) {
  if (!responseOk) return getErrorMessage(payload)
  const record = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {}
  if (record.success === false) return getErrorMessage(payload)
  return ''
}

function mapAssistFields(rawFields: unknown): ExtractionField[] {
  if (!Array.isArray(rawFields)) return []
  return rawFields.reduce<ExtractionField[]>((acc, field) => {
    if (!field || typeof field !== 'object') return acc
    const row = field as Record<string, unknown>
    const name = typeof row.name === 'string' ? row.name : ''
    const selector = typeof row.selector === 'string' ? row.selector : ''
    const type = typeof row.type === 'string' ? row.type : 'text'
    if (!name || !selector) return acc
    acc.push({ name, selector, type })
    return acc
  }, [])
}

export function useAssistWorkbenchActions({
  nodes,
  selectedNode,
  setNodes,
  updateSelectedNodeData,
  notify,
  executionMode,
  agentId,
}: UseAssistWorkbenchActionsArgs) {
  const [assistBusyAction, setAssistBusyAction] = useState<AssistActionKey>(null)
  const [assistApplyMode, setAssistApplyMode] = useState<AssistApplyMode>('related-nodes')
  const [assistSessionId, setAssistSessionId] = useState<string | null>(null)

  function getEntryUrl() {
    const entry = nodes.find((node) => node.type === 'open_page')
    const url = entry?.data.url
    return typeof url === 'string' ? url.trim() : ''
  }

  function getPrimarySelectListNode() {
    return nodes.find((node) => node.type === 'select_list') ?? null
  }

  function withAssistSession<T extends Record<string, unknown>>(payload: T): T & { session_id?: string; agent_id?: string } {
    const result: Record<string, unknown> = { ...payload }
    if (assistSessionId) result.session_id = assistSessionId
    const runtimeAgentId = buildRuntimeAgentId(executionMode, agentId)
    if (runtimeAgentId) result.agent_id = runtimeAgentId
    return result as T & { session_id?: string; agent_id?: string }
  }

  function syncAssistSession(payload: unknown) {
    if (!payload || typeof payload !== 'object') return
    const record = payload as Record<string, unknown>
    if (typeof record.session_id === 'string' && record.session_id.trim()) {
      setAssistSessionId(record.session_id)
    }
  }

  function runWithAssistLock(action: Exclude<AssistActionKey, null>, task: () => Promise<void>) {
    if (assistBusyAction) return
    setAssistBusyAction(action)
    task()
      .catch((error) => {
        const msg = error instanceof Error ? error.message : '辅助操作失败'
        notify.error(msg)
      })
      .finally(() => setAssistBusyAction(null))
  }

  function handleAutoDetectSelectList() {
    runWithAssistLock('auto-detect', async () => {
      if (!selectedNode || selectedNode.type !== 'select_list') return
      const entryUrl = getEntryUrl()
      const { response, payload } = await postAssistAction('/api/assist/auto-detect', withAssistSession({
        url: entryUrl || undefined,
      }))
      const error = normalizeAssistError(payload, response.ok)
      if (error) throw new Error(error)
      syncAssistSession(payload)

      const record = payload as Record<string, unknown>
      const result = (record.result && typeof record.result === 'object') ? record.result as Record<string, unknown> : {}
      const detectedSelector = typeof result.item_selector === 'string' ? result.item_selector : ''
      if (detectedSelector) {
        updateSelectedNodeData({ item_selector: detectedSelector })
      }

      const detectedFields = mapAssistFields(result.fields)
      if (detectedFields.length > 0 && assistApplyMode === 'related-nodes') {
        setNodes((current) => {
          let patched = false
          return current.map((node) => {
            if (!patched && node.type === 'extract_field') {
              patched = true
              return { ...node, data: { ...node.data, fields: detectedFields } }
            }
            return node
          })
        })
      }

      const detectedPaginationSelector = typeof result.pagination_selector === 'string' ? result.pagination_selector : ''
      const detectedPaginationStrategy = typeof result.pagination_strategy === 'string' ? result.pagination_strategy : ''
      if ((detectedPaginationSelector || detectedPaginationStrategy) && assistApplyMode === 'related-nodes') {
        setNodes((current) => {
          let patched = false
          return current.map((node) => {
            if (!patched && node.type === 'paginate') {
              patched = true
              return {
                ...node,
                data: {
                  ...node.data,
                  pagination_selector: detectedPaginationSelector || node.data.pagination_selector,
                  pagination_strategy: detectedPaginationStrategy || node.data.pagination_strategy,
                },
              }
            }
            return node
          })
        })
      }
      notify.success('自动检测结果已回填')
    })
  }

  function handleOptimizeListSelector() {
    runWithAssistLock('optimize-selector', async () => {
      if (!selectedNode || selectedNode.type !== 'select_list') return
      const selector = typeof selectedNode.data.item_selector === 'string' ? selectedNode.data.item_selector.trim() : ''
      if (!selector) throw new Error('请先填写列表选择器')
      const entryUrl = getEntryUrl()
      const extractResult = await postAssistAction('/api/assist/extract-html', withAssistSession({
        item_selector: selector,
        url: entryUrl || undefined,
      }))
      const extractError = normalizeAssistError(extractResult.payload, extractResult.response.ok)
      if (extractError) throw new Error(extractError)
      syncAssistSession(extractResult.payload)
      const extractPayload = extractResult.payload as Record<string, unknown>
      const htmlFragment = typeof extractPayload.html_fragment === 'string' ? extractPayload.html_fragment : ''
      if (!htmlFragment) throw new Error('未提取到 HTML 片段，无法优化选择器')

      const optimizeResult = await postAssistAction('/api/assist/optimize-selector', withAssistSession({
        initial_selector: selector,
        html_fragment: htmlFragment,
      }))
      const optimizeError = normalizeAssistError(optimizeResult.payload, optimizeResult.response.ok)
      if (optimizeError) throw new Error(optimizeError)

      const optimizePayload = optimizeResult.payload as Record<string, unknown>
      const result = (optimizePayload.result && typeof optimizePayload.result === 'object') ? optimizePayload.result as Record<string, unknown> : {}
      const optimizedSelector = typeof result.optimized_selector === 'string' ? result.optimized_selector.trim() : ''
      if (!optimizedSelector) throw new Error('模型未返回 optimized_selector')

      updateSelectedNodeData({ item_selector: optimizedSelector })
      notify.success('已应用优化后的列表选择器')
    })
  }

  function handleInferExtractFields() {
    runWithAssistLock('infer-fields', async () => {
      if (!selectedNode || selectedNode.type !== 'extract_field') return
      const selectListNode = getPrimarySelectListNode()
      const itemSelector = typeof selectListNode?.data.item_selector === 'string' ? selectListNode.data.item_selector.trim() : ''
      if (!itemSelector) throw new Error('请先配置 select_list 节点的 item_selector')

      const existingHtml = typeof selectedNode.data.html_fragment === 'string' ? selectedNode.data.html_fragment : ''
      let htmlFragment = existingHtml
      if (!htmlFragment) {
        const entryUrl = getEntryUrl()
        const extractResult = await postAssistAction('/api/assist/extract-html', withAssistSession({
          item_selector: itemSelector,
          url: entryUrl || undefined,
        }))
        const extractError = normalizeAssistError(extractResult.payload, extractResult.response.ok)
        if (extractError) throw new Error(extractError)
        syncAssistSession(extractResult.payload)
        const extractPayload = extractResult.payload as Record<string, unknown>
        htmlFragment = typeof extractPayload.html_fragment === 'string' ? extractPayload.html_fragment : ''
      }
      if (!htmlFragment) throw new Error('未提取到 HTML 片段，无法推断字段')

      const inferResult = await postAssistAction('/api/assist/infer-fields', withAssistSession({
        html_fragment: htmlFragment,
      }))
      const inferError = normalizeAssistError(inferResult.payload, inferResult.response.ok)
      if (inferError) throw new Error(inferError)
      const inferPayload = inferResult.payload as Record<string, unknown>
      const result = (inferPayload.result && typeof inferPayload.result === 'object') ? inferPayload.result as Record<string, unknown> : {}
      const inferredFields = mapAssistFields(result.fields)
      if (inferredFields.length === 0) throw new Error('模型未返回可用字段')

      updateSelectedNodeData({
        fields: inferredFields,
        html_fragment: htmlFragment,
      })
      const inferredItemSelector = typeof result.item_selector === 'string' ? result.item_selector.trim() : ''
      if (assistApplyMode === 'related-nodes' && inferredItemSelector) {
        setNodes((current) => {
          let patched = false
          return current.map((node) => {
            if (!patched && node.type === 'select_list') {
              patched = true
              return { ...node, data: { ...node.data, item_selector: inferredItemSelector } }
            }
            return node
          })
        })
      }
      notify.success('AI 字段推断已应用')
    })
  }

  function handleAnalyzePagination() {
    runWithAssistLock('analyze-pagination', async () => {
      if (!selectedNode || selectedNode.type !== 'paginate') return
      const selectListNode = getPrimarySelectListNode()
      const itemSelector = typeof selectListNode?.data.item_selector === 'string' ? selectListNode.data.item_selector.trim() : ''
      if (!itemSelector) throw new Error('请先配置 select_list 节点的 item_selector')

      const entryUrl = getEntryUrl()
      const extractResult = await postAssistAction('/api/assist/extract-html', withAssistSession({
        item_selector: itemSelector,
        url: entryUrl || undefined,
        include_pagination: true,
      }))
      const extractError = normalizeAssistError(extractResult.payload, extractResult.response.ok)
      if (extractError) throw new Error(extractError)
      syncAssistSession(extractResult.payload)
      const extractPayload = extractResult.payload as Record<string, unknown>
      const htmlFragment = typeof extractPayload.html_fragment === 'string' ? extractPayload.html_fragment : ''
      if (!htmlFragment) throw new Error('未提取到 HTML 片段，无法分析分页')

      const analyzeResult = await postAssistAction('/api/assist/analyze-pagination', withAssistSession({
        html_fragment: htmlFragment,
      }))
      const analyzeError = normalizeAssistError(analyzeResult.payload, analyzeResult.response.ok)
      if (analyzeError) throw new Error(analyzeError)
      const analyzeWarnings = Array.isArray(analyzeResult.envelope.warnings)
        ? analyzeResult.envelope.warnings.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
        : []
      const analyzePayload = analyzeResult.payload as Record<string, unknown>
      const result = (analyzePayload.result && typeof analyzePayload.result === 'object') ? analyzePayload.result as Record<string, unknown> : {}
      const paginationStrategy = typeof result.pagination_strategy === 'string' ? result.pagination_strategy : ''
      const nextSelector = typeof result.next_button_selector === 'string' ? result.next_button_selector : ''

      updateSelectedNodeData({
        pagination_strategy: paginationStrategy || selectedNode.data.pagination_strategy,
        pagination_selector: nextSelector || selectedNode.data.pagination_selector,
      })
      const inferredItemSelector = typeof result.item_selector === 'string' ? result.item_selector.trim() : ''
      if (assistApplyMode === 'related-nodes' && inferredItemSelector) {
        setNodes((current) => {
          let patched = false
          return current.map((node) => {
            if (!patched && node.type === 'select_list') {
              patched = true
              return { ...node, data: { ...node.data, item_selector: inferredItemSelector } }
            }
            return node
          })
        })
      }
      if (analyzeWarnings.length > 0) {
        notify.warning(analyzeWarnings[0])
      } else {
        notify.success('分页策略分析结果已应用')
      }
    })
  }

  function handleTestSelector(selector: string, selectorLabel: string) {
    runWithAssistLock('test-selector', async () => {
      const normalizedSelector = selector.trim()
      if (!normalizedSelector) throw new Error(`请先填写${selectorLabel}`)
      const entryUrl = getEntryUrl()
      const testResult = await postAssistAction('/api/assist/test-selector', withAssistSession({
        selector: normalizedSelector,
        url: entryUrl || undefined,
        clear_after_ms: 2200,
      }))
      const testError = normalizeAssistError(testResult.payload, testResult.response.ok)
      if (testError) throw new Error(testError)
      syncAssistSession(testResult.payload)

      const payload = testResult.payload as Record<string, unknown>
      const result = payload.result && typeof payload.result === 'object'
        ? payload.result as Record<string, unknown>
        : {}
      const matchCount = typeof result.match_count === 'number' ? result.match_count : 0
      const highlightedCount = typeof result.highlighted_count === 'number' ? result.highlighted_count : matchCount
      const clearAfterMs = typeof result.clear_after_ms === 'number' ? result.clear_after_ms : 2200
      if (matchCount <= 0) {
        notify.warning(`${selectorLabel}测试完成：未匹配到元素，请检查选择器。`)
        return
      }
      notify.success(`${selectorLabel}测试通过：匹配 ${matchCount} 个元素，已临时高亮 ${highlightedCount} 个元素，约 ${Math.round(clearAfterMs / 100) / 10} 秒后自动恢复。`)
    })
  }

  return {
    assistBusyAction,
    assistApplyMode,
    setAssistApplyMode,
    handleAutoDetectSelectList,
    handleOptimizeListSelector,
    handleInferExtractFields,
    handleAnalyzePagination,
    handleTestSelector,
  }
}
