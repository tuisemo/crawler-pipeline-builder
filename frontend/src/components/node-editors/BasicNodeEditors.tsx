import { Alert, Button, Form, Input, InputNumber, Select, Space, Typography } from 'antd'
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

export function OpenPageEditor({ selectedNode, clampNumberInput, updateSelectedNodeData }: NodeEditorProps) {
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
      <Space size={8} style={{ width: '100%' }}>
        <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>最大页数</Typography.Text>} style={{ flex: 1 }}>
          <InputNumber
            min={1}
            max={1000}
            style={{ width: '100%' }}
            value={Number(selectedNode.data.max_pages ?? 2)}
            onChange={(val) => updateSelectedNodeData({ max_pages: clampNumberInput(String(val ?? 2), 1, 1000, 2) })}
          />
        </Form.Item>
        <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>最大步骤</Typography.Text>} style={{ flex: 1 }}>
          <InputNumber
            min={1}
            max={50}
            style={{ width: '100%' }}
            value={Number(selectedNode.data.max_steps ?? 20)}
            onChange={(val) => updateSelectedNodeData({ max_steps: clampNumberInput(String(val ?? 20), 1, 50, 20) })}
          />
        </Form.Item>
      </Space>
    </>
  )
}

export function SelectListEditor({
  selectedNode,
  clampNumberInput,
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
      <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>最大条目</Typography.Text>}>
        <InputNumber
          min={1}
          max={50000}
          style={{ width: '100%' }}
          value={Number(selectedNode.data.max_items ?? 5)}
          onChange={(val) => updateSelectedNodeData({ max_items: clampNumberInput(String(val ?? 5), 1, 50000, 5) })}
        />
      </Form.Item>
    </>
  )
}

export function PaginateEditor({
  selectedNode,
  clampNumberInput,
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
      <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>最大页数</Typography.Text>}>
        <InputNumber
          min={1}
          max={1000}
          style={{ width: '100%' }}
          value={Number(selectedNode.data.max_pages ?? 2)}
          onChange={(val) => updateSelectedNodeData({ max_pages: clampNumberInput(String(val ?? 2), 1, 1000, 2) })}
        />
      </Form.Item>
    </>
  )
}

export function LoopEditor({ selectedNode, clampNumberInput, updateSelectedNodeData }: NodeEditorProps) {
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
        <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>最大条目</Typography.Text>} style={{ flex: 1 }}>
          <InputNumber
            min={1}
            max={50}
            style={{ width: '100%' }}
            value={Number(selectedNode.data.max_items ?? 5)}
            onChange={(val) => updateSelectedNodeData({ max_items: clampNumberInput(String(val ?? 5), 1, 50, 5) })}
          />
        </Form.Item>
        <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>单条失败策略</Typography.Text>} style={{ flex: 1.4 }}>
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
