import { Button, Checkbox, Input, Segmented, Space, Typography } from 'antd'
import {
  CopyOutlined,
  DownloadOutlined,
  EditOutlined,
  PlayCircleOutlined,
  RedoOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import { useState } from 'react'
import { StatTags, FullscreenEditorShell } from './ResultCommon'
import { copyText } from './resultHelpers'

export type ScriptWorkspaceProps = {
  script: string
  filename: string
  model?: string
  formatBusy: boolean
  saveBusy: boolean
  sandboxBusy: boolean
  onFormat: (content: string) => Promise<string | null>
  onSave: (path: string, content: string, overwrite: boolean) => Promise<void>
  onRunSandbox: (content: string, filename: string) => Promise<void>
  onRestore: () => void
  visibilityToken?: number
}

function summarizeText(text: string) {
  return {
    lines: text.split('\n').length,
    chars: text.length,
  }
}

export function ScriptWorkspace({
  script: originalScript,
  filename,
  model,
  formatBusy,
  saveBusy,
  sandboxBusy,
  onFormat,
  onSave,
  onRunSandbox,
  onRestore,
  visibilityToken,
}: ScriptWorkspaceProps) {
  const [scriptDraft, setScriptDraft] = useState(() => originalScript)
  const [scriptEditable, setScriptEditable] = useState(false)
  const [scriptWrapMode, setScriptWrapMode] = useState<'off' | 'on'>('off')
  const [savePath, setSavePath] = useState(() => `generated/${filename}`)
  const [overwriteTarget, setOverwriteTarget] = useState(false)
  const [notice, setNotice] = useState('')
  const [noticeTone, setNoticeTone] = useState<'success' | 'warning' | 'error' | 'info'>('info')
  const [copied, setCopied] = useState(false)

  const stats = summarizeText(scriptDraft)
  const isDirty = scriptDraft !== originalScript

  const handleCopy = async () => {
    await copyText(scriptDraft)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  const handleDownload = () => {
    const blob = new Blob([scriptDraft], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleFormat = async () => {
    const formatted = await onFormat(scriptDraft)
    if (formatted) {
      setScriptDraft(formatted)
      setNotice('脚本已格式化。')
      setNoticeTone('success')
    }
  }

  return (
    <div className="result-workspace-block">
      <Space size={8} wrap style={{ marginBottom: 12 }}>
        <Typography.Text strong>脚本工作区</Typography.Text>
        <StatTags value={filename} accent="blue" />
        <StatTags value={`${stats.lines} 行`} />
        <StatTags value={`${stats.chars} 字符`} />
        {isDirty ? <StatTags value="已编辑" accent="orange" /> : <StatTags value="原始版本" accent="green" />}
        {scriptEditable ? <StatTags value="编辑模式" accent="red" /> : <StatTags value="只读模式" />}
        {model ? <StatTags value={`via ${model}`} accent="green" /> : null}
      </Space>

      <Space wrap style={{ marginBottom: 12 }}>
        <Button size="small" icon={<CopyOutlined />} onClick={handleCopy}>
          {copied ? '已复制' : '复制脚本'}
        </Button>
        <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload}>
          下载文件
        </Button>
        <Button size="small" icon={<EditOutlined />} type={scriptEditable ? 'primary' : 'default'} onClick={() => setScriptEditable(!scriptEditable)}>
          {scriptEditable ? '结束编辑' : '进入编辑'}
        </Button>
        <Button size="small" loading={formatBusy} onClick={handleFormat}>
          格式化
        </Button>
        <Button size="small" icon={<PlayCircleOutlined />} loading={sandboxBusy} onClick={() => onRunSandbox(scriptDraft, filename)}>
          运行沙箱
        </Button>
        <Button size="small" icon={<RedoOutlined />} onClick={() => {
          onRestore()
          setScriptDraft(originalScript)
          setSavePath(`generated/${filename}`)
          setOverwriteTarget(false)
          setNotice('已恢复到最近一次生成结果。')
          setNoticeTone('info')
        }}>
          恢复生成结果
        </Button>
        <Button size="small" type="primary" icon={<SaveOutlined />} loading={saveBusy} onClick={() => onSave(savePath, scriptDraft, overwriteTarget)}>
          保存到项目
        </Button>
        <Segmented
          size="small"
          value={scriptWrapMode}
          onChange={(value) => setScriptWrapMode(value as 'off' | 'on')}
          options={[
            { label: '不换行', value: 'off' },
            { label: '自动换行', value: 'on' },
          ]}
        />
      </Space>

      <div className="script-save-row" style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <Input
          value={savePath}
          onChange={(event) => setSavePath(event.target.value)}
          placeholder="generated/crawler.py"
          addonBefore="保存路径"
          style={{ flex: '1 1 320px', minWidth: 280 }}
        />
        <Checkbox checked={overwriteTarget} onChange={(event) => setOverwriteTarget(event.target.checked)}>
          覆盖已有文件
        </Checkbox>
      </div>

      {notice && (
        <Typography.Paragraph type={noticeTone === 'error' ? 'danger' : noticeTone === 'warning' ? 'warning' : 'secondary'} style={{ marginBottom: 12 }}>
          {notice}
        </Typography.Paragraph>
      )}

      <FullscreenEditorShell
        value={scriptDraft}
        language="python"
        height={280}
        readOnly={!scriptEditable}
        theme="vs-dark"
        wordWrap={scriptWrapMode}
        onChange={setScriptDraft}
        visibilityToken={visibilityToken}
        label="脚本编辑器"
      />
    </div>
  )
}
