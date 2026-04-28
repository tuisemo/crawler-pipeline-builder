import { Button, Card, Input, Select, Space, Typography } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { WorkflowNode } from '../../workflowState'
import type { ExtractionField } from '../../workflowContracts'

const EXTRACTION_TYPES = [
  { value: 'text', label: 'text' },
  { value: 'attr:href', label: 'attr:href' },
  { value: 'attr:src', label: 'attr:src' },
  { value: 'attr:href:abs', label: 'attr:href:abs' },
  { value: 'html', label: 'html' },
  { value: 'all(text)', label: 'all(text)' },
  { value: 'all(@href)', label: 'all(@href)' },
]

type FieldValidation = {
  missingNameIndexes: Set<number>
  missingSelectorIndexes: Set<number>
  duplicateNameIndexes: Set<number>
}

type ExtractFieldEditorProps = {
  selectedNode: WorkflowNode
  fields: ExtractionField[]
  fieldValidation: FieldValidation
  assistBusyAction: string | null
  updateExtractField: (index: number, patch: Partial<ExtractionField>) => void
  addExtractField: () => void
  removeExtractField: (index: number) => void
  onInferExtractFields: () => void
  onCleanExtractField: (index: number) => void
  onTestSelector: (selector: string, selectorLabel: string) => void
}

export function ExtractFieldEditor({
  selectedNode,
  fields,
  fieldValidation,
  assistBusyAction,
  updateExtractField,
  addExtractField,
  removeExtractField,
  onInferExtractFields,
  onCleanExtractField,
  onTestSelector,
}: ExtractFieldEditorProps) {
  return (
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
  )
}
