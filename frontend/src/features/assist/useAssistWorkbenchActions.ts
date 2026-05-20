import { useState, type Dispatch, type SetStateAction } from 'react'
import { postAssistAction } from '../../services/workflowApi'
import {
  autoDetectLocally,
  extractHtmlLocally,
  extractPaginationContextLocally,
  testSelectorLocally,
} from '../runtime/extensionBridge'
import { getErrorMessage, type WorkflowNode } from '../workflow/workflowState'
import type { AssistApplyMode, ExtractionField, WorkflowNodeData } from '../workflow/workflowContracts'

export type AssistActionKey =
  | 'auto-detect'
  | 'optimize-selector'
  | 'infer-fields'
  | 'analyze-pagination'
  | 'test-selector'
  | null


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
}: UseAssistWorkbenchActionsArgs) {
  const [assistBusyAction, setAssistBusyAction] = useState<AssistActionKey>(null)
  const [assistApplyMode, setAssistApplyMode] = useState<AssistApplyMode>('related-nodes')

  function getEntryUrl() {
    const entryNode = nodes.find((node) => node.type === 'open_page')
    const rawUrl = typeof entryNode?.data.url === 'string' ? entryNode.data.url.trim() : ''
    return rawUrl
  }

  function requireEntryUrl() {
    const entryUrl = getEntryUrl()
    if (!entryUrl) {
      throw new Error('请先配置 open_page 节点的目标 URL，扩展将基于该地址打开或复用目标标签页。')
    }
    return entryUrl
  }

  function getPrimarySelectListNode() {
    return nodes.find((node) => node.type === 'select_list') ?? null
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

      const result = await autoDetectLocally(requireEntryUrl())
      if (result.itemSelector) {
        updateSelectedNodeData({ item_selector: result.itemSelector })
      }

      const detectedFields = mapAssistFields(result.fields)
      if (detectedFields.length > 0 && assistApplyMode === 'related-nodes') {
        setNodes((current) => {
          let patched = false
          return current.map((node) => {
            if (!patched && node.type === 'extract_field') {
              patched = true
              return { ...node, data: { ...node.data, fields: detectedFields, html_fragment: result.htmlFragment } }
            }
            return node
          })
        })
      }

      if ((result.paginationSelector || result.paginationStrategy) && assistApplyMode === 'related-nodes') {
        setNodes((current) => {
          let patched = false
          return current.map((node) => {
            if (!patched && node.type === 'paginate') {
              patched = true
              return {
                ...node,
                data: {
                  ...node.data,
                  pagination_selector: result.paginationSelector || node.data.pagination_selector,
                  pagination_strategy: result.paginationStrategy || node.data.pagination_strategy,
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
      const entryUrl = requireEntryUrl()

      const extractResult = await extractHtmlLocally(selector, 3, entryUrl)
      const htmlFragment = extractResult.htmlFragment
      if (!htmlFragment) throw new Error('未提取到 HTML 片段，无法优化选择器')

      const optimizeResult = await postAssistAction('/api/assist/optimize-selector', {
        initial_selector: selector,
        html_fragment: htmlFragment,
      })
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

  function handleInferExtractFields(userIntent?: string) {
    runWithAssistLock('infer-fields', async () => {
      if (!selectedNode || selectedNode.type !== 'extract_field') return
      const selectListNode = getPrimarySelectListNode()
      const itemSelector = typeof selectListNode?.data.item_selector === 'string' ? selectListNode.data.item_selector.trim() : ''
      if (!itemSelector) throw new Error('请先配置 select_list 节点的 item_selector')
      const entryUrl = requireEntryUrl()

      const existingHtml = typeof selectedNode.data.html_fragment === 'string' ? selectedNode.data.html_fragment : ''
      const htmlFragment = existingHtml || (await extractHtmlLocally(itemSelector, 3, entryUrl)).htmlFragment
      if (!htmlFragment) throw new Error('未提取到 HTML 片段，无法推断字段')

      const requestBody: Record<string, unknown> = {
        html_fragment: htmlFragment,
      }
      if (userIntent && userIntent.trim()) {
        requestBody.user_intent = userIntent.trim()
      }

      const inferResult = await postAssistAction('/api/assist/infer-fields', requestBody)
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

      notify.success('AI 字段推断已应用')
    })
  }

  function handleAnalyzePagination() {
    runWithAssistLock('analyze-pagination', async () => {
      if (!selectedNode || selectedNode.type !== 'paginate') return
      const entryUrl = requireEntryUrl()

      const context = await extractPaginationContextLocally(entryUrl)
      if (!context.htmlFragment || !context.prunedBodyHtml) {
        throw new Error('未提取到分页分析所需的页面证据。请检查：\n1. open_page URL 是否可访问\n2. 目标页面是否已完整加载\n3. 页面中是否存在可见的分页区域或翻页控件')
      }

      const analyzeResult = await postAssistAction('/api/assist/analyze-pagination', {
        html_fragment: context.htmlFragment,
        pruned_body_html: context.prunedBodyHtml,
        pagination_component_html: context.paginationComponentHtml || undefined,
      })
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
      const entryUrl = requireEntryUrl()

      const result = await testSelectorLocally(normalizedSelector, 2200, 5, entryUrl)
      if (result.matchCount <= 0) {
        notify.warning(`${selectorLabel}测试完成：未匹配到元素，请检查选择器。`)
        return
      }
      notify.success(`${selectorLabel}测试通过：匹配 ${result.matchCount} 个元素，已临时高亮 ${result.highlightedCount} 个元素，约 ${Math.round(result.clearAfterMs / 100) / 10} 秒后自动恢复。`)
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
