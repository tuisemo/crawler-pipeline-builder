import { Tag, Typography } from 'antd'
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
    <div className="dsl-editor-minimal" style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 2px', flexShrink: 0 }}>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          {dslFeedback}
        </Typography.Text>
        <Tag color={status.color === 'success' ? 'blue' : status.color === 'error' ? 'red' : 'orange'} style={{ margin: 0, fontSize: 10, borderRadius: 4 }}>
          {status.label}
        </Tag>
      </div>
    </div>
  )
}
