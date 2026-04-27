import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { loader } from '@monaco-editor/react'
import { App as AntdApp, Button, Drawer, Tabs, Tag, Typography } from 'antd'
import {
  AppstoreOutlined,
  BarsOutlined,
  LayoutOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import {
  MarkerType,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import './App.css'
import {
  applyDslTextChange,
  getErrorMessage,
  toCanonicalGraph,
  type DslStatus,
  type WorkflowEdge,
  type WorkflowNode,
} from './workflowState'
import type { CanonicalWorkflowEdge, ExtractionField, ScriptGenerationMode, WorkflowNodeData, WorkflowNodeType } from './workflowContracts'
import { DslEditorPanel } from './components/DslEditorPanel'
import { NodePalette, type PaletteItem } from './components/NodePalette'
import { PropertyPanel } from './components/PropertyPanel'
import { ResultsPanel } from './components/ResultsPanel'
import { WorkbenchToolbar, type WorkbenchAction } from './components/WorkbenchToolbar'
import { WorkflowCanvas } from './components/WorkflowCanvas'
import { useWorkflowActions } from './hooks/useWorkflowActions'
import {
  buildWorkflowGraphKey,
  extractEditablePrompt,
  loadSavedPromptDrafts,
  persistSavedPromptDrafts,
  type SavedPromptDraftMap,
} from './promptDrafts'
import { postAssistAction, validateGraphWithBackend } from './services/workflowApi'
import { resolveNextNodeId, resolveNextNodePosition, autoLayoutNodes } from './workflowNodePlacement'

loader.config({ paths: { vs: '/monaco-editor/min/vs' } })

function clampNumberInput(value: string, min: number, max: number, fallback: number) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(Math.max(parsed, min), max)
}

function toPositiveLimit(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return null
  return Math.trunc(value)
}

const paletteItems: PaletteItem[] = [
  { type: 'open_page', label: 'open_page', detail: '设置目标页面地址与访问边界' },
  { type: 'select_list', label: 'select_list', detail: '定位页面中重复的列表容器' },
  { type: 'loop', label: 'loop', detail: '逐项遍历上游列表，配置上限与容错策略' },
  { type: 'extract_field', label: 'extract_field', detail: '从当前项中抽取结构化字段' },
  { type: 'condition', label: 'condition', detail: '按白名单条件切分执行路径（true/false）' },
  { type: 'paginate', label: 'paginate', detail: '处理翻页并重试下游采集链路' },
  { type: 'emit_record', label: 'emit_record', detail: '提交已抽取的记录结果' },
  { type: 'end', label: 'end', detail: '显式结束当前流程路径' },
]

type AssistActionKey =
  | 'auto-detect'
  | 'optimize-selector'
  | 'infer-fields'
  | 'analyze-pagination'
  | 'clean-data'
  | 'test-selector'
  | null
type AssistApplyMode = 'current-only' | 'related-nodes'
type DockTabKey = 'results' | 'dsl'
type WorkbenchLayoutState = {
  leftPanelOpen: boolean
  rightPanelOpen: boolean
  bottomDockOpen: boolean
  activeDockTab: DockTabKey
}

const WORKBENCH_LAYOUT_STORAGE_KEY = 'sea-data:workbench-layout:v1'
const DEFAULT_WORKBENCH_LAYOUT: WorkbenchLayoutState = {
  leftPanelOpen: true,
  rightPanelOpen: true,
  bottomDockOpen: false,
  activeDockTab: 'results',
}

function loadWorkbenchLayoutState(): WorkbenchLayoutState {
  if (typeof window === 'undefined') return DEFAULT_WORKBENCH_LAYOUT
  try {
    const raw = window.localStorage.getItem(WORKBENCH_LAYOUT_STORAGE_KEY)
    if (!raw) return DEFAULT_WORKBENCH_LAYOUT
    const parsed = JSON.parse(raw) as Partial<WorkbenchLayoutState>
    const activeDockTab: DockTabKey = parsed.activeDockTab === 'dsl' ? 'dsl' : 'results'
    return {
      leftPanelOpen: parsed.leftPanelOpen ?? DEFAULT_WORKBENCH_LAYOUT.leftPanelOpen,
      rightPanelOpen: parsed.rightPanelOpen ?? DEFAULT_WORKBENCH_LAYOUT.rightPanelOpen,
      bottomDockOpen: false, // Always collapse bottom dock by default on load
      activeDockTab,
    }
  } catch {
    return DEFAULT_WORKBENCH_LAYOUT
  }
}

function inferCleanDataType(field: ExtractionField): string {
  const fieldType = String(field.type ?? field.extraction_type ?? '').toLowerCase()
  const fieldName = String(field.name ?? field.field_name ?? '').toLowerCase()

  if (fieldType.includes('href') || fieldType.includes('src') || fieldType.includes('url')) return 'url'
  if (fieldType.includes('bool')) return 'bool'
  if (fieldName.includes('price') || fieldName.includes('金额') || fieldName.includes('价格')) return 'price'
  if (fieldName.includes('date') || fieldName.includes('time') || fieldName.includes('日期') || fieldName.includes('时间')) return 'date'
  if (fieldName.includes('rating') || fieldName.includes('score') || fieldName.includes('评分')) return 'rating'
  if (fieldName.includes('count') || fieldName.includes('total') || fieldName.includes('数量') || fieldName.includes('评论')) return 'count'
  if (fieldName.includes('phone') || fieldName.includes('tel') || fieldName.includes('电话')) return 'phone'
  if (fieldName.includes('mail') || fieldName.includes('email') || fieldName.includes('邮箱')) return 'email'
  return 'text'
}

function createDefaultData(type: WorkflowNodeType): WorkflowNodeData {
  switch (type) {
    case 'open_page':
      return { label: '打开页面', url: '', max_pages: 2, max_steps: 20 }
    case 'select_list':
      return { label: '选择列表', item_selector: '', max_items: 5 }
    case 'loop':
      return { label: '逐项循环', max_items: 5, on_error: 'skip' }
    case 'extract_field':
      return { label: '字段抽取', fields: [{ name: 'title', selector: '', type: 'text' }] }
    case 'condition':
      return { label: '条件判断', condition: '', expression_mode: 'simple' }
    case 'paginate':
      return { label: '分页', pagination_selector: '', pagination_strategy: 'click_next', max_pages: 2 }
    case 'emit_record':
      return { label: '输出记录', output_mode: 'memory', write_mode: 'append', dedupe_keys: [], batch_size: 50 }
    case 'end':
      return { label: '结束' }
  }
}

const initialNodes: WorkflowNode[] = [
  {
    id: 'open-page-1',
    type: 'open_page',
    position: { x: 60, y: 140 },
    data: { label: '打开页面', url: 'https://quotes.toscrape.com/', max_pages: 2, max_steps: 20 },
  },
  {
    id: 'select-list-1',
    type: 'select_list',
    position: { x: 330, y: 140 },
    data: { label: '选择列表', item_selector: '.quote', max_items: 5 },
  },
  {
    id: 'extract-field-1',
    type: 'extract_field',
    position: { x: 600, y: 140 },
    data: { label: '字段抽取', fields: [{ name: 'text', selector: '.text', type: 'text' }] },
  },
]

const initialEdges: WorkflowEdge[] = [
  {
    id: 'edge-open-select',
    source: 'open-page-1',
    target: 'select-list-1',
    markerEnd: { type: MarkerType.ArrowClosed },
  },
  {
    id: 'edge-select-extract',
    source: 'select-list-1',
    target: 'extract-field-1',
    markerEnd: { type: MarkerType.ArrowClosed },
  },
]

export default function App() {
  const { message } = AntdApp.useApp()
  const [initialWorkbenchLayout] = useState<WorkbenchLayoutState>(() => loadWorkbenchLayoutState())
  const [nodes, setNodes] = useState<WorkflowNode[]>(initialNodes)
  const [edges, setEdges] = useState<WorkflowEdge[]>(initialEdges)
  const [selectedNodeId, setSelectedNodeId] = useState(initialNodes[0].id)
  const [dslText, setDslText] = useState(() => JSON.stringify(toCanonicalGraph(initialNodes, initialEdges), null, 2))
  const [dslStatus, setDslStatus] = useState<DslStatus>('synced')
  const [dslFeedback, setDslFeedback] = useState('画布与 DSL 已保持同步。')
  const isApplyingDslRef = useRef(false)
  const dslValidationRequestIdRef = useRef(0)
  const pendingSelectionRef = useRef<string | null>(null)

  const [leftPanelOpen, setLeftPanelOpen] = useState(initialWorkbenchLayout.leftPanelOpen)
  const [rightPanelOpen, setRightPanelOpen] = useState(initialWorkbenchLayout.rightPanelOpen)
  const [bottomDockOpen, setBottomDockOpen] = useState(initialWorkbenchLayout.bottomDockOpen)
  const [activeDockTab, setActiveDockTab] = useState<DockTabKey>(initialWorkbenchLayout.activeDockTab)
  const [assistBusyAction, setAssistBusyAction] = useState<AssistActionKey>(null)
  const [assistApplyMode, setAssistApplyMode] = useState<AssistApplyMode>('related-nodes')
  const [assistSessionId, setAssistSessionId] = useState<string | null>(null)
  const [canvasFitToken, setCanvasFitToken] = useState(0)
  const [workspaceVisibilityToken, setWorkspaceVisibilityToken] = useState(0)
  const [savedPromptDrafts, setSavedPromptDrafts] = useState<SavedPromptDraftMap>(() => loadSavedPromptDrafts())
  const [promptDraftByGraph, setPromptDraftByGraph] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(loadSavedPromptDrafts()).map(([key, value]) => [key, value.text])),
  )
  const [promptBaseByGraph, setPromptBaseByGraph] = useState<Record<string, string>>({})
  const [generationMode, setGenerationMode] = useState<ScriptGenerationMode>('lite')

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null
  const canonicalGraph = useMemo(() => toCanonicalGraph(nodes, edges), [
    nodes.map((n) => `${n.id}-${n.type}`).join('|'),
    JSON.stringify(nodes.map((n) => n.data)),
    edges,
  ])
  const graphKey = useMemo(() => buildWorkflowGraphKey(canonicalGraph), [canonicalGraph])
  const workflowStats = useMemo(() => {
    const explicitMaxItems = nodes.flatMap((node) => {
      if (
        node.type === 'open_page' ||
        node.type === 'select_list' ||
        node.type === 'loop' ||
        node.type === 'extract_field'
      ) {
        const limit = toPositiveLimit(node.data.max_items)
        return limit === null ? [] : [limit]
      }
      return []
    })
    const explicitMaxPages = nodes.flatMap((node) => {
      if (node.type === 'paginate' || node.type === 'open_page') {
        const limit = toPositiveLimit(node.data.max_pages)
        return limit === null ? [] : [limit]
      }
      return []
    })
    const explicitMaxSteps = nodes.flatMap((node) => {
      if (node.type === 'open_page') {
        const limit = toPositiveLimit(node.data.max_steps)
        return limit === null ? [] : [limit]
      }
      return []
    })

    return {
      nodeCount: nodes.length,
      edgeCount: edges.length,
      fieldCount: nodes.reduce((count, node) => count + (node.type === 'extract_field' ? node.data.fields?.length ?? 0 : 0), 0),
      maxItems: explicitMaxItems.length > 0 ? Math.min(...explicitMaxItems) : null,
      maxPages: explicitMaxPages.length > 0 ? Math.min(...explicitMaxPages) : null,
      maxSteps: explicitMaxSteps.length > 0 ? Math.min(...explicitMaxSteps) : null,
      hasPagination: nodes.some((node) => node.type === 'paginate'),
    }
  }, [edges.length, nodes.map(n => n.type).join('|'), JSON.stringify(nodes.map(n => n.data))])

  const getPromptOverride = useCallback((targetGraphKey: string) => {
    const draft = promptDraftByGraph[targetGraphKey]?.trim() ?? ''
    if (!draft) return ''
    const base = promptBaseByGraph[targetGraphKey]?.trim() ?? ''
    return draft !== base ? draft : ''
  }, [promptBaseByGraph, promptDraftByGraph])

  const { resultState, runningAction, runWorkflowAction } = useWorkflowActions({
    canonicalGraph,
    selectedNodeId,
    graphKey,
    getPromptOverride,
    generationMode,
  })

  const conditionOutgoingEdges = useMemo(() => {
    if (!selectedNode || selectedNode.type !== 'condition') return []
    return edges
      .filter((edge) => edge.source === selectedNode.id)
      .map((edge) => ({
        id: edge.id,
        target: edge.target,
        branch: edge.branch,
        label: typeof edge.label === 'string' ? edge.label : undefined,
        order: edge.order,
      }))
  }, [edges, selectedNode?.id, selectedNode?.type])

  const workflowContext = useMemo(() => ({
    hasOpenPageNode: nodes.some((node) => node.type === 'open_page'),
    hasSelectListNode: nodes.some((node) => node.type === 'select_list'),
    hasTerminalNode: nodes.some((node) => node.type === 'end'),
  }), [nodes.map(n => n.type).join('|')])

  const sourceNodeTypeById = useMemo(
    () => Object.fromEntries(nodes.map((node) => [node.id, node.type])) as Record<string, WorkflowNodeType>,
    [nodes.map(n => `${n.id}-${n.type}`).join('|')],
  )

  useEffect(() => {
    if (pendingSelectionRef.current && nodes.some((node) => node.id === pendingSelectionRef.current)) {
      setSelectedNodeId(pendingSelectionRef.current)
      pendingSelectionRef.current = null
      return
    }
    if (selectedNodeId && !nodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(nodes[0]?.id ?? '')
    }
  }, [nodes, selectedNodeId])

  useEffect(() => {
    if (isApplyingDslRef.current) {
      isApplyingDslRef.current = false
      return
    }

    const timer = setTimeout(() => {
      setDslText(JSON.stringify(canonicalGraph, null, 2))
      setDslStatus('synced')
      setDslFeedback('画布与 DSL 已保持同步。')
    }, 400)

    return () => clearTimeout(timer)
  }, [canonicalGraph])

  useEffect(() => {
    const prompt = extractEditablePrompt(resultState.payload)
    const resultGraphKey = resultState.graphKey
    if (!prompt || !resultGraphKey) return
    setPromptBaseByGraph((current) => (
      current[resultGraphKey] === prompt
        ? current
        : { ...current, [resultGraphKey]: prompt }
    ))
    setPromptDraftByGraph((current) => (
      typeof current[resultGraphKey] === 'string'
        ? current
        : { ...current, [resultGraphKey]: prompt }
    ))
  }, [resultState.graphKey, resultState.payload])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(WORKBENCH_LAYOUT_STORAGE_KEY, JSON.stringify({
        leftPanelOpen,
        rightPanelOpen,
        bottomDockOpen,
        activeDockTab,
      }))
    } catch {
      // ignore storage errors so layout state persistence never breaks the app
    }
  }, [activeDockTab, bottomDockOpen, leftPanelOpen, rightPanelOpen])

  function getEntryUrl() {
    const entry = nodes.find((node) => node.type === 'open_page')
    const url = entry?.data.url
    return typeof url === 'string' ? url.trim() : ''
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
        message.error(msg)
      })
      .finally(() => setAssistBusyAction(null))
  }

  const onNodesChange = useCallback((changes: NodeChange<WorkflowNode>[]) => {
    const removedNodeIds = changes
      .filter((change) => change.type === 'remove')
      .map((change) => change.id)
    if (removedNodeIds.length > 0) {
      setEdges((currentEdges) =>
        currentEdges.filter((edge) => !removedNodeIds.includes(edge.source) && !removedNodeIds.includes(edge.target)),
      )
      setSelectedNodeId((current) => (removedNodeIds.includes(current) ? '' : current))
    }
    setNodes((currentNodes) => applyNodeChanges(changes, currentNodes))
  }, [])

  const onEdgesChange = useCallback((changes: EdgeChange<WorkflowEdge>[]) => {
    setEdges((currentEdges) => applyEdgeChanges(changes, currentEdges))
  }, [])

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return
    setEdges((currentEdges) => {
      const exists = currentEdges.some(
        (edge) => edge.source === connection.source && edge.target === connection.target,
      )
      if (exists) return currentEdges
      const sourceNode = nodes.find((node) => node.id === connection.source)
      const outgoingCount = currentEdges.filter((edge) => edge.source === connection.source).length
      const isConditionSource = sourceNode?.type === 'condition'
      const inferredBranch: CanonicalWorkflowEdge['branch'] | undefined = isConditionSource
        ? (outgoingCount === 0 ? 'true' : outgoingCount === 1 ? 'false' : 'default')
        : undefined
      const inferredLabel = inferredBranch === 'true'
        ? 'TRUE'
        : inferredBranch === 'false'
          ? 'FALSE'
          : inferredBranch === 'default'
            ? 'DEFAULT'
            : undefined
      return addEdge({
        ...connection,
        id: `edge-${connection.source}-${connection.target}-${currentEdges.length + 1}`,
        markerEnd: { type: MarkerType.ArrowClosed },
        branch: inferredBranch,
        order: isConditionSource ? outgoingCount : undefined,
        label: inferredLabel,
      }, currentEdges)
    })
  }, [nodes])

  async function handleDslChange(value: string | undefined) {
    const nextText = value ?? ''
    setDslText(nextText)
    const result = await applyDslTextChange(
      { nodes, edges, selectedNodeId }, nextText, dslValidationRequestIdRef, validateGraphWithBackend,
    )
    if (result.requestId !== dslValidationRequestIdRef.current) return
    if (result.applied) {
      isApplyingDslRef.current = true
      setNodes(result.nodes)
      setEdges(result.edges)
      setSelectedNodeId(result.selectedNodeId)
      setCanvasFitToken((token) => token + 1)
    }
    setDslText(result.dslText)
    setDslStatus(result.dslStatus)
    setDslFeedback(result.dslFeedback)
  }

  function addPaletteNode(type: WorkflowNodeType) {
    let createdNodeId = ''
    setNodes((currentNodes) => {
      createdNodeId = resolveNextNodeId(currentNodes, type)
      return [...currentNodes, {
        id: createdNodeId,
        type,
        position: resolveNextNodePosition(currentNodes, false),
        data: createDefaultData(type),
      }]
    })
    pendingSelectionRef.current = createdNodeId
    message.success(`已添加节点：${createdNodeId}`)
    setRightPanelOpen(true)
    setCanvasFitToken((token) => token + 1)
  }

  function deleteSelectedNode() {
    if (!selectedNodeId) return
    const next = nodes.find((node) => node.id !== selectedNodeId)?.id ?? ''
    setNodes((current) => current.filter((n) => n.id !== selectedNodeId))
    setEdges((current) => current.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId))
    setSelectedNodeId(next)
  }

  function updateSelectedNodeData(patch: Partial<WorkflowNodeData>) {
    setNodes((current) => current.map((node) =>
      node.id === selectedNodeId ? { ...node, data: { ...node.data, ...patch } } : node,
    ))
  }

  function updateSelectedNodeFields(updater: (fields: ExtractionField[]) => ExtractionField[]) {
    setNodes((current) => current.map((node) =>
      node.id === selectedNodeId ? { ...node, data: { ...node.data, fields: updater(node.data.fields ?? []) } } : node,
    ))
  }

  function updateConditionEdge(edgeId: string, patch: Partial<CanonicalWorkflowEdge>) {
    setEdges((current) => current.map((edge) => {
      if (edge.id !== edgeId) return edge
      return {
        ...edge,
        ...patch,
      }
    }))
  }

  function updateExtractField(index: number, patch: Partial<ExtractionField>) {
    updateSelectedNodeFields((fields) => fields.map((f, i) => (i === index ? { ...f, ...patch } : f)))
  }

  function addExtractField() {
    updateSelectedNodeFields((fields) => [...fields, { name: '', selector: '', type: 'text' }])
  }

  function removeExtractField(index: number) {
    updateSelectedNodeFields((fields) => fields.filter((_, i) => i !== index))
  }

  function normalizeAssistError(payload: unknown, responseOk: boolean) {
    if (!responseOk) return getErrorMessage(payload)
    const record = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {}
    if (record.success === false) return getErrorMessage(payload)
    return ''
  }

  function withAssistSession<T extends Record<string, unknown>>(payload: T): T & { session_id?: string } {
    return assistSessionId ? { ...payload, session_id: assistSessionId } : payload
  }

  function syncAssistSession(payload: unknown) {
    if (!payload || typeof payload !== 'object') return
    const record = payload as Record<string, unknown>
    if (typeof record.session_id === 'string' && record.session_id.trim()) {
      setAssistSessionId(record.session_id)
    }
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
      message.success('自动检测结果已回填')
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
      message.success('已应用优化后的列表选择器')
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
      message.success('AI 字段推断已应用')
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
      message.success('分页策略分析结果已应用')
    })
  }

  function handleTestSelector(selector: string, selectorLabel: string) {
    runWithAssistLock('test-selector', async () => {
      const normalizedSelector = selector.trim()
      if (!normalizedSelector) throw new Error(`请先填写${selectorLabel}`)
      const entryUrl = getEntryUrl()
      const extractResult = await postAssistAction('/api/assist/extract-html', withAssistSession({
        item_selector: normalizedSelector,
        url: entryUrl || undefined,
      }))
      const extractError = normalizeAssistError(extractResult.payload, extractResult.response.ok)
      if (extractError) throw new Error(extractError)
      syncAssistSession(extractResult.payload)

      const payload = extractResult.payload as Record<string, unknown>
      const metadata = payload.metadata && typeof payload.metadata === 'object'
        ? payload.metadata as Record<string, unknown>
        : {}
      const itemCount = typeof metadata.item_count === 'number' ? metadata.item_count : 0
      const truncated = metadata.truncated === true
      if (itemCount <= 0) {
        message.warning(`${selectorLabel}测试完成：未匹配到元素，请检查选择器。`)
        return
      }
      const suffix = truncated ? '（片段已裁剪）' : ''
      message.success(`${selectorLabel}测试通过：匹配 ${itemCount} 个元素${suffix}`)
    })
  }

  function handleCleanExtractField(index: number) {
    runWithAssistLock('clean-data', async () => {
      if (!selectedNode || selectedNode.type !== 'extract_field') return
      const field = selectedNode.data.fields?.[index]
      if (!field) throw new Error('字段不存在')
      const rawData = typeof field.sample_value === 'string' ? field.sample_value.trim() : ''
      if (!rawData) throw new Error('请先填写样例原始值')
      const cleanType = typeof field.clean_data_type === 'string' && field.clean_data_type.trim()
        ? field.clean_data_type.trim()
        : inferCleanDataType(field)

      const cleanResult = await postAssistAction('/api/assist/clean-data', withAssistSession({
        raw_data: rawData,
        data_type: cleanType,
      }))
      const cleanError = normalizeAssistError(cleanResult.payload, cleanResult.response.ok)
      if (cleanError) throw new Error(cleanError)

      const payload = cleanResult.payload as Record<string, unknown>
      const result = (payload.result && typeof payload.result === 'object') ? payload.result as Record<string, unknown> : {}
      if (!Object.prototype.hasOwnProperty.call(result, 'cleaned_value')) {
        throw new Error('模型未返回 cleaned_value')
      }
      const cleanedValue = result.cleaned_value
      const normalized = typeof cleanedValue === 'string'
        ? cleanedValue
        : cleanedValue === null || cleanedValue === undefined
          ? ''
          : JSON.stringify(cleanedValue)

      updateExtractField(index, {
        clean_data_type: cleanType,
        normalized_sample: normalized,
      })
      message.success('样例值已清洗并回填')
    })
  }

  function updatePromptDraft(targetGraphKey: string, nextValue: string) {
    setPromptDraftByGraph((current) => ({ ...current, [targetGraphKey]: nextValue }))
  }

  function savePromptDraft(targetGraphKey: string) {
    const text = promptDraftByGraph[targetGraphKey] ?? promptBaseByGraph[targetGraphKey] ?? ''
    if (!text.trim()) {
      message.warning('当前没有可保存的提示词内容')
      return
    }
    const nextDrafts: SavedPromptDraftMap = {
      ...savedPromptDrafts,
      [targetGraphKey]: {
        text,
        savedAt: Date.now(),
      },
    }
    setSavedPromptDrafts(nextDrafts)
    persistSavedPromptDrafts(nextDrafts)
    message.success('提示词草稿已保存，可直接用于后续脚本生成')
  }

  function resetPromptDraft(targetGraphKey: string) {
    const basePrompt = promptBaseByGraph[targetGraphKey] ?? ''
    setPromptDraftByGraph((current) => ({ ...current, [targetGraphKey]: basePrompt }))
    if (savedPromptDrafts[targetGraphKey]) {
      const nextDrafts = { ...savedPromptDrafts }
      delete nextDrafts[targetGraphKey]
      setSavedPromptDrafts(nextDrafts)
      persistSavedPromptDrafts(nextDrafts)
    }
    message.success('已恢复为系统生成的提示词')
  }

  const promptWorkspace = useMemo(() => {
    const resultGraphKey = resultState.graphKey
    if (!resultGraphKey) return null
    const basePrompt = promptBaseByGraph[resultGraphKey] ?? extractEditablePrompt(resultState.payload)
    if (!basePrompt) return null
    const draft = promptDraftByGraph[resultGraphKey] ?? basePrompt
    const savedMeta = savedPromptDrafts[resultGraphKey]
    return {
      graphKey: resultGraphKey,
      value: draft,
      baseValue: basePrompt,
      savedAt: savedMeta?.savedAt,
      hasSavedDraft: Boolean(savedMeta?.text),
      isDirty: draft !== basePrompt,
      onChange: (nextValue: string) => updatePromptDraft(resultGraphKey, nextValue),
      onSave: () => savePromptDraft(resultGraphKey),
      onReset: () => resetPromptDraft(resultGraphKey),
    }
  }, [promptBaseByGraph, promptDraftByGraph, resultState.graphKey, resultState.payload, savedPromptDrafts])

  function handleRunWorkflowAction(action: WorkbenchAction) {
    if (action === 'auto-layout') {
      const nextNodes = autoLayoutNodes(nodes, edges)
      setNodes(nextNodes)
      setCanvasFitToken((t) => t + 1)
      message.success('布局已优化')
      return
    }
    setBottomDockOpen(true)
    setActiveDockTab('results')
    void runWorkflowAction(action)
  }

  function openDockTab(tab: DockTabKey) {
    setBottomDockOpen(true)
    setActiveDockTab(tab)
  }

  const workspaceShellClassName = [
    'workspace-shell',
    leftPanelOpen ? 'workspace-shell--left-open' : 'workspace-shell--left-closed',
    rightPanelOpen ? 'workspace-shell--right-open' : 'workspace-shell--right-closed',
  ].join(' ')
  const activeWorkspaceLabel = activeDockTab === 'dsl' ? 'DSL 编辑器' : '执行结果'

  return (
    <div className="console-root">
      <div className="console-toolbar">
        <WorkbenchToolbar
          runningAction={runningAction}
          selectedNodeId={selectedNodeId}
          workflowStats={workflowStats}
          onRunAction={handleRunWorkflowAction}
          generationMode={generationMode}
          onGenerationModeChange={setGenerationMode}
          layout={{
            leftPanelOpen,
            rightPanelOpen,
            bottomDockOpen,
            activeDockTab,
            setLeftPanelOpen,
            setRightPanelOpen,
            openDockTab,
          }}
        />
      </div>

      <div className={workspaceShellClassName}>
        {leftPanelOpen && (
          <aside className="workbench-panel layout-panel-left">
            <div className="workbench-panel-header">
              <div className="console-panel-title">
                <LayoutOutlined />
                <span>节点面板</span>
              </div>
              <Tag color="blue" style={{ margin: 0, border: 'none', boxShadow: 'var(--sd-shadow-border-light)' }}>{paletteItems.length} 种</Tag>
            </div>
            <NodePalette items={paletteItems} onAddNode={addPaletteNode} />
          </aside>
        )}

        <div className="workspace-center">
          <div className="canvas-stage">
            <WorkflowCanvas
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={(_, node) => {
                setSelectedNodeId(node.id)
                setRightPanelOpen(true)
              }}
              onPaneClick={() => { }}
              sourceNodeTypeById={sourceNodeTypeById}
              fitViewToken={canvasFitToken}
            />
          </div>
          <button className="bottom-dock-collapsed" type="button" onClick={() => openDockTab('results')}>
            打开结果与 DSL 工作区
          </button>
        </div>

        {rightPanelOpen && (
          <aside className="workbench-panel layout-panel-right">
            <div className="workbench-panel-header">
              <div className="console-panel-title">
                <AppstoreOutlined />
                <span>{selectedNode ? `配置 - ${selectedNode.id}` : '属性面板'}</span>
              </div>
              <Button size="small" onClick={() => setRightPanelOpen(false)}>收起</Button>
            </div>
            <PropertyPanel
              selectedNode={selectedNode}
              conditionOutgoingEdges={conditionOutgoingEdges}
              workflowContext={workflowContext}
              clampNumberInput={clampNumberInput}
              updateSelectedNodeData={updateSelectedNodeData}
              updateExtractField={updateExtractField}
              updateConditionEdge={updateConditionEdge}
              assistApplyMode={assistApplyMode}
              setAssistApplyMode={setAssistApplyMode}
              onAutoDetectSelectList={handleAutoDetectSelectList}
              onOptimizeListSelector={handleOptimizeListSelector}
              onInferExtractFields={handleInferExtractFields}
              onAnalyzePagination={handleAnalyzePagination}
              onCleanExtractField={handleCleanExtractField}
              onTestSelector={handleTestSelector}
              assistBusyAction={assistBusyAction}
              addExtractField={addExtractField}
              removeExtractField={removeExtractField}
              onDeleteNode={deleteSelectedNode}
            />
          </aside>
        )}
      </div>

      <Drawer
        placement="bottom"
        open={bottomDockOpen}
        mask={false}
        keyboard
        forceRender
        height="84vh"
        title={(
          <div className="workspace-drawer-title">
            <Typography.Text strong>结果与 DSL 工作区</Typography.Text>
            <Typography.Text type="secondary" className="workspace-drawer-subtitle">
              聚合复杂输出、日志与 DSL 编辑内容
            </Typography.Text>
          </div>
        )}
        extra={(
          <div className="workspace-drawer-extra">
            <Tag className="workspace-drawer-extra-tag">{activeWorkspaceLabel}</Tag>
            <Tag className="workspace-drawer-extra-tag">{selectedNodeId || '未选择节点'}</Tag>
          </div>
        )}
        onClose={() => setBottomDockOpen(false)}
        afterOpenChange={(open) => {
          if (open) setWorkspaceVisibilityToken((current) => current + 1)
        }}
        rootClassName="workspace-drawer"
        styles={{
          body: { padding: 0, display: 'flex', minHeight: 0 },
          header: { padding: '14px 18px', borderBottom: '1px solid rgba(148, 163, 184, 0.14)' },
          content: { overflow: 'hidden' },
        }}
      >
        <Tabs
          activeKey={activeDockTab}
          onChange={(key) => {
            setActiveDockTab(key as DockTabKey)
            setWorkspaceVisibilityToken((current) => current + 1)
          }}
          className="workspace-drawer-tabs"
          destroyInactiveTabPane={false}
          animated={false}
          items={[
            {
              key: 'results',
              label: (
                <span className="workspace-drawer-tab-label">
                  <BarsOutlined />
                  <span>执行结果</span>
                </span>
              ),
              children: (
                <div className="workspace-drawer-pane">
                  <ResultsPanel
                    resultState={resultState}
                    runningAction={runningAction}
                    promptWorkspace={promptWorkspace}
                    selectedNodeId={selectedNodeId}
                    visibilityToken={activeDockTab === 'results' ? workspaceVisibilityToken : undefined}
                  />
                </div>
              ),
            },
            {
              key: 'dsl',
              label: (
                <span className="workspace-drawer-tab-label">
                  <SaveOutlined />
                  <span>DSL 编辑器</span>
                </span>
              ),
              children: (
                <div className="workspace-drawer-pane">
                  <DslEditorPanel
                    dslStatus={dslStatus}
                    dslFeedback={dslFeedback}
                    dslText={dslText}
                    onChange={handleDslChange}
                    showHeader={false}
                    contextSummary={{
                      selectedNodeId,
                      nodeCount: workflowStats.nodeCount,
                      edgeCount: workflowStats.edgeCount,
                      fieldCount: workflowStats.fieldCount,
                    }}
                    visibilityToken={activeDockTab === 'dsl' ? workspaceVisibilityToken : undefined}
                  />
                </div>
              ),
            },
          ]}
        />
      </Drawer>
    </div>
  )
}
