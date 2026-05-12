import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { loader } from '@monaco-editor/react'
import { App as AntdApp, Button, Drawer, Tabs, Tag, Typography, Result } from 'antd'
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
  toCanonicalGraph,
  type DslStatus,
  type WorkflowEdge,
  type WorkflowNode,
} from '../features/workflow/workflowState'
import type { CanonicalWorkflowEdge, ExtractionField, ScriptGenerationMode, WorkflowNodeData, WorkflowNodeType } from '../features/workflow/workflowContracts'
import { DslEditorPanel } from '../features/workflow/components/DslEditorPanel'
import { NodePalette } from '../features/workflow/components/NodePalette'
import { PropertyPanel } from '../features/workflow/components/PropertyPanel'
import { ResultsPanel } from '../features/results/ResultsPanel'
import { WorkbenchToolbar, type WorkbenchAction } from './components/WorkbenchToolbar'
import { WorkflowCanvas } from '../features/workflow/components/WorkflowCanvas'
import { usePromptWorkspace } from '../features/prompt-workspace/usePromptWorkspace'
import { useAssistWorkbenchActions } from '../features/assist/useAssistWorkbenchActions'
import { useWorkbenchLayout } from './useWorkbenchLayout'
import { useWorkflowActions } from '../features/workflow/useWorkflowActions'
import { detectExtension, type ExtensionStatus } from '../features/runtime/extensionBridge'
import {
  buildWorkflowGraphKey,
} from '../features/prompt-workspace/promptDrafts'
import { validateGraphWithBackend } from '../services/workflowApi'
import {
  clampNumberInput,
  createDefaultData,
  initialEdges,
  initialNodes,
  paletteItems,
  type DockTabKey,
} from '../features/workflow/workbenchDefaults'
import { resolveNextNodeId, resolveNextNodePosition, autoLayoutNodes } from '../features/workflow/workflowNodePlacement'
import { useTaskContext, useWorkflowAsset } from './useTaskContext'
import { saveTaskAssets } from '../services/taskApi'

loader.config({ paths: { vs: '/monaco-editor/min/vs' } })

export default function WorkbenchPage() {
  const { message } = AntdApp.useApp()
  const { taskId, taskName, goBack, errorKind } = useTaskContext()
  const { loadAsset } = useWorkflowAsset()
  const [nodes, setNodes] = useState<WorkflowNode[]>(initialNodes)
  const [edges, setEdges] = useState<WorkflowEdge[]>(initialEdges)
  const [selectedNodeId, setSelectedNodeId] = useState(initialNodes[0].id)
  const [dslText, setDslText] = useState(() => JSON.stringify(toCanonicalGraph(initialNodes, initialEdges), null, 2))
  const [dslStatus, setDslStatus] = useState<DslStatus>('synced')
  const [dslFeedback, setDslFeedback] = useState('画布与 DSL 已保持同步。')
  const isApplyingDslRef = useRef(false)
  const dslValidationRequestIdRef = useRef(0)
  const pendingSelectionRef = useRef<string | null>(null)

  const [canvasFitToken, setCanvasFitToken] = useState(0)
  const [generationMode, setGenerationMode] = useState<ScriptGenerationMode>('lite')

  // Load workflow_graph asset from task on mount
  useEffect(() => {
    if (!taskId) return
    let cancelled = false
    loadAsset(taskId).then((result) => {
      if (cancelled) return
      setCanvasFitToken((t) => t + 1)
      if (!result) return
      setNodes(result.nodes)
      setEdges(result.edges)
      setSelectedNodeId(result.nodes[0]?.id ?? '')
      setDslText(JSON.stringify(toCanonicalGraph(result.nodes, result.edges), null, 2))
    })
    return () => {
      cancelled = true
    }
  }, [taskId, loadAsset])

  const [extensionStatus, setExtensionStatus] = useState<ExtensionStatus | null>(null)
  useEffect(() => {
    let cancelled = false
    async function poll() {
      const status = await detectExtension()
      if (!cancelled) {
        setExtensionStatus(status)
      }
    }
    poll()
    const interval = setInterval(poll, 5000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])
  const {
    leftPanelOpen,
    rightPanelOpen,
    bottomDockOpen,
    activeDockTab,
    workspaceVisibilityToken,
    setLeftPanelOpen,
    setRightPanelOpen,
    openDockTab,
    openResultsDock,
    closeBottomDock,
    selectDockTab,
    handleDockOpenChange,
  } = useWorkbenchLayout()
  const {
    getPromptOverride,
    syncPromptFromResult,
    buildPromptWorkspace,
  } = usePromptWorkspace({
    onSaveSuccess: () => message.success('提示词草稿已保存，可直接用于后续脚本生成'),
    onResetSuccess: () => message.success('已恢复为系统生成的提示词'),
    onEmptySave: () => message.warning('当前没有可保存的提示词内容'),
  })

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null
  const {
    assistBusyAction,
    assistApplyMode,
    setAssistApplyMode,
    handleAutoDetectSelectList,
    handleOptimizeListSelector,
    handleInferExtractFields,
    handleAnalyzePagination,
    handleTestSelector,
  } = useAssistWorkbenchActions({
    nodes,
    selectedNode,
    setNodes,
    updateSelectedNodeData,
    notify: message,
  })
  const canonicalGraph = useMemo(() => toCanonicalGraph(nodes, edges), [nodes, edges])
  const graphKey = useMemo(() => buildWorkflowGraphKey(canonicalGraph), [canonicalGraph])
  const workflowStats = useMemo(() => {
    return {
      nodeCount: nodes.length,
      edgeCount: edges.length,
      fieldCount: nodes.reduce((count, node) => count + (node.type === 'extract_field' ? node.data.fields?.length ?? 0 : 0), 0),
      hasPagination: nodes.some((node) => node.type === 'paginate'),
    }
  }, [nodes, edges])

  const { resultState, runningAction, runWorkflowAction } = useWorkflowActions({
    canonicalGraph,
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
  }, [edges, selectedNode])

  const workflowContext = useMemo(() => ({
    hasOpenPageNode: nodes.some((node) => node.type === 'open_page'),
    hasSelectListNode: nodes.some((node) => node.type === 'select_list'),
    hasTerminalNode: nodes.some((node) => node.type === 'end'),
  }), [nodes])

  const sourceNodeTypeById = useMemo(
    () => Object.fromEntries(nodes.map((node) => [node.id, node.type])) as Record<string, WorkflowNodeType>,
    [nodes],
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
    syncPromptFromResult(resultState.graphKey, resultState.payload)
  }, [resultState.graphKey, resultState.payload, syncPromptFromResult])

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

  const promptWorkspace = useMemo(
    () => buildPromptWorkspace(resultState.graphKey, resultState.payload),
    [buildPromptWorkspace, resultState.graphKey, resultState.payload],
  )

  function handleRunWorkflowAction(action: WorkbenchAction) {
    if (action === 'auto-layout') {
      const nextNodes = autoLayoutNodes(nodes, edges)
      setNodes(nextNodes)
      setCanvasFitToken((t) => t + 1)
      message.success('布局已优化')
      return
    }
    openResultsDock()
    void runWorkflowAction(action)
  }

  const [saveToTaskLoading, setSaveToTaskLoading] = useState(false)

  function extractScriptFromPayload(payload: unknown): string {
    if (!payload || typeof payload !== 'object') return ''
    const record = payload as Record<string, unknown>
    return typeof record.script === 'string' ? record.script : ''
  }

  function extractCompilePlanFromPayload(payload: unknown): string {
    if (!payload || typeof payload !== 'object') return ''
    const record = payload as Record<string, unknown>
    if (typeof record.plan === 'object' && record.plan !== null) {
      return JSON.stringify(record.plan)
    }
    return ''
  }

  function extractPromptFromPayload(payload: unknown): string {
    if (!payload || typeof payload !== 'object') return ''
    const record = payload as Record<string, unknown>
    if (typeof record.prompt === 'string') return record.prompt
    if (typeof record.effective_prompt === 'string') return record.effective_prompt
    return ''
  }

  function toDetailBatchRunnerContent(detailBatchRunner: unknown): { config: string; script: string } {
    if (!detailBatchRunner || typeof detailBatchRunner !== 'object') return { config: '', script: '' }
    const record = detailBatchRunner as Record<string, unknown>
    return {
      config: typeof record.config === 'string' ? record.config : '',
      script: typeof record.script === 'string' ? record.script : '',
    }
  }

  async function handleSaveToTask() {
    if (!taskId) return
    setSaveToTaskLoading(true)
    try {
      const payloadRecord = resultState.payload && typeof resultState.payload === 'object'
        ? resultState.payload as Record<string, unknown>
        : {}

      const assets: Record<string, string> = {
        workflow_graph: JSON.stringify(canonicalGraph),
      }

      const scriptContent = extractScriptFromPayload(resultState.payload)
      if (scriptContent) assets.list_script = scriptContent

      const compilePlanContent = extractCompilePlanFromPayload(resultState.payload)
      if (compilePlanContent) assets.compile_plan = compilePlanContent

      const promptContent = extractPromptFromPayload(resultState.payload)
      if (promptContent) assets.prompt = promptContent

      const detailBatchRunner = toDetailBatchRunnerContent(payloadRecord['detail-batch-runner'])
      if (detailBatchRunner.config) assets.detail_batch_config = detailBatchRunner.config
      if (detailBatchRunner.script) assets.detail_batch_script = detailBatchRunner.script

      await saveTaskAssets(taskId, assets)
      message.success('已保存到任务')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaveToTaskLoading(false)
    }
  }

  const workspaceShellClassName = [
    'workspace-shell',
    leftPanelOpen ? 'workspace-shell--left-open' : 'workspace-shell--left-closed',
    rightPanelOpen ? 'workspace-shell--right-open' : 'workspace-shell--right-closed',
  ].join(' ')
  const activeWorkspaceLabel = activeDockTab === 'dsl' ? 'DSL 编辑器' : '执行结果'

  // Handle 404 / not-found for non-owned or non-existent tasks
  if (errorKind === 'not_found') {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '80vh', background: '#f4f5f7' }}>
        <Result
          status="404"
          title="任务不存在"
          subTitle="该任务可能已被删除，或者您没有访问权限。"
          extra={
            <Button type="primary" onClick={goBack} style={{ background: '#000', border: 'none', borderRadius: 8, fontWeight: 600 }}>
              返回任务列表
            </Button>
          }
        />
      </div>
    )
  }

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
          extensionStatus={extensionStatus}
          layout={{
            leftPanelOpen,
            rightPanelOpen,
            bottomDockOpen,
            activeDockTab,
            setLeftPanelOpen,
            setRightPanelOpen,
            openDockTab,
          }}
          taskName={taskName}
          onBack={taskId ? goBack : undefined}
          onSaveToTask={taskId ? handleSaveToTask : undefined}
          saveToTaskLoading={saveToTaskLoading}
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
        size="84vh"
        title={(
          <div className="workspace-drawer-title-simple">
            <Typography.Text strong style={{ fontSize: 15 }}>工作区</Typography.Text>
          </div>
        )}
        extra={(
          <div className="workspace-drawer-extra">
            <Tag color="default" style={{ borderRadius: 6, margin: 0, border: 'none', background: 'rgba(15, 23, 42, 0.05)' }}>
              {activeWorkspaceLabel}
            </Tag>
            <Tag color="blue" style={{ borderRadius: 6, margin: 0, border: 'none', background: 'rgba(37, 99, 235, 0.08)', color: '#2563eb' }}>
              {selectedNodeId ? `节点: ${selectedNodeId}` : '未选择节点'}
            </Tag>
          </div>
        )}
        onClose={closeBottomDock}
        afterOpenChange={handleDockOpenChange}
        rootClassName="workspace-drawer"
        styles={{
          body: { padding: '0 16px 12px', display: 'flex', minHeight: 0 },
          header: { padding: '10px 18px', borderBottom: '1px solid rgba(148, 163, 184, 0.12)' },
          section: { overflow: 'hidden' },
        }}
      >
        <Tabs
          activeKey={activeDockTab}
          onChange={(key) => selectDockTab(key as DockTabKey)}
          className="workspace-drawer-tabs"
          destroyOnHidden={false}
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
