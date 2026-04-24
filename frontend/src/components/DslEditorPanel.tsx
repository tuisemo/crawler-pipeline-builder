import { Alert, Card, Tag, Typography } from 'antd'
import Editor from '@monaco-editor/react'
import type { DslStatus } from '../workflowState'

type DslEditorPanelProps = {
  dslStatus: DslStatus
  dslFeedback: string
  dslText: string
  onChange: (value: string | undefined) => void
}

const statusMap: Record<DslStatus, { color: 'success' | 'warning' | 'error' | 'info'; label: string }> = {
  synced: { color: 'success', label: 'Canonical graph JSON' },
  'parse-error': { color: 'error', label: 'Last valid graph preserved' },
  'schema-error': { color: 'warning', label: 'Last valid graph preserved' },
}

export function DslEditorPanel({ dslStatus, dslFeedback, dslText, onChange }: DslEditorPanelProps) {
  const status = statusMap[dslStatus]

  return (
    <Card
      className="dsl-editor ant-dsl-editor-card"
      style={{ height: '100%', minHeight: 0 }}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Typography.Text strong style={{ fontSize: 16, color: '#0f172a' }}>DSL Editor</Typography.Text>
          <Tag color={status.color === 'success' ? 'blue' : status.color === 'error' ? 'red' : 'orange'}>
            {status.label}
          </Tag>
        </div>
      }
      extra={
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {dslStatus === 'synced' ? '画布与 DSL 已保持同步' : '保留上次有效图形'}
        </Typography.Text>
      }
      styles={{ body: { padding: '0 16px 16px', display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 } }}
      variant="outlined"
    >
      <Alert
        title={<span style={{ color: '#0f172a', fontWeight: 500 }}>{dslFeedback}</span>}
        type={status.color}
        showIcon
        style={{
          marginBottom: 12,
          borderRadius: 10,
          flexShrink: 0,
          backgroundColor: status.color === 'success' ? '#f0fdf4' : status.color === 'error' ? '#fef2f2' : '#fffbeb',
          borderColor: status.color === 'success' ? '#bbf7d0' : status.color === 'error' ? '#fecaca' : '#fde68a',
        }}
      />
      <div className="monaco-shell dsl-monaco-shell" style={{ flex: 1, minHeight: 0 }}>
        <Editor
          height="100%"
          language="json"
          theme="vs-dark"
          value={dslText}
          options={{
            automaticLayout: true,
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbersMinChars: 3,
            padding: { top: 14, bottom: 14 },
            scrollBeyondLastLine: false,
            wordWrap: 'on',
            wrappingIndent: 'indent',
          }}
          onChange={(value) => onChange(value ?? '')}
        />
      </div>
    </Card>
  )
}
