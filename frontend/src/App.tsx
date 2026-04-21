import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Editor, { loader } from '@monaco-editor/react'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import './App.css'
import {
  applyDslTextChange,
  getErrorMessage,
  toCanonicalGraph,
  type DslStatus,
  type ExtractionField,
  type WorkflowEdge,
  type WorkflowGraph,
  type WorkflowNode,
  type WorkflowNodeData,
  type WorkflowNodeType,
} from './workflowState'
loader.config({ paths: { vs: '/monaco-editor/min/vs' } })

type BackendStatus = 'checking' | 'online' | 'offline'
type ResultTone = 'idle' | 'success' | 'error'
type PaletteItem = {
  type: WorkflowNodeType
  label: string
  detail: string
}

const fallbackUrl = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : window.location.origin

function clampNumberInput(value: string, min: number, max: number, fallback: number) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(Math.max(parsed, min), max)
}

const paletteItems: PaletteItem[] = [
  { type: 'open_page', label: 'open_page', detail: 'Set target URL' },
  { type: 'select_list', label: 'select_list', detail: 'Choose item selector' },
  { type: 'loop', label: 'loop', detail: 'Bound list iteration' },
  { type: 'extract_field', label: 'extract_field', detail: 'Legacy fields array' },
  { type: 'condition', label: 'condition', detail: 'Branch by expression' },
  { type: 'paginate', label: 'paginate', detail: 'Legacy pagination' },
  { type: 'emit_record', label: 'emit_record', detail: 'Output record' },
  { type: 'end', label: 'end', detail: 'Stop workflow' },
]

const nodeTypeLabels: Record<WorkflowNodeType, string> = {
  open_page: 'Open Page',
  select_list: 'Select List',
  loop: 'Loop',
  extract_field: 'Extract Field',
  condition: 'Condition',
  paginate: 'Paginate',
  emit_record: 'Emit Record',
  end: 'End',
}

const initialNodes: WorkflowNode[] = [
  {
    id: 'open-page-1',
    type: 'open_page',
    position: { x: 60, y: 140 },
    data: { label: 'Open Page', url: 'https://quotes.toscrape.com/', max_pages: 2, max_steps: 20 },
  },
  {
    id: 'select-list-1',
    type: 'select_list',
    position: { x: 330, y: 140 },
    data: { label: 'Select List', item_selector: '.quote', max_items: 5 },
  },
  {
    id: 'extract-field-1',
    type: 'extract_field',
    position: { x: 600, y: 140 },
    data: { label: 'Extract Field', fields: [{ name: 'text', selector: '.text', type: 'text' }] },
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

function createDefaultData(type: WorkflowNodeType): WorkflowNodeData {
  switch (type) {
    case 'open_page':
      return { label: 'Open Page', url: '', max_pages: 2, max_steps: 20 }
    case 'select_list':
      return { label: 'Select List', item_selector: '', max_items: 5 }
    case 'loop':
      return { label: 'Loop', max_items: 5 }
    case 'extract_field':
      return { label: 'Extract Field', fields: [{ name: 'title', selector: '', type: 'text' }] }
    case 'condition':
      return { label: 'Condition', condition: '' }
    case 'paginate':
      return { label: 'Paginate', pagination_selector: '', pagination_strategy: 'click_next', max_pages: 2 }
    case 'emit_record':
      return { label: 'Emit Record' }
    case 'end':
      return { label: 'End' }
  }
}

function nodeSummary(type: WorkflowNodeType, data: WorkflowNodeData) {
  if (type === 'open_page') return String(data.url || 'Set target URL')
  if (type === 'select_list') return String(data.item_selector || 'Set item selector')
  if (type === 'extract_field') return `${data.fields?.length ?? 0} legacy field(s)`
  if (type === 'paginate') return `${data.pagination_strategy || 'click_next'} ${data.max_pages ?? 1} page(s)`
  if (type === 'loop') return `${data.max_items ?? 5} max item(s)`
  if (type === 'condition') return String(data.condition || 'Set condition')
  return 'Ready'
}

function WorkflowCanvasNode({ data, type, selected }: NodeProps<WorkflowNode>) {
  const workflowType = type as WorkflowNodeType

  return (
    <div className={`canvas-node-card ${selected ? 'selected' : ''}`}>
      <Handle type="target" position={Position.Left} />
      <span className="node-type">{workflowType}</span>
      <strong>{String(data.label || nodeTypeLabels[workflowType])}</strong>
      <small>{nodeSummary(workflowType, data)}</small>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const reactFlowNodeTypes = {
  open_page: WorkflowCanvasNode,
  select_list: WorkflowCanvasNode,
  loop: WorkflowCanvasNode,
  extract_field: WorkflowCanvasNode,
  condition: WorkflowCanvasNode,
  paginate: WorkflowCanvasNode,
  emit_record: WorkflowCanvasNode,
  end: WorkflowCanvasNode,
}

function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('checking')
  const [backendMessage, setBackendMessage] = useState('Checking legacy backend at localhost:8000...')
  const [resultTone, setResultTone] = useState<ResultTone>('idle')
  const [resultMessage, setResultMessage] = useState(
    'Select an action from the toolbar to show validation, prompt preview, node test, or subflow output here.',
  )
  const [nodes, setNodes] = useState<WorkflowNode[]>(initialNodes)
  const [edges, setEdges] = useState<WorkflowEdge[]>(initialEdges)
  const [selectedNodeId, setSelectedNodeId] = useState(initialNodes[0].id)
  const [dslText, setDslText] = useState(() => JSON.stringify(toCanonicalGraph(initialNodes, initialEdges), null, 2))
  const [dslStatus, setDslStatus] = useState<DslStatus>('synced')
  const [dslFeedback, setDslFeedback] = useState('Canvas and DSL are synchronized.')
  const isApplyingDslRef = useRef(false)
  const dslValidationRequestIdRef = useRef(0)

  useEffect(() => {
    const controller = new AbortController()

    fetch('/legacy-health', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Backend returned HTTP ${response.status}`)
        }
        setBackendStatus('online')
        setBackendMessage('Legacy fallback backend is reachable on port 8000.')
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }
        setBackendStatus('offline')
        setBackendMessage(
          'Legacy backend is not reachable. The workbench stays available, and the fallback link remains visible.',
        )
      })

    return () => controller.abort()
  }, [])

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null
  const canonicalGraph = useMemo(() => toCanonicalGraph(nodes, edges), [nodes, edges])

  useEffect(() => {
    if (isApplyingDslRef.current) {
      isApplyingDslRef.current = false
      return
    }
    queueMicrotask(() => {
      setDslText(JSON.stringify(canonicalGraph, null, 2))
      setDslStatus('synced')
      setDslFeedback('Canvas and DSL are synchronized.')
    })
  }, [canonicalGraph])

  const onNodesChange = useCallback((changes: NodeChange<WorkflowNode>[]) => {
    setNodes((currentNodes) => applyNodeChanges(changes, currentNodes))
  }, [])

  const onEdgesChange = useCallback((changes: EdgeChange<WorkflowEdge>[]) => {
    setEdges((currentEdges) => applyEdgeChanges(changes, currentEdges))
  }, [])

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return

    setEdges((currentEdges) => {
      const edgeExists = currentEdges.some(
        (edge) => edge.source === connection.source && edge.target === connection.target,
      )
      if (edgeExists) return currentEdges

      return addEdge(
        {
          ...connection,
          id: `edge-${connection.source}-${connection.target}-${currentEdges.length + 1}`,
          markerEnd: { type: MarkerType.ArrowClosed },
        },
        currentEdges,
      )
    })
  }, [])

  async function validateGraphWithBackend(graph: WorkflowGraph) {
    const response = await fetch('/api/workflows/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ graph }),
    })
    const payload: unknown = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(getErrorMessage(payload))
    }
  }

  async function handleDslChange(value: string | undefined) {
    const nextText = value ?? ''
    setDslText(nextText)

    const result = await applyDslTextChange(
      { nodes, edges, selectedNodeId },
      nextText,
      dslValidationRequestIdRef,
      validateGraphWithBackend,
    )

    if (result.requestId !== dslValidationRequestIdRef.current) return

    if (result.applied) {
      isApplyingDslRef.current = true
      setNodes(result.nodes)
      setEdges(result.edges)
      setSelectedNodeId(result.selectedNodeId)
    }

    setDslText(result.dslText)
    setDslStatus(result.dslStatus)
    setDslFeedback(result.dslFeedback)
  }
  function showShellResult(action: string) {
    if (backendStatus === 'offline') {
      setResultTone('error')
      setResultMessage(`${action} cannot reach the backend. Keep authoring locally or open the legacy UI directly.`)
      return
    }

    setResultTone('success')
    setResultMessage(`${action} is available in the shell. Backend integration is handled by the next React milestone.`)
  }

  function addPaletteNode(type: WorkflowNodeType) {
    const existingSuffixes = nodes
      .filter((node) => node.type === type)
      .map((node) => Number(node.id.split('-').at(-1)))
      .filter(Number.isFinite)
    const nextCount = Math.max(0, ...existingSuffixes) + 1
    const newNode: WorkflowNode = {
      id: `${type.replaceAll('_', '-')}-${nextCount}`,
      type,
      position: { x: 120 + (nodes.length % 4) * 210, y: 80 + Math.floor(nodes.length / 4) * 150 },
      data: createDefaultData(type),
    }

    setNodes((currentNodes) => [...currentNodes, newNode])
    setSelectedNodeId(newNode.id)
  }

  function updateSelectedNodeData(patch: Partial<WorkflowNodeData>) {
    setNodes((currentNodes) =>
      currentNodes.map((node) => {
        if (node.id !== selectedNodeId) return node
        return { ...node, data: { ...node.data, ...patch } }
      }),
    )
  }

  function updateSelectedNodeFields(updater: (fields: ExtractionField[]) => ExtractionField[]) {
    setNodes((currentNodes) =>
      currentNodes.map((node) => {
        if (node.id !== selectedNodeId) return node
        return { ...node, data: { ...node.data, fields: updater(node.data.fields ?? []) } }
      }),
    )
  }

  function updateExtractField(index: number, patch: Partial<ExtractionField>) {
    updateSelectedNodeFields((fields) =>
      fields.map((field, fieldIndex) => (fieldIndex === index ? { ...field, ...patch } : field)),
    )
  }

  function addExtractField() {
    updateSelectedNodeFields((fields) => [...fields, { name: '', selector: '', type: 'text' }])
  }

  function removeExtractField(index: number) {
    updateSelectedNodeFields((fields) => fields.filter((_, fieldIndex) => fieldIndex !== index))
  }

  return (
    <main className="workbench-shell" aria-label="Sea Data React Workbench">
      <header className="toolbar" aria-label="Workbench toolbar">
        <div>
          <span className="eyebrow">Sea Data Workbench</span>
          <h1>Workflow Designer</h1>
        </div>
        <nav className="toolbar-actions" aria-label="Workbench actions">
          <button type="button" onClick={() => showShellResult('Validate DSL')}>
            Validate DSL
          </button>
          <button type="button" onClick={() => showShellResult('Preview Prompt')}>
            Preview Prompt
          </button>
          <button type="button" onClick={() => showShellResult('Run Node Test')}>
            Run Node Test
          </button>
          <span className="bounds-pill">max_items 5 / max_pages 2 / max_steps 20</span>
          <a className="fallback-link" href={fallbackUrl} target="_blank" rel="noreferrer">
            Open legacy UI
          </a>
        </nav>
      </header>

      <section className={`backend-banner ${backendStatus}`} aria-live="polite">
        <strong>Backend status:</strong> {backendMessage}
      </section>

      <div className="workspace-grid">
        <aside className="panel node-palette" aria-label="Node palette">
          <div className="panel-heading">
            <span>Node Palette</span>
            <small>MVP workflow nodes</small>
          </div>
          <div className="palette-list">
            {paletteItems.map((item) => (
              <button key={item.type} type="button" className="palette-card" onClick={() => addPaletteNode(item.type)}>
                <span>{item.label}</span>
                <small>{item.detail}</small>
              </button>
            ))}
          </div>
          <p className="scope-note">
            Detail-page scraping and complex nested loops are intentionally not required for this MVP workbench.
          </p>
        </aside>

        <section className="panel canvas-region" aria-label="Workflow canvas region">
          <div className="panel-heading">
            <span>Canvas</span>
            <small>Add, drag, select, and connect nodes</small>
          </div>
          <div className="canvas-surface">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={reactFlowNodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={(_, node) => setSelectedNodeId(node.id)}
              onPaneClick={() => setSelectedNodeId('')}
              fitView
            >
              <Background />
              <MiniMap pannable zoomable />
              <Controls />
            </ReactFlow>
          </div>
        </section>

        <aside className="panel properties-panel" aria-label="Property panel">
          <div className="panel-heading">
            <span>Property Panel</span>
            <small>{selectedNode ? selectedNode.id : 'No node selected'}</small>
          </div>

          {selectedNode ? (
            <div className="property-form">
              <label>
                Node type
                <input value={selectedNode.type} readOnly />
              </label>
              <label>
                Label
                <input
                  value={String(selectedNode.data.label ?? '')}
                  onChange={(event) => updateSelectedNodeData({ label: event.target.value })}
                />
              </label>

              {selectedNode.type === 'open_page' && (
                <>
                  <label>
                    Target URL
                    <input
                      aria-label="Target URL"
                      value={String(selectedNode.data.url ?? '')}
                      onChange={(event) => updateSelectedNodeData({ url: event.target.value })}
                    />
                  </label>
                  <label>
                    Max pages
                    <input
                      type="number"
                      min="1"
                      max="5"
                      value={Number(selectedNode.data.max_pages ?? 2)}
                      onChange={(event) =>
                        updateSelectedNodeData({
                          max_pages: clampNumberInput(event.target.value, 1, 5, Number(selectedNode.data.max_pages ?? 2)),
                        })
                      }
                    />
                  </label>
                  <label>
                    Max steps
                    <input
                      type="number"
                      min="1"
                      max="50"
                      value={Number(selectedNode.data.max_steps ?? 20)}
                      onChange={(event) =>
                        updateSelectedNodeData({
                          max_steps: clampNumberInput(event.target.value, 1, 50, Number(selectedNode.data.max_steps ?? 20)),
                        })
                      }
                    />
                  </label>
                </>
              )}

              {selectedNode.type === 'select_list' && (
                <>
                  <label>
                    Item selector
                    <input
                      aria-label="Item selector"
                      value={String(selectedNode.data.item_selector ?? '')}
                      onChange={(event) => updateSelectedNodeData({ item_selector: event.target.value })}
                    />
                  </label>
                  <label>
                    Max items
                    <input
                      type="number"
                      min="1"
                      max="20"
                      value={Number(selectedNode.data.max_items ?? 5)}
                      onChange={(event) =>
                        updateSelectedNodeData({
                          max_items: clampNumberInput(event.target.value, 1, 20, Number(selectedNode.data.max_items ?? 5)),
                        })
                      }
                    />
                  </label>
                </>
              )}

              {selectedNode.type === 'extract_field' && (
                <div className="field-editor">
                  <div className="field-editor-heading">
                    <strong>Legacy fields</strong>
                    <button type="button" onClick={addExtractField}>
                      Add field
                    </button>
                  </div>
                  {(selectedNode.data.fields ?? []).map((field, index) => (
                    <div className="field-row" key={`${selectedNode.id}-field-${index}`}>
                      <input
                        aria-label={`Field ${index + 1} name`}
                        placeholder="name"
                        value={field.name}
                        onChange={(event) => updateExtractField(index, { name: event.target.value })}
                      />
                      <input
                        aria-label={`Field ${index + 1} selector`}
                        placeholder="selector"
                        value={field.selector}
                        onChange={(event) => updateExtractField(index, { selector: event.target.value })}
                      />
                      <select
                        aria-label={`Field ${index + 1} type`}
                        value={field.type}
                        onChange={(event) => updateExtractField(index, { type: event.target.value })}
                      >
                        <option value="text">text</option>
                        <option value="attr:href">attr:href</option>
                        <option value="attr:src">attr:src</option>
                        <option value="attr:href:abs">attr:href:abs</option>
                        <option value="html">html</option>
                        <option value="all(text)">all(text)</option>
                        <option value="all(@href)">all(@href)</option>
                      </select>
                      <button type="button" onClick={() => removeExtractField(index)}>
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {selectedNode.type === 'paginate' && (
                <>
                  <label>
                    Pagination selector
                    <input
                      aria-label="Pagination selector"
                      value={String(selectedNode.data.pagination_selector ?? '')}
                      onChange={(event) => updateSelectedNodeData({ pagination_selector: event.target.value })}
                    />
                  </label>
                  <label>
                    Pagination strategy
                    <select
                      value={String(selectedNode.data.pagination_strategy ?? 'click_next')}
                      onChange={(event) => updateSelectedNodeData({ pagination_strategy: event.target.value })}
                    >
                      <option value="click_next">click_next</option>
                      <option value="infinite_scroll">infinite_scroll</option>
                      <option value="load_more">load_more</option>
                      <option value="none">none</option>
                    </select>
                  </label>
                  <label>
                    Max pages
                    <input
                      type="number"
                      min="1"
                      max="5"
                      value={Number(selectedNode.data.max_pages ?? 2)}
                      onChange={(event) =>
                        updateSelectedNodeData({
                          max_pages: clampNumberInput(event.target.value, 1, 5, Number(selectedNode.data.max_pages ?? 2)),
                        })
                      }
                    />
                  </label>
                </>
              )}

              {selectedNode.type === 'loop' && (
                <label>
                  Max items
                  <input
                    type="number"
                    min="1"
                    max="20"
                    value={Number(selectedNode.data.max_items ?? 5)}
                    onChange={(event) => updateSelectedNodeData({ max_items: Number(event.target.value) })}
                  />
                </label>
              )}

              {selectedNode.type === 'condition' && (
                <label>
                  Condition
                  <input
                    value={String(selectedNode.data.condition ?? '')}
                    onChange={(event) => updateSelectedNodeData({ condition: event.target.value })}
                  />
                </label>
              )}
            </div>
          ) : (
            <p className="empty-selection">Select a canvas node to edit canonical node data.</p>
          )}
        </aside>

        <section className="panel dsl-editor" aria-label="DSL editor region">
          <div className="panel-heading">
            <span>DSL Editor</span>
            <small>{dslStatus === 'synced' ? 'Canonical graph JSON' : 'Last valid graph preserved'}</small>
          </div>
          <div className={`dsl-feedback ${dslStatus}`} aria-live="polite">
            {dslFeedback}
          </div>
          <div className="monaco-shell">
            <Editor
              height="260px"
              language="json"
              theme="vs-dark"
              value={dslText}
              options={{ automaticLayout: true, minimap: { enabled: false }, tabSize: 2 }}
              onChange={handleDslChange}
            />
          </div>
        </section>

        <section className="panel results-area" aria-label="Bottom result area">
          <div className="panel-heading">
            <span>Results</span>
            <small>Validation and execution feedback</small>
          </div>
          <div className={`result-placeholder ${resultTone}`} aria-live="polite">
            {resultMessage}
          </div>
        </section>
      </div>
    </main>
  )
}

export default App






