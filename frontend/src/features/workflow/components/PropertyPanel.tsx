import {
  Alert,
  Button,
  Card,
  Collapse,
  Empty,
  Form,
  Input,
  Select,
  Space,
  Typography,
} from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import './PropertyPanel.css'
import type { WorkflowNode } from '../workflowState'
import type { AssistApplyMode, CanonicalWorkflowEdge, ExtractionField, WorkflowNodeData } from '../workflowContracts'
import {
  ConditionEditor,
  EmitRecordEditor,
  EndEditor,
  LoopEditor,
  OpenPageEditor,
  PaginateEditor,
  SelectListEditor,
} from './node-editors/BasicNodeEditors'
import { ExtractFieldEditor } from './node-editors/ExtractFieldEditor'


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
  onInferExtractFields: (userIntent?: string) => void
  onAnalyzePagination: () => void
  onTestSelector: (selector: string, selectorLabel: string) => void
  assistBusyAction: string | null
  addExtractField: () => void
  removeExtractField: (index: number) => void
  onDeleteNode: () => void
}


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
                  <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12 }}>AI 回填策略</Typography.Text>}>
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
                  <Form.Item label={<Typography.Text type="secondary" style={{ fontSize: 12 }}>节点类型</Typography.Text>}>
                    <Input value={selectedNode.type} readOnly />
                  </Form.Item>
                  <Form.Item
                    label={<Typography.Text type="secondary" style={{ fontSize: 12 }}>显示名称</Typography.Text>}
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
                    <OpenPageEditor
                      selectedNode={selectedNode}
                      clampNumberInput={clampNumberInput}
                      updateSelectedNodeData={updateSelectedNodeData}
                    />
                  )}

                  {selectedNode.type === 'select_list' && (
                    <SelectListEditor
                      selectedNode={selectedNode}
                      clampNumberInput={clampNumberInput}
                      updateSelectedNodeData={updateSelectedNodeData}
                      assistBusyAction={assistBusyAction}
                      onAutoDetectSelectList={onAutoDetectSelectList}
                      onOptimizeListSelector={onOptimizeListSelector}
                      onTestSelector={onTestSelector}
                    />
                  )}

                  {selectedNode.type === 'extract_field' && (
                    <ExtractFieldEditor
                      selectedNode={selectedNode}
                      fields={fields}
                      fieldValidation={fieldValidation}
                      assistBusyAction={assistBusyAction}
                      updateExtractField={updateExtractField}
                      addExtractField={addExtractField}
                      removeExtractField={removeExtractField}
                      onInferExtractFields={onInferExtractFields}
                      onTestSelector={onTestSelector}
                    />
                  )}

                  {selectedNode.type === 'paginate' && (
                    <PaginateEditor
                      selectedNode={selectedNode}
                      clampNumberInput={clampNumberInput}
                      updateSelectedNodeData={updateSelectedNodeData}
                      assistBusyAction={assistBusyAction}
                      onAnalyzePagination={onAnalyzePagination}
                      onTestSelector={onTestSelector}
                    />
                  )}

                  {selectedNode.type === 'loop' && (
                    <LoopEditor
                      selectedNode={selectedNode}
                      clampNumberInput={clampNumberInput}
                      updateSelectedNodeData={updateSelectedNodeData}
                    />
                  )}

                  {selectedNode.type === 'condition' && (
                    <ConditionEditor
                      selectedNode={selectedNode}
                      updateSelectedNodeData={updateSelectedNodeData}
                      conditionOutgoingEdges={conditionOutgoingEdges.map(e => ({ ...e, branch: String(e.branch ?? 'default') }))}
                      updateConditionEdge={updateConditionEdge}
                      clampNumberInput={clampNumberInput}
                    />
                  )}

                  {selectedNode.type === 'emit_record' && (
                    <EmitRecordEditor
                      selectedNode={selectedNode}
                      updateSelectedNodeData={updateSelectedNodeData}
                      clampNumberInput={clampNumberInput}
                      workflowContext={workflowContext}
                    />
                  )}

                  {selectedNode.type === 'end' && (
                    <EndEditor />
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
