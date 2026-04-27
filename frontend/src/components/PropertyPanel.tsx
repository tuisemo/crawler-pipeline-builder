import {
  Alert,
  Button,
  Card,
  Collapse,
  Empty,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Typography,
} from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { WorkflowNode } from '../workflowState'
import type { CanonicalWorkflowEdge, ExtractionField, WorkflowNodeData } from '../workflowContracts'

type AssistApplyMode = 'current-only' | 'related-nodes'

type PropertyPanelProps = {
  selectedNode: WorkflowNode | null
  conditionOutgoingEdges: Array<{
    id: string
    target: string
    branch?: CanonicalWorkflowEdge['branch']
    label?: string
    order?: number
  }>
  workflowContext: {
    hasOpenPageNode: boolean
    hasSelectListNode: boolean
    hasTerminalNode: boolean
  }
  clampNumberInput: (value: string, min: number, max: number, fallback: number) => number
  updateSelectedNodeData: (patch: Partial<WorkflowNodeData>) => void
  updateExtractField: (index: number, patch: Partial<ExtractionField>) => void
  updateConditionEdge: (edgeId: string, patch: Partial<CanonicalWorkflowEdge>) => void
  assistApplyMode: AssistApplyMode
  setAssistApplyMode: (mode: AssistApplyMode) => void
  onAutoDetectSelectList: () => void
  onOptimizeListSelector: () => void
  onInferExtractFields: () => void
  onAnalyzePagination: () => void
  onCleanExtractField: (index: number) => void
  onTestSelector: (selector: string, selectorLabel: string) => void
  assistBusyAction: string | null
  addExtractField: () => void
  removeExtractField: (index: number) => void
  onDeleteNode: () => void
}

const EXTRACTION_TYPES = [
  { value: 'text', label: 'text' },
  { value: 'attr:href', label: 'attr:href' },
  { value: 'attr:src', label: 'attr:src' },
  { value: 'attr:href:abs', label: 'attr:href:abs' },
  { value: 'html', label: 'html' },
  { value: 'all(text)', label: 'all(text)' },
  { value: 'all(@href)', label: 'all(@href)' },
]

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

const OUTPUT_MODE_OPTIONS = [
  { value: 'memory', label: '内存结果（memory）' },
  { value: 'json_file', label: 'JSON 文件（json_file）' },
  { value: 'sqlite', label: 'SQLite 数据库（sqlite）' },
]

const WRITE_MODE_OPTIONS = [
  { value: 'append', label: '追加写入（append）' },
  { value: 'upsert', label: '去重更新（upsert）' },
]

const EXPRESSION_MODES = [
  { value: 'simple', label: '简单模式（推荐）' },
  { value: 'advanced', label: '高级模式' },
]

const CONDITION_BRANCH_OPTIONS = [
  { value: 'true', label: 'true 分支' },
  { value: 'false', label: 'false 分支' },
  { value: 'default', label: 'default 分支' },
]

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function buildFieldValidation(fields: ExtractionField[]) {
  const normalizedNames = fields.map((field) => normalizeText(field.name ?? field.field_name))
  const missingNameIndexes = new Set<number>()
  const missingSelectorIndexes = new Set<number>()
  const duplicateNameIndexes = new Set<number>()
  const seen = new Map<string, number>()

  fields.forEach((field, index) => {
    const name = normalizedNames[index]
    const selector = normalizeText(field.selector ?? field.css)
    if (!name) {
      missingNameIndexes.add(index)
    }
    if (!selector) {
      missingSelectorIndexes.add(index)
    }
    if (name) {
      if (seen.has(name)) {
        duplicateNameIndexes.add(index)
        duplicateNameIndexes.add(seen.get(name) ?? index)
      } else {
        seen.set(name, index)
      }
    }
  })

  return { missingNameIndexes, missingSelectorIndexes, duplicateNameIndexes }
}

function buildNodeIssues(node: WorkflowNode, workflowContext: PropertyPanelProps['workflowContext']): string[] {
  const issues: string[] = []
  const nodeLabel = normalizeText(node.data.label)
  if (!nodeLabel) {
    issues.push('建议为节点设置显示名称，便于在画布中快速识别。')
  }

  if (node.type === 'open_page') {
    const url = normalizeText(node.data.url)
    if (!url) issues.push('open_page 节点缺少目标地址。')
    if (url && !/^https?:\/\//i.test(url)) issues.push('目标地址应以 http:// 或 https:// 开头。')
  }

  if (node.type === 'select_list') {
    const selector = normalizeText(node.data.item_selector)
    if (!selector) issues.push('select_list 节点缺少 item_selector。')
    if (!workflowContext.hasOpenPageNode) issues.push('当前流程缺少 open_page 节点，列表选择器无法稳定运行。')
  }

  if (node.type === 'extract_field') {
    const fields = node.data.fields ?? []
    if (fields.length === 0) {
      issues.push('extract_field 节点至少需要一个字段定义。')
    }
    const fieldValidation = buildFieldValidation(fields)
    if (fieldValidation.missingNameIndexes.size > 0) issues.push('存在字段缺少名称。')
    if (fieldValidation.missingSelectorIndexes.size > 0) issues.push('存在字段缺少选择器。')
    if (fieldValidation.duplicateNameIndexes.size > 0) issues.push('字段名称重复，输出会被覆盖。')
    if (!workflowContext.hasSelectListNode) issues.push('当前流程缺少 select_list 节点，字段抽取缺少上游列表输入。')
  }

  if (node.type === 'paginate') {
    const strategy = normalizeText(node.data.pagination_strategy ?? 'click_next')
    const selector = normalizeText(node.data.pagination_selector)
    if (strategy !== 'none' && !selector) {
      issues.push('分页策略不是 none 时必须提供 pagination_selector。')
    }
    if (!workflowContext.hasSelectListNode) {
      issues.push('建议在分页前配置 select_list 节点，否则翻页后无法抽取列表结果。')
    }
  }

  if (node.type === 'condition') {
    const mode = normalizeText(node.data.expression_mode ?? 'simple')
    const condition = normalizeText(node.data.condition)
    if (mode === 'simple' && !condition) {
      issues.push('condition 节点在 simple 模式下缺少条件表达式。')
    }
  }

  if (node.type === 'emit_record' && !workflowContext.hasTerminalNode) {
    issues.push('建议在 emit_record 后增加 end 节点，形成清晰终止路径。')
  }
  if (node.type === 'emit_record') {
    const mode = normalizeText(node.data.output_mode ?? 'memory')
    const jsonFilePath = normalizeText(node.data.json_file_path)
    const sqlitePath = normalizeText(node.data.sqlite_path)
    const sqliteTable = normalizeText(node.data.sqlite_table)
    if (mode === 'json_file' && !jsonFilePath) {
      issues.push('json_file 模式建议配置 json_file_path。')
    }
    if (mode === 'sqlite' && !sqlitePath) {
      issues.push('sqlite 模式建议配置 sqlite_path。')
    }
    if (mode === 'sqlite' && !sqliteTable) {
      issues.push('sqlite 模式建议配置 sqlite_table。')
    }
  }

  return issues
}

export function PropertyPanel({
  selectedNode,
  conditionOutgoingEdges,
  workflowContext,
  clampNumberInput,
  updateSelectedNodeData,
  updateExtractField,
  updateConditionEdge,
  assistApplyMode,
  setAssistApplyMode,
  onAutoDetectSelectList,
  onOptimizeListSelector,
  onInferExtractFields,
  onAnalyzePagination,
  onCleanExtractField,
  onTestSelector,
  assistBusyAction,
  addExtractField,
  removeExtractField,
  onDeleteNode,
}: PropertyPanelProps) {
  if (!selectedNode) {
    return (
      <Card
        className="properties-panel"
        title={<Typography.Text strong style={{ fontSize: 16, color: '#0f172a' }}>配置面板</Typography.Text>}
        extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>未选择节点</Typography.Text>}
        variant="outlined"
      >
        <Empty
          description={(
            <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
              请先在画布中选中一个节点，再编辑其规范配置与执行限制。
            </Typography.Paragraph>
          )}
          style={{ padding: '32px 0' }}
        />
      </Card>
    )
  }

  const nodeIssues = buildNodeIssues(selectedNode, workflowContext)
  const fields = selectedNode.data.fields ?? []
  const fieldValidation = buildFieldValidation(fields)
  const emitDedupeKeys = Array.isArray(selectedNode.data.dedupe_keys)
    ? selectedNode.data.dedupe_keys.filter((key): key is string => typeof key === 'string' && key.trim().length > 0)
    : []
  const showSelectorDependencyHint = (
    (selectedNode.type === 'extract_field' || selectedNode.type === 'paginate') && !workflowContext.hasSelectListNode
  )

  return (
    <Card
      title={(
        <Space>
          <Typography.Text strong style={{ fontSize: 16, color: '#0f172a' }}>配置面板</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>—</Typography.Text>
          <Typography.Text code style={{ fontSize: 12 }}>{selectedNode.id}</Typography.Text>
        </Space>
      )}
      extra={(
        <Button danger size="small" icon={<DeleteOutlined />} onClick={onDeleteNode}>
          删除节点
        </Button>
      )}
      styles={{ body: { padding: '12px 16px' } }}
      className="properties-panel ant-property-panel-card"
      variant="outlined"
    >
      {nodeIssues.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          title={`发现 ${nodeIssues.length} 项配置风险`}
          description={(
            <Space orientation="vertical" size={2} style={{ width: '100%' }}>
              {nodeIssues.map((issue) => (
                <Typography.Text key={issue} style={{ fontSize: 12 }}>
                  • {issue}
                </Typography.Text>
              ))}
            </Space>
          )}
          style={{ marginBottom: 12, borderRadius: 10 }}
        />
      ) : null}

      {showSelectorDependencyHint ? (
        <Alert
          type="info"
          showIcon
          title="依赖提示"
          description="当前流程中还没有 select_list 节点，建议先配置列表选择器再继续下游抽取/分页。"
          style={{ marginBottom: 12, borderRadius: 10 }}
        />
      ) : null}

      <Form layout="vertical" size="small">
        <Collapse
          size="small"
          defaultActiveKey={['base', 'config']}
          items={[
            {
              key: 'base',
              label: '基础信息',
              children: (
                <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                  <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>AI 回填策略</Typography.Text>}>
                    <Select
                      value={assistApplyMode}
                      options={[
                        { value: 'current-only', label: '仅当前节点' },
                        { value: 'related-nodes', label: '当前 + 关联节点' },
                      ]}
                      onChange={(mode) => setAssistApplyMode(mode as AssistApplyMode)}
                    />
                    <Typography.Paragraph type="secondary" style={{ margin: '6px 0 0', fontSize: 11 }}>
                      仅当前节点：只改选中节点。当前 + 关联节点：同时回填 `extract_field` / `paginate` / `select_list` 关联配置。
                    </Typography.Paragraph>
                  </Form.Item>
                  <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>节点类型</Typography.Text>}>
                    <Input value={selectedNode.type} readOnly />
                  </Form.Item>
                  <Form.Item
                    label={<Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>显示名称</Typography.Text>}
                    validateStatus={normalizeText(selectedNode.data.label) ? undefined : 'warning'}
                    help={normalizeText(selectedNode.data.label) ? undefined : '建议填写业务语义名称，便于图上排查问题。'}
                  >
                    <Input
                      value={String(selectedNode.data.label ?? '')}
                      onChange={(e) => updateSelectedNodeData({ label: e.target.value })}
                    />
                  </Form.Item>
                </Space>
              ),
            },
            {
              key: 'config',
              label: '节点配置',
              children: (
                <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                  {selectedNode.type === 'open_page' && (
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
                  )}

                  {selectedNode.type === 'select_list' && (
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
                  )}

                  {selectedNode.type === 'extract_field' && (
                    <>
                      <Space wrap size={8} style={{ width: '100%', marginBottom: 4 }}>
                        <Button size="small" loading={assistBusyAction === 'infer-fields'} onClick={onInferExtractFields}>
                          AI 推断字段
                        </Button>
                      </Space>
                      <Typography.Text strong style={{ fontSize: 13, color: '#0f172a', display: 'block', marginBottom: 4 }}>
                        字段抽取
                      </Typography.Text>
                      <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: '0 0 10px' }}>
                        为输出结构定义字段名、选择器与抽取方式。
                      </Typography.Paragraph>
                      {fields.map((field, index) => {
                        const hasMissingName = fieldValidation.missingNameIndexes.has(index)
                        const hasMissingSelector = fieldValidation.missingSelectorIndexes.has(index)
                        const hasDuplicateName = fieldValidation.duplicateNameIndexes.has(index)
                        return (
                          <Card key={`${selectedNode.id}-field-${index}`} size="small" style={{ marginBottom: 8, background: '#f8fafc', border: '1px solid #e5edf6' }}>
                            <Space orientation="vertical" size={6} style={{ width: '100%' }}>
                              <Space size={6} style={{ width: '100%', alignItems: 'flex-start' }}>
                                <Input
                                  placeholder="字段名"
                                  status={hasMissingName || hasDuplicateName ? 'error' : undefined}
                                  value={field.name}
                                  style={{ flex: 1 }}
                                  onChange={(e) => updateExtractField(index, { name: e.target.value })}
                                />
                                <Select
                                  value={field.type}
                                  style={{ width: 140 }}
                                  options={EXTRACTION_TYPES}
                                  onChange={(val) => updateExtractField(index, { type: val })}
                                />
                                <Button
                                  danger
                                  size="small"
                                  icon={<DeleteOutlined />}
                                  onClick={() => removeExtractField(index)}
                                  style={{ marginTop: 4 }}
                                />
                              </Space>
                              
                              <Input.TextArea
                                placeholder="多层级选择器路径 (例如: div > a.title)"
                                status={hasMissingSelector ? 'error' : undefined}
                                value={field.selector}
                                autoSize={{ minRows: 1, maxRows: 4 }}
                                style={{ width: '100%' }}
                                onChange={(e) => updateExtractField(index, { selector: e.target.value })}
                              />
                              {hasMissingName ? <Typography.Text type="danger" style={{ fontSize: 11 }}>字段名不能为空。</Typography.Text> : null}
                              {hasDuplicateName ? <Typography.Text type="danger" style={{ fontSize: 11 }}>字段名重复，结果会被覆盖。</Typography.Text> : null}
                              {hasMissingSelector ? <Typography.Text type="danger" style={{ fontSize: 11 }}>选择器不能为空。</Typography.Text> : null}
                              <Space size={6} style={{ width: '100%' }}>
                                <Input
                                  placeholder="样例原始值（用于 AI 清洗）"
                                  value={typeof field.sample_value === 'string' ? field.sample_value : ''}
                                  style={{ flex: 1.6 }}
                                  onChange={(e) => updateExtractField(index, { sample_value: e.target.value })}
                                />
                                <Input
                                  placeholder="清洗类型（可选）"
                                  value={typeof field.clean_data_type === 'string' ? field.clean_data_type : ''}
                                  style={{ flex: 1 }}
                                  onChange={(e) => updateExtractField(index, { clean_data_type: e.target.value })}
                                />
                                <Button size="small" loading={assistBusyAction === 'clean-data'} onClick={() => onCleanExtractField(index)}>
                                  AI 清洗
                                </Button>
                                <Button
                                  size="small"
                                  loading={assistBusyAction === 'test-selector'}
                                  onClick={() => onTestSelector(String(field.selector ?? ''), `字段 ${field.name || index + 1} 选择器`)}
                                >
                                  测试
                                </Button>
                              </Space>
                              <Input
                                placeholder="清洗结果"
                                value={typeof field.normalized_sample === 'string' ? field.normalized_sample : ''}
                                readOnly
                              />
                            </Space>
                          </Card>
                        )
                      })}
                      <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={addExtractField} style={{ width: '100%', marginTop: 4 }}>
                        新增字段
                      </Button>
                    </>
                  )}

                  {selectedNode.type === 'paginate' && (
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
                  )}

                  {selectedNode.type === 'loop' && (
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
                  )}

                  {selectedNode.type === 'condition' && (
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
                                  updateConditionEdge(edge.id, { branch: value as CanonicalWorkflowEdge['branch'], label: branchLabel })
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
                  )}

                  {selectedNode.type === 'emit_record' && (
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
                    </>
                  )}

                  {selectedNode.type === 'end' && (
                    <Alert
                      title="结束节点"
                      description="显式标记当前流程路径终止。执行到此处后，不再继续调度后续节点。"
                      type="success"
                      showIcon
                      style={{ borderRadius: 10 }}
                    />
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Form>
    </Card>
  )
}
