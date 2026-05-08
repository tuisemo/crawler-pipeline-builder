import { useEffect, useRef } from 'react'
import { Tag } from 'antd'
import Editor from '@monaco-editor/react'

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

export async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', 'true')
  textarea.style.position = 'absolute'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

export function formatSavedAt(savedAt?: number) {
  if (!savedAt) return '未保存'
  return new Date(savedAt).toLocaleString('zh-CN', { hour12: false })
}
