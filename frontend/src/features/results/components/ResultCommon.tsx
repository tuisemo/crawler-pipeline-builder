import { useEffect, useRef } from 'react'
import { Tag } from 'antd'
import Editor from '@monaco-editor/react'
export { FullscreenEditorShell } from './FullscreenEditorShell'

export function StatTags({ value, accent }: { value: string; accent?: 'blue' | 'green' | 'orange' | 'red' | 'default' }) {
  return (
    <Tag color={accent} style={{ borderRadius: 999, paddingInline: 10 }}>
      {value}
    </Tag>
  )
}

export function EditorShell({
  value,
  language,
  height,
  readOnly,
  theme = 'vs-dark',
  wordWrap = 'on',
  onChange,
  visibilityToken,
}: {
  value: string
  language: string
  height: number | string
  readOnly: boolean
  theme?: 'vs' | 'vs-dark'
  wordWrap?: 'on' | 'off'
  onChange?: (value: string) => void
  visibilityToken?: number
}) {
  const editorRef = useRef<{ layout: () => void } | null>(null)

  useEffect(() => {
    if (!editorRef.current || visibilityToken === undefined) return
    requestAnimationFrame(() => editorRef.current?.layout())
    window.setTimeout(() => editorRef.current?.layout(), 120)
    window.setTimeout(() => editorRef.current?.layout(), 260)
  }, [visibilityToken])

  return (
    <div
      className="result-editor-shell"
      style={{ height: height || '100%', width: '100%', display: 'flex', flex: '1 1 auto', minWidth: 0, minHeight: 0, flexDirection: 'column' }}
    >
      <Editor
        height="100%"
        language={language}
        theme={theme}
        value={value}
        options={{
          automaticLayout: true,
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbersMinChars: 3,
          padding: { top: 14, bottom: 14 },
          scrollBeyondLastLine: false,
          readOnly,
          wordWrap,
          wrappingIndent: 'indent',
        }}
        onMount={(editor) => {
          editorRef.current = editor
          window.setTimeout(() => editor.layout(), 0)
          window.setTimeout(() => editor.layout(), 120)
        }}
        onChange={(next) => {
          if (readOnly || !onChange) return
          onChange(next ?? '')
        }}
      />
    </div>
  )
}
