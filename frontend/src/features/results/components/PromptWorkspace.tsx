import { Button, Space, Typography } from 'antd'
import { CopyOutlined, RedoOutlined, SaveOutlined } from '@ant-design/icons'
import { useState } from 'react'
import { StatTags, EditorShell } from './ResultCommon'
import { copyText, formatSavedAt } from './resultHelpers'

export type PromptWorkspaceProps = {
  graphKey: string
  value: string
  baseValue: string
  savedAt?: number
  hasSavedDraft: boolean
  isDirty: boolean
  onChange: (value: string) => void
  onSave: () => void
  onReset: () => void
}

export type PromptPreviewProps = {
  prompt: string
  effectivePrompt?: string
  promptWorkspace?: PromptWorkspaceProps | null
  visibilityToken?: number
}

function summarizeText(text: string) {
  return {
    lines: text.split('\n').length,
    chars: text.length,
  }
}

export function PromptWorkspace({
  workspace,
  stats,
  visibilityToken,
}: {
  workspace: PromptWorkspaceProps
  stats: { lines: number; chars: number }
  visibilityToken?: number
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await copyText(workspace.value)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <div className="result-workspace-block">
      <Space size={8} style={{ marginBottom: 12 }}>
        <Typography.Text strong>提示词工作区</Typography.Text>
        <StatTags value={`${stats.lines} 行`} />
        <StatTags value={`${stats.chars} 字符`} />
        {workspace.isDirty ? <StatTags value="未保存修改" accent="orange" /> : <StatTags value="已与默认同步" accent="green" />}
        {workspace.hasSavedDraft ? <StatTags value={`已保存 ${formatSavedAt(workspace.savedAt)}`} accent="blue" /> : null}
      </Space>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        这里编辑的是可定制提示词正文。执行脚本生成时，系统会自动在前面拼接固定执行计划与字段规则。
      </Typography.Paragraph>
      <Space wrap style={{ marginBottom: 12 }}>
        <Button size="small" icon={<CopyOutlined />} onClick={handleCopy}>
          {copied ? '已复制' : '复制提示词'}
        </Button>
        <Button size="small" type="primary" icon={<SaveOutlined />} onClick={workspace.onSave}>
          保存修改
        </Button>
        <Button size="small" icon={<RedoOutlined />} onClick={workspace.onReset}>
          恢复默认
        </Button>
      </Space>
      <EditorShell
        value={workspace.value}
        language="markdown"
        height={280}
        readOnly={false}
        onChange={workspace.onChange}
        visibilityToken={visibilityToken}
      />
    </div>
  )
}

export function PromptPreview({
  prompt,
  visibilityToken,
}: {
  prompt: string
  visibilityToken?: number
}) {
  const [copied, setCopied] = useState(false)
  const stats = summarizeText(prompt)

  const handleCopy = async () => {
    await copyText(prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <div className="result-workspace-block">
      <Space size={8} style={{ marginBottom: 12 }}>
        <Typography.Text strong>提示词预览</Typography.Text>
        <StatTags value={`${stats.lines} 行`} />
        <StatTags value={`${stats.chars} 字符`} />
      </Space>
      <Space style={{ marginBottom: 12 }}>
        <Button size="small" icon={<CopyOutlined />} onClick={handleCopy}>
          {copied ? '已复制' : '复制'}
        </Button>
      </Space>
      <EditorShell
        value={prompt}
        language="markdown"
        height={240}
        readOnly={true}
        visibilityToken={visibilityToken}
      />
    </div>
  )
}
