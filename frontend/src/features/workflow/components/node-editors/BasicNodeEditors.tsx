import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Typography } from 'antd'
import type { WorkflowNode } from '../../workflowState'
import type { WorkflowNodeData } from '../../workflowContracts'

const PAGINATION_STRATEGIES = [
  { value: 'click_next', label: 'click_next' },
  { value: 'infinite_scroll', label: 'infinite_scroll' },
  { value: 'load_more', label: 'load_more' },
  { value: 'none', label: 'none' },
]

const ON_ERROR_OPTIONS = [
  { value: 'skip', label: '跳过当前项（skip）' },
  { value: 'stop', label: '立即停止（stop）' },
]

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

type NodeEditorProps = {
  selectedNode: WorkflowNode
  clampNumberInput: (value: string, min: number, max: number, fallback: number) => number
  updateSelectedNodeData: (patch: Partial<WorkflowNodeData>) => void
}

type AssistNodeEditorProps = NodeEditorProps & {
  assistBusyAction: string | null
  onTestSelector: (selector: string, selectorLabel: string) => void
}

export function OpenPageEditor({ selectedNode, updateSelectedNodeData }: NodeEditorProps) {
  return (
    <>
      <Form.Item
        label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>目标地址</Typography.Text>}
        validateStatus={normalizeText(selectedNode.data.url) ? undefined : 'error'}
        help={normalizeText(selectedNode.data.url) ? undefined : '请输入入口 URL。'}
      >
        <Input
          placeholder="https://example.com/page"
          value={String(selectedNode.data.url ?? '')}
          onChange={(e) => updateSelectedNodeData({ url: e.target.value })}
        />
      </Form.Item>
    </>
  )
}

export function SelectListEditor({
  selectedNode,
  updateSelectedNodeData,
  assistBusyAction,
  onTestSelector,
  onAutoDetectSelectList,
  onOptimizeListSelector,
}: AssistNodeEditorProps & {
  onAutoDetectSelectList: () => void
  onOptimizeListSelector: () => void
}) {
  return (
    <>
      <Space wrap size={8} style={{ width: '100%', marginBottom: 4 }}>
        <Button size="small" loading={assistBusyAction === 'auto-detect'} onClick={onAutoDetectSelectList}>
          自动检测列表
        </Button>
        <Button size="small" loading={assistBusyAction === 'optimize-selector'} onClick={onOptimizeListSelector}>
          优化选择器
        </Button>
        <Button
          size="small"
          loading={assistBusyAction === 'test-selector'}
          onClick={() => onTestSelector(String(selectedNode.data.item_selector ?? ''), '列表选择器')}
        >
          测试选择器
        </Button>
      </Space>
      <Form.Item
        label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>列表选择器</Typography.Text>}
        validateStatus={normalizeText(selectedNode.data.item_selector) ? undefined : 'error'}
        help={normalizeText(selectedNode.data.item_selector) ? undefined : '请填写 item_selector。'}
      >
        <Input.TextArea
          autoSize={{ minRows: 1, maxRows: 4 }}
          placeholder=".item-card"
          value={String(selectedNode.data.item_selector ?? '')}
          onChange={(e) => updateSelectedNodeData({ item_selector: e.target.value })}
        />
      </Form.Item>
    </>
  )
}

export function PaginateEditor({
  selectedNode,
  updateSelectedNodeData,
  assistBusyAction,
  onAnalyzePagination,
  onTestSelector,
}: AssistNodeEditorProps & {
  onAnalyzePagination: () => void
}) {
  return (
    <>
      <Space wrap size={8} style={{ width: '100%', marginBottom: 4 }}>
        <Button size="small" loading={assistBusyAction === 'analyze-pagination'} onClick={onAnalyzePagination}>
          AI 分析分页
        </Button>
        <Button
          size="small"
          loading={assistBusyAction === 'test-selector'}
          onClick={() => onTestSelector(String(selectedNode.data.pagination_selector ?? ''), '分页选择器')}
        >
          测试选择器
        </Button>
      </Space>
      <Form.Item
        label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>分页选择器</Typography.Text>}
        validateStatus={normalizeText(selectedNode.data.pagination_selector) ? undefined : 'error'}
        help={normalizeText(selectedNode.data.pagination_selector) ? undefined : '策略不是 none 时建议填写分页选择器。'}
      >
        <Input.TextArea
          autoSize={{ minRows: 1, maxRows: 4 }}
          placeholder="a.next"
          value={String(selectedNode.data.pagination_selector ?? '')}
          onChange={(e) => updateSelectedNodeData({ pagination_selector: e.target.value })}
        />
      </Form.Item>
      <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>分页策略</Typography.Text>}>
        <Select
          value={String(selectedNode.data.pagination_strategy ?? 'click_next')}
          options={PAGINATION_STRATEGIES}
          onChange={(val) => updateSelectedNodeData({ pagination_strategy: val })}
        />
      </Form.Item>
    </>
  )
}

export function LoopEditor({ selectedNode, updateSelectedNodeData }: NodeEditorProps) {
  return (
    <>
      <Alert
        title="循环控制"
        description="消费上游 select_list 的数据集合，按配置逐项执行后续节点。"
        type="info"
        showIcon
        style={{ marginBottom: 12, borderRadius: 10 }}
      />
      <Space size={8} style={{ width: '100%' }}>
        <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>单条失败策略</Typography.Text>} style={{ flex: 1 }}>
          <Select
            value={String(selectedNode.data.on_error ?? 'skip')}
            options={ON_ERROR_OPTIONS}
            onChange={(val) => updateSelectedNodeData({ on_error: val as 'skip' | 'stop' })}
          />
        </Form.Item>
      </Space>
    </>
  )
}

export function EndEditor() {
  return (
    <Alert
      title="结束节点"
      description="显式标记当前流程路径终止。执行到此处后，不再继续调度后续节点。"
      type="success"
      showIcon
      style={{ borderRadius: 10 }}
    />
  )
}

const CONDITION_BRANCH_OPTIONS = [
  { value: 'true', label: 'true 分支' },
  { value: 'false', label: 'false 分支' },
  { value: 'default', label: 'default 分支' },
]

const EXPRESSION_MODES = [
  { value: 'simple', label: '简单模式（推荐）' },
  { value: 'advanced', label: '高级模式' },
]

export function ConditionEditor({
  selectedNode,
  updateSelectedNodeData,
  conditionOutgoingEdges,
  updateConditionEdge,
}: NodeEditorProps & {
  conditionOutgoingEdges: Array<{
    id: string
    target: string
    branch?: string
    label?: string
    order?: number
  }>
  updateConditionEdge: (edgeId: string, patch: any) => void
}) {
  return (
    <>
      <Alert
        title="条件分支"
        description="基于白名单表达式判断，支持字段存在、包含、等于等操作符。"
        type="info"
        showIcon
        style={{ marginBottom: 12, borderRadius: 10 }}
      />
      <Form.Item
        label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>条件表达式（simple 模式）</Typography.Text>}
        validateStatus={normalizeText(selectedNode.data.condition) ? undefined : 'warning'}
        help={normalizeText(selectedNode.data.condition) ? undefined : 'simple 模式建议提供条件表达式。'}
      >
        <Input
          placeholder={'例如：title 包含 "仪器"'}
          value={String(selectedNode.data.condition ?? '')}
          onChange={(e) => updateSelectedNodeData({ condition: e.target.value })}
        />
      </Form.Item>
      <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>表达式模式</Typography.Text>}>
        <Select
          value={String(selectedNode.data.expression_mode ?? 'simple')}
          options={EXPRESSION_MODES}
          onChange={(val) => updateSelectedNodeData({ expression_mode: val as 'simple' | 'advanced' })}
        />
      </Form.Item>
      <Typography.Text strong style={{ fontSize: 13, color: '#0f172a', display: 'block', marginBottom: 6 }}>
        出边分支映射
      </Typography.Text>
      {conditionOutgoingEdges.length === 0 ? (
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 0 }}>
          当前条件节点尚未连出边。请先在画布上连接 true/false 分支。
        </Typography.Paragraph>
      ) : null}
      {conditionOutgoingEdges.map((edge) => (
        <Card key={edge.id} size="small" style={{ marginBottom: 8, background: '#f8fafc', border: '1px solid #e5edf6' }}>
          <Space orientation="vertical" size={6} style={{ width: '100%' }}>
            <Typography.Text style={{ fontSize: 12 }}>
              目标节点：<Typography.Text code>{edge.target}</Typography.Text>
            </Typography.Text>
            <Space size={6} style={{ width: '100%' }}>
              <Select
                style={{ width: 130 }}
                value={String(edge.branch ?? 'default')}
                options={CONDITION_BRANCH_OPTIONS}
                onChange={(value) => {
                  const branchLabel = value === 'true' ? 'TRUE' : value === 'false' ? 'FALSE' : 'DEFAULT'
                  updateConditionEdge(edge.id, { branch: value as any, label: branchLabel })
                }}
              />
              <Input
                placeholder="边标签"
                value={edge.label ?? ''}
                onChange={(e) => updateConditionEdge(edge.id, { label: e.target.value })}
              />
              <InputNumber
                min={0}
                max={99}
                value={typeof edge.order === 'number' ? edge.order : undefined}
                onChange={(value) => updateConditionEdge(edge.id, { order: typeof value === 'number' ? value : undefined })}
              />
            </Space>
          </Space>
        </Card>
      ))}
    </>
  )
}

const OUTPUT_MODE_OPTIONS = [
  { value: 'memory', label: '内存结果（memory）' },
  { value: 'json_file', label: 'JSON 文件（json_file）' },
  { value: 'sqlite', label: 'SQLite 数据库（sqlite）' },
]

const WRITE_MODE_OPTIONS = [
  { value: 'append', label: '追加写入（append）' },
  { value: 'upsert', label: '去重更新（upsert）' },
]

export function EmitRecordEditor({
  selectedNode,
  updateSelectedNodeData,
  clampNumberInput,
  workflowContext,
}: NodeEditorProps & {
  workflowContext: any
}) {
  const emitDedupeKeys = Array.isArray(selectedNode.data.dedupe_keys)
    ? selectedNode.data.dedupe_keys.filter((key): key is string => typeof key === 'string' && key.trim().length > 0)
    : []

  return (
    <>
      <Alert
        title="输出节点"
        description="默认仅把记录保留在结果面板中；如需落盘，可切换为 JSON 文件或 SQLite。"
        type="success"
        showIcon
        style={{ borderRadius: 10, marginBottom: 12 }}
      />
      <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>输出模式</Typography.Text>}>
        <Select
          value={String(selectedNode.data.output_mode ?? 'memory')}
          options={OUTPUT_MODE_OPTIONS}
          onChange={(value) => updateSelectedNodeData({ output_mode: value })}
        />
      </Form.Item>
      {String(selectedNode.data.output_mode ?? 'memory') === 'json_file' && (
        <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>JSON 文件路径</Typography.Text>}>
          <Input
            placeholder="output/crawler_output.json"
            value={String(selectedNode.data.json_file_path ?? '')}
            onChange={(e) => updateSelectedNodeData({ json_file_path: e.target.value })}
          />
        </Form.Item>
      )}
      {String(selectedNode.data.output_mode ?? 'memory') === 'sqlite' && (
        <>
          <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>SQLite 文件路径</Typography.Text>}>
            <Input
              placeholder="output/crawler_output.db"
              value={String(selectedNode.data.sqlite_path ?? '')}
              onChange={(e) => updateSelectedNodeData({ sqlite_path: e.target.value })}
            />
          </Form.Item>
          <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>数据表名</Typography.Text>}>
            <Input
              placeholder="records"
              value={String(selectedNode.data.sqlite_table ?? '')}
              onChange={(e) => updateSelectedNodeData({ sqlite_table: e.target.value })}
            />
          </Form.Item>
        </>
      )}
      {String(selectedNode.data.output_mode ?? 'memory') !== 'memory' && (
        <>
          <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>写入模式</Typography.Text>}>
            <Select
              value={String(selectedNode.data.write_mode ?? 'append')}
              options={WRITE_MODE_OPTIONS}
              onChange={(value) => updateSelectedNodeData({ write_mode: value })}
            />
          </Form.Item>
          <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>去重键</Typography.Text>}>
            <Input
              placeholder="detail_url, product_id"
              value={emitDedupeKeys.join(', ')}
              onChange={(e) => updateSelectedNodeData({
                dedupe_keys: e.target.value
                  .split(',')
                  .map((item) => item.trim())
                  .filter(Boolean),
              })}
            />
            <Typography.Paragraph type="secondary" style={{ margin: '6px 0 0', fontSize: 11 }}>
              多个字段用逗号分隔。留空时，系统会回退到整条记录哈希去重。
            </Typography.Paragraph>
          </Form.Item>
          <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>批量写入条数</Typography.Text>}>
            <InputNumber
              min={1}
              max={1000}
              style={{ width: '100%' }}
              value={Number(selectedNode.data.batch_size ?? 50)}
              onChange={(value) => updateSelectedNodeData({ batch_size: clampNumberInput(String(value ?? 50), 1, 1000, 50) })}
            />
          </Form.Item>
        </>
      )}
      {!workflowContext.hasTerminalNode && (
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 8, borderRadius: 10 }}
          description="建议在 emit_record 后增加 end 节点，形成清晰终止路径。"
        />
      )}
    </>
  )
}
