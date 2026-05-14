import { useEffect, useRef, useState } from 'react'
import { Button } from 'antd'
import { FullscreenOutlined, FullscreenExitOutlined } from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import type { editor } from 'monaco-editor'
import { copyText } from './resultHelpers'

export type FullscreenEditorShellProps = {
  value: string
  language: string
  height: number | string
  readOnly: boolean
  theme?: 'vs' | 'vs-dark'
  wordWrap?: 'on' | 'off'
  onChange?: (value: string) => void
  visibilityToken?: number
  label?: string
}

export function FullscreenEditorShell({
  value,
  language,
  height,
  readOnly,
  theme = 'vs-dark',
  wordWrap = 'on',
  onChange,
  label = '编辑器',
}: FullscreenEditorShellProps) {
  const [fullscreen, setFullscreen] = useState(false)
  const [copied, setCopied] = useState(false)
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null)

  useEffect(() => {
    if (!fullscreen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFullscreen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [fullscreen])

  useEffect(() => {
    if (fullscreen && editorRef.current) {
      window.setTimeout(() => editorRef.current?.layout(), 50)
    }
  }, [fullscreen])

  const handleCopy = async () => {
    const ok = await copyText(value)
    setCopied(ok)
    if (ok) setTimeout(() => setCopied(false), 1800)
  }

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Button size="small" icon={<FullscreenOutlined />} onClick={() => setFullscreen(true)}>
          全屏
        </Button>
        <span style={{ fontSize: 12, color: 'var(--sd-color-text-secondary)' }}>{label}</span>
      </div>

      <div
        className="result-editor-shell"
        style={{
          height: height || '100%',
          width: '100%',
          display: 'flex',
          flex: '1 1 auto',
          minWidth: 0,
          minHeight: 0,
          flexDirection: 'column',
        }}
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
          onMount={(ed) => {
            editorRef.current = ed
            window.setTimeout(() => ed.layout(), 0)
            window.setTimeout(() => ed.layout(), 120)
          }}
          onChange={(next) => {
            if (readOnly || !onChange) return
            onChange(next ?? '')
          }}
        />
      </div>

      {fullscreen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            background: '#0f172a',
            padding: '12px 16px',
            gap: 8,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setFullscreen(false)
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '8px 12px',
              background: 'rgba(255,255,255,0.06)',
              borderRadius: 8,
              flexShrink: 0,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ color: '#e2e8f0', fontSize: 14 }}>{label}</span>
              <span style={{ color: '#94a3b8', fontSize: 12 }}>按 ESC 或点击外部退出全屏</span>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button size="small" icon={<FullscreenExitOutlined />} onClick={() => setFullscreen(false)}>
                退出全屏
              </Button>
              <Button size="small" onClick={handleCopy}>
                {copied ? '已复制' : '复制内容'}
              </Button>
            </div>
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <Editor
              height="100%"
              language={language}
              theme={theme}
              value={value}
              options={{
                automaticLayout: true,
                minimap: { enabled: true },
                fontSize: 14,
                lineNumbersMinChars: 4,
                padding: { top: 16, bottom: 16 },
                scrollBeyondLastLine: false,
                readOnly,
                wordWrap,
                wrappingIndent: 'indent',
              }}
              onMount={(ed) => {
                editorRef.current = ed
                window.setTimeout(() => ed.layout(), 50)
              }}
              onChange={(next) => {
                if (readOnly || !onChange) return
                onChange(next ?? '')
              }}
            />
          </div>
        </div>
      )}
    </>
  )
}
