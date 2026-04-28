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
  toCanonicalGraph,
  type DslStatus,
  type WorkflowEdge,
  type WorkflowNode,
} from './workflowState'
import type { CanonicalWorkflowEdge, ExtractionField, ScriptGenerationMode, WorkflowNodeData, WorkflowNodeType } from './workflowContracts'
import { DslEditorPanel } from './components/DslEditorPanel'
import { NodePalette } from './components/NodePalette'
import { PropertyPanel } from './components/PropertyPanel'
import { ResultsPanel } from './components/ResultsPanel'
import { WorkbenchToolbar, type WorkbenchAction } from './components/WorkbenchToolbar'
import { WorkflowCanvas } from './components/WorkflowCanvas'
import { usePromptWorkspace } from './hooks/usePromptWorkspace'
import { useAssistWorkbenchActions } from './hooks/useAssistWorkbenchActions'
import { useWorkbenchLayout } from './hooks/useWorkbenchLayout'
import { useWorkflowActions } from './hooks/useWorkflowActions'
import {
  buildWorkflowGraphKey,
} from './promptDrafts'
import { validateGraphWithBackend } from './services/workflowApi'
import {
  clampNumberInput,
  createDefaultData,
  initialEdges,
  initialNodes,
  paletteItems,
  toPositiveLimit,
  type DockTabKey,
} from './workbenchDefaults'
import { resolveNextNodeId, resolveNextNodePosition, autoLayoutNodes } from './workflowNodePlacement'

loader.config({ paths: { vs: '/monaco-editor/min/vs' } })

export default function App() {
  const { message } = AntdApp.useApp()
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
    handleCleanExtractField,
  } = useAssistWorkbenchActions({
    nodes,
    selectedNode,
    setNodes,
    updateSelectedNodeData,
    updateExtractField,
    notify: message,
  })
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
        onClose={closeBottomDock}
        afterOpenChange={handleDockOpenChange}
        rootClassName="workspace-drawer"
        styles={{
          body: { padding: 0, display: 'flex', minHeight: 0 },
          header: { padding: '14px 18px', borderBottom: '1px solid rgba(148, 163, 184, 0.14)' },
          content: { overflow: 'hidden' },
        }}
      >
        <Tabs
          activeKey={activeDockTab}
          onChange={(key) => selectDockTab(key as DockTabKey)}
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
