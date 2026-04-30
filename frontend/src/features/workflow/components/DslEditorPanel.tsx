import { Alert, Card, Tag, Typography } from 'antd'
import Editor from '@monaco-editor/react'
import { useEffect, useRef } from 'react'
import type { DslStatus } from '../workflowState'

type DslEditorPanelProps = {
  dslStatus: DslStatus
  dslFeedback: string
  dslText: string
  onChange: (value: string | undefined) => void
  showHeader?: boolean
  contextSummary?: {
    selectedNodeId: string
    nodeCount: number
    edgeCount: number
    fieldCount: number
  }
  visibilityToken?: number
}

const statusMap: Record<DslStatus, { color: 'success' | 'warning' | 'error' | 'info'; label: string }> = {
  synced: { color: 'success', label: 'Canonical graph JSON' },
  'parse-error': { color: 'error', label: 'Last valid graph preserved' },
  'schema-error': { color: 'warning', label: 'Last valid graph preserved' },
}

export function DslEditorPanel({
  dslStatus,
  dslFeedback,
  dslText,
  onChange,
  showHeader = true,
  contextSummary,
  visibilityToken,
}: DslEditorPanelProps) {
  const status = statusMap[dslStatus]
  const editorRef = useRef<{ layout: () => void } | null>(null)

  useEffect(() => {
    if (!editorRef.current || visibilityToken === undefined) return
    requestAnimationFrame(() => editorRef.current?.layout())
    window.setTimeout(() => editorRef.current?.layout(), 120)
    window.setTimeout(() => editorRef.current?.layout(), 260)
  }, [visibilityToken])

  return (
    <Card
      className="dsl-editor ant-dsl-editor-card"
      style={{ height: '100%', minHeight: 0 }}
      title={showHeader ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Typography.Text strong style={{ fontSize: 16, color: 'var(--sd-color-ink)', letterSpacing: '-0.32px' }}>DSL Editor</Typography.Text>
          <Tag color={status.color === 'success' ? 'blue' : status.color === 'error' ? 'red' : 'orange'}>
            {status.label}
          </Tag>
        </div>
      ) : undefined}
      extra={showHeader ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {dslStatus === 'synced' ? '画布与 DSL 已保持同步' : '保留上次有效图形'}
        </Typography.Text>
      ) : undefined}
      styles={{ body: { padding: '0 16px 16px', display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 } }}
      variant="outlined"
    >
      {contextSummary ? (
        <div className="workspace-context-strip">
          <Typography.Text className="workspace-context-chip">
            当前节点 {contextSummary.selectedNodeId || '未选择'}
          </Typography.Text>
          <Typography.Text className="workspace-context-chip">
            {contextSummary.nodeCount} 节点 / {contextSummary.edgeCount} 连线
          </Typography.Text>
          <Typography.Text className="workspace-context-chip">
            {contextSummary.fieldCount} 个字段
          </Typography.Text>
        </div>
      ) : null}

      <Alert
        title={<span style={{ color: 'var(--sd-color-ink)', fontWeight: 500 }}>{dslFeedback}</span>}
        type={status.color}
        showIcon
        style={{
          marginBottom: 12,
          borderRadius: 'var(--sd-radius-lg)',
          border: 'none',
          boxShadow: 'var(--sd-shadow-border)',
          flexShrink: 0,
        }}
      />
      <div className="monaco-shell dsl-monaco-shell" style={{ flex: 1, minHeight: 0 }}>
        <Editor
          height="100%"
          language="json"
          theme="vs-dark"
          value={dslText}
          onMount={(editor) => {
            editorRef.current = editor
            window.setTimeout(() => editor.layout(), 0)
            window.setTimeout(() => editor.layout(), 120)
          }}
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
