import { Button, Checkbox, Descriptions, Input, Segmented, Space, Typography } from 'antd'
import { CopyOutlined, DownloadOutlined, EditOutlined, SaveOutlined } from '@ant-design/icons'
import { useState, useEffect } from 'react'
import { EditorShell, copyText } from './ResultCommon'

export type DetailBatchRunnerForm = {
  databasePath: string
  listTableName: string
  recordIdField: string
  detailUrlField: string
  taskTableName: string
  outputRoot: string
  concurrency: string
  batchSize: string
  maxAttempts: string
  timeout: string
  cliExecutable: string
  generationMode: 'skeleton_enhancement' | 'llm_skeleton_enhancement'
}

export type BatchRunnerWorkspaceProps = {
  script: string
  filename: string
  form: DetailBatchRunnerForm
  busy: boolean
  formatBusy: boolean
  saveBusy: boolean
  validation?: { passed: boolean }
  warnings: string[]
  generationMode?: string
  onUpdateForm: (patch: Partial<DetailBatchRunnerForm>) => void
  onGenerate: () => Promise<void>
  onRestoreDefaults: () => void
  onFormat: (content: string) => Promise<string | null>
  onSave: (path: string, content: string, overwrite: boolean) => Promise<void>
  visibilityToken?: number
}

export function BatchRunnerWorkspace({
  script: originalScript,
  filename,
  form,
  busy,
  formatBusy,
  saveBusy,
  validation,
  warnings,
  generationMode,
  onUpdateForm,
  onGenerate,
  onRestoreDefaults,
  onFormat,
  onSave,
  visibilityToken,
}: BatchRunnerWorkspaceProps) {
  const [draft, setDraft] = useState(originalScript)
  const [editable, setEditable] = useState(false)
  const [wrapMode, setWrapMode] = useState<'off' | 'on'>('off')
  const [savePath, setSavePath] = useState(`generated/${filename}`)
  const [overwrite, setOverwrite] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    setDraft(originalScript)
    setSavePath(`generated/${filename}`)
  }, [originalScript, filename])

  const handleCopy = async () => {
    await copyText(draft)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  const handleDownload = () => {
    const blob = new Blob([draft], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleFormat = async () => {
    const formatted = await onFormat(draft)
    if (formatted) setDraft(formatted)
  }

  return (
    <div className="result-workspace-block">
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        基于当前列表采集脚本的输出契约，生成一个独立的第二阶段批处理脚本。该脚本会从 SQLite 读取 <Typography.Text code>detail_url</Typography.Text>，并并发调用 <Typography.Text code>page-extractor collect</Typography.Text>。
      </Typography.Paragraph>

      <div className="detail-batch-form-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12, marginBottom: 16 }}>
        <Input
          value={form.databasePath}
          onChange={(e) => onUpdateForm({ databasePath: e.target.value })}
          addonBefore="数据库"
          placeholder="output/crawler_output.db"
        />
        <Input
          value={form.listTableName}
          onChange={(e) => onUpdateForm({ listTableName: e.target.value })}
          addonBefore="列表表"
          placeholder="records"
        />
        <Input
          value={form.recordIdField}
          onChange={(e) => onUpdateForm({ recordIdField: e.target.value })}
          addonBefore="记录主键"
          placeholder="record_id"
        />
        <Input
          value={form.detailUrlField}
          onChange={(e) => onUpdateForm({ detailUrlField: e.target.value })}
          addonBefore="详情 URL 字段"
          placeholder="detail_url"
        />
        <Input
          value={form.taskTableName}
          onChange={(e) => onUpdateForm({ taskTableName: e.target.value })}
          addonBefore="任务表"
          placeholder="detail_collection_tasks"
        />
        <Input
          value={form.outputRoot}
          onChange={(e) => onUpdateForm({ outputRoot: e.target.value })}
          addonBefore="CLI 输出根目录"
          placeholder="./detail-output"
        />
        <Input
          value={form.concurrency}
          onChange={(e) => onUpdateForm({ concurrency: e.target.value })}
          addonBefore="并发度"
          placeholder="4"
        />
        <Input
          value={form.batchSize}
          onChange={(e) => onUpdateForm({ batchSize: e.target.value })}
          addonBefore="批大小"
          placeholder="20"
        />
        <Input
          value={form.maxAttempts}
          onChange={(e) => onUpdateForm({ maxAttempts: e.target.value })}
          addonBefore="最大重试"
          placeholder="3"
        />
        <Input
          value={form.timeout}
          onChange={(e) => onUpdateForm({ timeout: e.target.value })}
          addonBefore="超时（秒）"
          placeholder="180"
        />
        <Input
          value={form.cliExecutable}
          onChange={(e) => onUpdateForm({ cliExecutable: e.target.value })}
          addonBefore="CLI 可执行名"
          placeholder="page-extractor"
        />
        <Segmented
          value={form.generationMode}
          onChange={(value) => onUpdateForm({ generationMode: value as any })}
          options={[
            { label: 'Deterministic', value: 'skeleton_enhancement' },
            { label: 'LLM Enhance', value: 'llm_skeleton_enhancement' },
          ]}
        />
      </div>

      <Space wrap style={{ marginBottom: 12 }}>
        <Button size="small" type="primary" loading={busy} onClick={onGenerate}>
          生成详情批处理脚本
        </Button>
        <Button size="small" onClick={onRestoreDefaults}>
          恢复推导默认值
        </Button>
      </Space>

      {originalScript ? (
        <div className="detail-batch-script-block" style={{ marginTop: 12 }}>
          <Space wrap style={{ marginBottom: 12 }}>
            <Button size="small" icon={<CopyOutlined />} onClick={handleCopy}>
              {copied ? '已复制' : '复制脚本'}
            </Button>
            <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload}>
              下载
            </Button>
            <Button size="small" icon={<EditOutlined />} type={editable ? 'primary' : 'default'} onClick={() => setEditable(!editable)}>
              {editable ? '结束编辑' : '编辑'}
            </Button>
            <Button size="small" loading={formatBusy} onClick={handleFormat}>
              格式化
            </Button>
            <Button size="small" type="primary" icon={<SaveOutlined />} loading={saveBusy} onClick={() => onSave(savePath, draft, overwrite)}>
              保存到项目
            </Button>
            <Segmented
              size="small"
              value={wrapMode}
              onChange={(value) => setWrapMode(value as 'off' | 'on')}
              options={[
                { label: '不换行', value: 'off' },
                { label: '自动换行', value: 'on' },
              ]}
            />
          </Space>
          <div className="script-save-row" style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
            <Input
              value={savePath}
              onChange={(e) => setSavePath(e.target.value)}
              addonBefore="保存路径"
              placeholder="generated/run_detail_batch.py"
              style={{ flex: '1 1 320px', minWidth: 280 }}
            />
            <Checkbox checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)}>
              覆盖已有文件
            </Checkbox>
          </div>
          {validation ? (
            <Descriptions size="small" column={1} bordered style={{ borderRadius: 8, overflow: 'hidden', marginBottom: 12 }}>
              <Descriptions.Item label="校验结果">{validation.passed ? 'passed' : 'failed'}</Descriptions.Item>
              <Descriptions.Item label="生成模式">{generationMode || '—'}</Descriptions.Item>
              {warnings.length > 0 && <Descriptions.Item label="Warnings">{warnings.join(' | ')}</Descriptions.Item>}
            </Descriptions>
          ) : null}
          <EditorShell
            value={draft}
            language="python"
            height={320}
            readOnly={!editable}
            theme="vs-dark"
            wordWrap={wrapMode}
            onChange={setDraft}
            visibilityToken={visibilityToken}
          />
        </div>
      ) : null}
    </div>
  )
}
