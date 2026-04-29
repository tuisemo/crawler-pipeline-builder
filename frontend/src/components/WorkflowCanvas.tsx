import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type ReactFlowInstance,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type NodeProps,
} from '@xyflow/react'
import { Card, Tag, Typography } from 'antd'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import type { WorkflowEdge, WorkflowNode } from '../workflowState'
import type { WorkflowNodeData, WorkflowNodeType } from '../workflowContracts'
import { decorateWorkflowEdges } from './workflowEdgeDecorators'

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

function nodeSummary(type: WorkflowNodeType, data: WorkflowNodeData) {
  if (type === 'open_page') return String(data.url || '设置目标地址')
  if (type === 'select_list') return String(data.item_selector || '设置列表选择器')
  if (type === 'extract_field') return `${data.fields?.length ?? 0} 个抽取字段`
  if (type === 'paginate') return `${data.pagination_strategy || 'click_next'} · 自动结束`
  if (type === 'loop') return String(data.on_error === 'stop' ? '失败即停止' : '失败跳过')
  if (type === 'condition') return String(data.condition || '设置条件')
  if (type === 'emit_record') {
    const mode = String(data.output_mode || 'memory')
    if (mode === 'sqlite') return `sqlite · ${String(data.sqlite_table || 'records')}`
    if (mode === 'json_file') return `json · ${String(data.json_file_path || 'output/crawler_output.json')}`
    return 'memory'
  }
  return 'Ready'
}

function resolveNodeVisual(type: WorkflowNodeType) {
  if (type === 'open_page') return { className: 'node-category-source', tagColor: 'blue', group: 'Source' }
  if (type === 'select_list' || type === 'paginate') return { className: 'node-category-collector', tagColor: 'cyan', group: 'Collect' }
  if (type === 'extract_field' || type === 'loop' || type === 'condition') return { className: 'node-category-transform', tagColor: 'purple', group: 'Transform' }
  return { className: 'node-category-sink', tagColor: 'green', group: 'Output' }
}

const WorkflowCanvasNode = memo(({ data, type, selected }: NodeProps<WorkflowNode>) => {
  const workflowType = type as WorkflowNodeType
  const visual = resolveNodeVisual(workflowType)

  return (
    <div className={`canvas-node-card ${visual.className} ${selected ? 'selected' : ''}`}>
      <Handle type="target" position={Position.Left} />
      <div className="canvas-node-meta-row">
        <Tag className="node-type" color={visual.tagColor}>{workflowType}</Tag>
        <Typography.Text className="canvas-node-group">{visual.group}</Typography.Text>
      </div>
      <strong>{String(data.label || nodeTypeLabels[workflowType])}</strong>
      <small>{nodeSummary(workflowType, data)}</small>
      <Handle type="source" position={Position.Right} />
    </div>
  )
})

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

type WorkflowCanvasProps = {
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  onNodesChange: (changes: NodeChange<WorkflowNode>[]) => void
  onEdgesChange: (changes: EdgeChange<WorkflowEdge>[]) => void
  onConnect: (connection: Connection) => void
  onNodeClick: (_event: React.MouseEvent, node: WorkflowNode) => void
  onPaneClick: () => void
  sourceNodeTypeById?: Partial<Record<string, WorkflowNodeType>>
  fitViewToken?: number
}

export function WorkflowCanvas({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeClick,
  onPaneClick,
  sourceNodeTypeById = {},
  fitViewToken,
}: WorkflowCanvasProps) {
  const decoratedEdges = useMemo(
    () => decorateWorkflowEdges(edges, sourceNodeTypeById),
    [edges, sourceNodeTypeById],
  )
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance<WorkflowNode, WorkflowEdge> | null>(null)
  const prevNodeCountRef = useRef(nodes.length)
  const graphHealth = useMemo(() => {
    const nodeIds = new Set(nodes.map((node) => node.id))
    const incoming = new Map<string, number>()
    const outgoing = new Map<string, number>()

    edges.forEach((edge) => {
      if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) return
      incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1)
      outgoing.set(edge.source, (outgoing.get(edge.source) ?? 0) + 1)
    })

    const entries = nodes.filter((node) => node.type === 'open_page')
    const hasTerminal = nodes.some((node) => node.type === 'end')
    const disconnected = nodes.filter((node) => (
      (incoming.get(node.id) ?? 0) === 0 && (outgoing.get(node.id) ?? 0) === 0
    ))
    const issues: string[] = []
    if (entries.length === 0) issues.push('缺少 open_page 入口节点')
    if (!hasTerminal) issues.push('缺少 end 终止节点')
    if (disconnected.length > 0) issues.push(`${disconnected.length} 个孤立节点`)

    return {
      entryCount: entries.length,
      hasTerminal,
      disconnectedCount: disconnected.length,
      issues,
      score: Math.max(0, 100 - issues.length * 20),
    }
  }, [edges, nodes])

  useEffect(() => {
    if (!rfInstance) {
      prevNodeCountRef.current = nodes.length
      return
    }
    if (nodes.length > prevNodeCountRef.current) {
      requestAnimationFrame(() => {
        rfInstance.fitView({ padding: 0.22, maxZoom: 1.15, duration: 260 })
      })
    }
    prevNodeCountRef.current = nodes.length
  }, [nodes.length, rfInstance])

  useEffect(() => {
    if (!rfInstance || typeof fitViewToken !== 'number') return
    requestAnimationFrame(() => {
      rfInstance.fitView({ padding: 0.2, maxZoom: 1.1, duration: 280 })
    })
  }, [fitViewToken, rfInstance])

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <Typography.Text strong style={{ fontSize: 16, color: 'var(--sd-color-ink)', letterSpacing: '-0.32px' }}>流程画布</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: '2px 0 0', lineHeight: 1.4 }}>
              在主舞台中编排抓取链路、观察节点关系，并联动下方结果区完成验证与迭代。
            </Typography.Paragraph>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <Tag color={graphHealth.issues.length === 0 ? 'success' : 'warning'} style={{ border: 'none', boxShadow: 'var(--sd-shadow-border)' }}>
              健康度 {graphHealth.score}
            </Tag>
            <Tag color="default" style={{ border: 'none', boxShadow: 'var(--sd-shadow-border)' }}>{nodes.length} 节点</Tag>
            <Tag color={graphHealth.hasTerminal ? 'success' : 'error'} style={{ border: 'none', boxShadow: 'var(--sd-shadow-border)' }}>
              {graphHealth.hasTerminal ? '含终止节点' : '缺少终止节点'}
            </Tag>
            {graphHealth.disconnectedCount > 0 ? <Tag color="warning" style={{ border: 'none', boxShadow: 'var(--sd-shadow-border)' }}>{graphHealth.disconnectedCount} 孤立</Tag> : null}
          </div>
        </div>
      }
      styles={{ body: { padding: 0 } }}
      className="canvas-region ant-canvas-card"
      variant="outlined"
    >
        <div className="canvas-surface">
          <div className="canvas-overlay">
            <Typography.Text strong style={{ fontSize: 13, color: 'var(--sd-color-ink)', letterSpacing: '-0.32px' }}>工作提示</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              支持拖拽、连线、选择与删除；新增节点会自动对齐到可视区域。
            </Typography.Text>
          {graphHealth.issues.length > 0 ? (
            <Typography.Text type="warning" style={{ fontSize: 11 }}>
              {graphHealth.issues[0]}
            </Typography.Text>
          ) : (
            <Typography.Text type="success" style={{ fontSize: 11 }}>
              图结构完整，可直接进入执行验证。
            </Typography.Text>
          )}
        </div>
        <ReactFlow
          nodes={nodes}
          edges={decoratedEdges}
          onInit={setRfInstance}
          nodeTypes={reactFlowNodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          fitView
          fitViewOptions={{ padding: 0.2, maxZoom: 1.1 }}
          nodesDraggable
          nodesConnectable
          elementsSelectable
          deleteKeyCode={['Backspace', 'Delete']}
          panOnDrag={[1, 2]}
          selectionOnDrag
          minZoom={0.35}
          maxZoom={1.6}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={24} size={1.2} color="rgba(148, 163, 184, 0.15)" />
          <MiniMap pannable zoomable />
          <Controls />
        </ReactFlow>
      </div>
    </Card>
  )
}
