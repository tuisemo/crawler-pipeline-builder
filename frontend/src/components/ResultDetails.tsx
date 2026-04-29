import {
  Button,
  Checkbox,
  Collapse,
  Descriptions,
  Input,
  Segmented,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import Editor from '@monaco-editor/react'
import {
  CheckCircleFilled,
  CloseCircleFilled,
  CopyOutlined,
  DownloadOutlined,
  EditOutlined,
  PlayCircleOutlined,
  RedoOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { extractEffectivePrompt, normalizeMultilineText, summarizeText } from '../promptDrafts'
import { postWorkflowAction } from '../services/workflowApi'
import { getErrorMessage } from '../workflowState'

type ExecutionLog = {
  level?: string
  message?: string
  node_id?: string | null
  [key: string]: unknown
}

type NodeExecutionResult = {
  node_id?: string
  node_type?: string
  success?: boolean
  error?: string | null
  result?: unknown
  logs?: ExecutionLog[]
}

export type PromptWorkspace = {
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

type ResultDetailsProps = {
  payload?: unknown
  promptWorkspace?: PromptWorkspace | null
  view?: ResultDetailsView
  focusMode?: boolean
  visibilityToken?: number
}

type CollapseItemConfig = {
  key: string
  label: ReactNode
  children: ReactNode
  extra?: ReactNode
}

export type ResultDetailsView = 'all' | 'script' | 'prompt' | 'records' | 'logs' | 'diagnostics'

const LEVEL_COLORS: Record<string, string> = {
  info: 'blue',
  warning: 'orange',
  error: 'red',
  debug: 'default',
}

async function copyText(text: string) {
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

function formatSavedAt(savedAt?: number) {
  if (!savedAt) return '未保存'
  return new Date(savedAt).toLocaleString('zh-CN', { hour12: false })
}

function resolveDefaultScriptPath(filename: string) {
  const trimmed = filename.trim() || 'crawler.py'
  return `generated/${trimmed}`.replace(/\/+/g, '/')
}

function StatTags({ value, accent }: { value: string; accent?: 'blue' | 'green' | 'orange' | 'red' }) {
  return (
    <Tag color={accent} style={{ borderRadius: 999, paddingInline: 10 }}>
      {value}
    </Tag>
  )
}

function EditorShell({
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

export function ResultDetails({ payload, promptWorkspace, view = 'all', focusMode = false, visibilityToken }: ResultDetailsProps) {
  const [copiedKey, setCopiedKey] = useState<string>('')
  const [scriptWrapMode, setScriptWrapMode] = useState<'off' | 'on'>('off')
  const [scriptEditable, setScriptEditable] = useState(false)
  const [scriptDraft, setScriptDraft] = useState('')
  const [savePath, setSavePath] = useState('')
  const [overwriteTarget, setOverwriteTarget] = useState(false)
  const [formatBusy, setFormatBusy] = useState(false)
  const [saveBusy, setSaveBusy] = useState(false)
  const [sandboxBusy, setSandboxBusy] = useState(false)
  const [manualSandboxResult, setManualSandboxResult] = useState<Record<string, unknown> | null>(null)
  const [scriptNotice, setScriptNotice] = useState('')
  const [scriptNoticeTone, setScriptNoticeTone] = useState<'success' | 'warning' | 'error' | 'info'>('info')

  const hasPayload = Boolean(payload)
  const record = hasPayload && typeof payload === 'object' && payload !== null ? payload as Record<string, unknown> : {}
  const prompt = typeof record.prompt === 'string' ? record.prompt : ''
  const effectivePrompt = extractEffectivePrompt(payload)
  const script = typeof record.script === 'string' ? record.script : ''
  const normalizedScript = script ? normalizeMultilineText(script) : ''
  const filename = typeof record.filename === 'string' ? record.filename : 'crawler.py'
  const model = typeof record.model === 'string' ? record.model : ''
  const usage = record.usage && typeof record.usage === 'object' ? record.usage as Record<string, unknown> : null
  const logs = Array.isArray(record.logs) ? record.logs as ExecutionLog[] : []
  const nodeResults = Array.isArray(record.node_results)
    ? record.node_results as NodeExecutionResult[]
    : record.result && typeof record.result === 'object'
      ? [record.result as NodeExecutionResult]
      : []
  const records = Array.isArray(record.records)
    ? record.records
    : Array.isArray(record.records_sample)
      ? record.records_sample
      : []
  const outputInfo = record.output && typeof record.output === 'object' ? record.output as Record<string, unknown> : null
  const checkpoint = record.checkpoint && typeof record.checkpoint === 'object' ? record.checkpoint as Record<string, unknown> : null
  const runId = typeof record.run_id === 'string' ? record.run_id : ''
  const jobId = typeof record.job_id === 'string' ? record.job_id : ''
  const sessionId = typeof record.session_id === 'string' ? record.session_id : ''
  const resumed = record.resumed === true
  const pagesProcessed = typeof record.pages_processed === 'number' ? record.pages_processed : null
  const emittedCount = typeof record.emitted_count === 'number' ? record.emitted_count : null
  const generationMode = typeof record.generation_mode === 'string' ? record.generation_mode : ''
  const generationTrace = Array.isArray(record.generation_trace)
    ? record.generation_trace.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    : []
  const warnings = Array.isArray(record.warnings)
    ? record.warnings.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
  const reviewSummary = record.review_summary && typeof record.review_summary === 'object'
    ? record.review_summary as Record<string, unknown>
    : null
  const sandboxResult = record.sandbox_result && typeof record.sandbox_result === 'object'
    ? record.sandbox_result as Record<string, unknown>
    : null
  const activeSandboxResult = manualSandboxResult ?? sandboxResult

  const promptValue = promptWorkspace?.value ?? ''
  const scriptResultKey = `${promptWorkspace?.graphKey ?? 'standalone'}:${filename}:${script}`
  const promptStats = useMemo(() => summarizeText(promptValue), [promptValue])
  const effectivePromptStats = useMemo(() => summarizeText(effectivePrompt), [effectivePrompt])
  const scriptStats = useMemo(() => summarizeText(scriptDraft), [scriptDraft])
  const scriptDirty = scriptDraft !== normalizedScript

  useEffect(() => {
    setScriptDraft(normalizedScript)
    setSavePath(resolveDefaultScriptPath(filename))
    setOverwriteTarget(false)
    setScriptEditable(false)
    setManualSandboxResult(null)
    setScriptNotice('')
    setScriptNoticeTone('info')
  }, [filename, normalizedScript, scriptResultKey])

  const handleCopy = async (key: string, text: string) => {
    await copyText(text)
    setCopiedKey(key)
    window.setTimeout(() => setCopiedKey(''), 1800)
  }

  const handleDownload = (text: string, name: string) => {
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleFormatScript() {
    if (!scriptDraft.trim()) {
      setScriptNoticeTone('warning')
      setScriptNotice('当前没有可格式化的脚本内容。')
      return
    }
    setFormatBusy(true)
    try {
      const { response, payload: formatPayload } = await postWorkflowAction('/api/workflows/format-script', {
        content: scriptDraft,
        language: 'python',
      })
      if (!response.ok) {
        throw new Error(getErrorMessage(formatPayload))
      }
      const result = formatPayload as Record<string, unknown>
      const formatted = typeof result.formatted_content === 'string' ? result.formatted_content : scriptDraft
      const warnings = Array.isArray(result.warnings) ? result.warnings.filter((item): item is string => typeof item === 'string') : []
      setScriptDraft(normalizeMultilineText(formatted))
      setScriptNoticeTone(warnings.length > 0 ? 'warning' : 'success')
      setScriptNotice(warnings[0] ?? '脚本已格式化。')
    } catch (error) {
      setScriptNoticeTone('error')
      setScriptNotice(error instanceof Error ? error.message : '脚本格式化失败。')
    } finally {
      setFormatBusy(false)
    }
  }

  async function handleSaveScript() {
    if (!scriptDraft.trim()) {
      setScriptNoticeTone('warning')
      setScriptNotice('请先生成或编辑脚本，再保存到项目文件。')
      return
    }
    setSaveBusy(true)
    try {
      const { response, payload: savePayload } = await postWorkflowAction('/api/workflows/save-script', {
        relative_path: savePath,
        content: scriptDraft,
        overwrite: overwriteTarget,
      })
      if (!response.ok) {
        throw new Error(getErrorMessage(savePayload))
      }
      const result = savePayload as Record<string, unknown>
      const savedPath = typeof result.relative_path === 'string' ? result.relative_path : savePath
      const overwritten = result.overwritten === true
      setScriptNoticeTone('success')
      setScriptNotice(overwritten ? `已覆盖保存到 ${savedPath}` : `已保存到 ${savedPath}`)
    } catch (error) {
      setScriptNoticeTone('error')
      setScriptNotice(error instanceof Error ? error.message : '脚本保存失败。')
    } finally {
      setSaveBusy(false)
    }
  }

  async function handleRunSandbox() {
    if (!scriptDraft.trim()) {
      setScriptNoticeTone('warning')
      setScriptNotice('当前没有可执行的脚本内容。')
      return
    }
    setSandboxBusy(true)
    try {
      const { response, payload: sandboxPayload } = await postWorkflowAction('/api/workflows/run-script-sandbox', {
        script: scriptDraft,
        filename,
      })
      const result = sandboxPayload as Record<string, unknown>
      const nextSandboxResult = result.sandbox_result && typeof result.sandbox_result === 'object'
        ? result.sandbox_result as Record<string, unknown>
        : result
      setManualSandboxResult(nextSandboxResult)
      if (!response.ok) {
        throw new Error(getErrorMessage(sandboxPayload))
      }
      const passed = nextSandboxResult.success === true
      setScriptNoticeTone(passed ? 'success' : 'error')
      setScriptNotice(passed ? '沙箱执行通过。' : `沙箱执行失败：${typeof nextSandboxResult.error === 'string' ? nextSandboxResult.error : '请查看执行日志。'}`)
    } catch (error) {
      setScriptNoticeTone('error')
      setScriptNotice(error instanceof Error ? error.message : '沙箱执行失败。')
    } finally {
      setSandboxBusy(false)
    }
  }

  const collapseItems: CollapseItemConfig[] = []

  if (promptWorkspace && promptValue) {
    collapseItems.push({
      key: 'prompt-workspace',
      label: (
        <Space size={8}>
          <Typography.Text strong>提示词工作区</Typography.Text>
          <StatTags value={`${promptStats.lines} 行`} />
          <StatTags value={`${promptStats.chars} 字符`} />
          {promptWorkspace.isDirty ? <StatTags value="未保存修改" accent="orange" /> : <StatTags value="已与默认同步" accent="green" />}
          {promptWorkspace.hasSavedDraft ? <StatTags value={`已保存 ${formatSavedAt(promptWorkspace.savedAt)}`} accent="blue" /> : null}
        </Space>
      ),
      children: (
        <div className="result-workspace-block">
          <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
            这里编辑的是可定制提示词正文。执行脚本生成时，系统会自动在前面拼接固定执行计划与字段规则。
          </Typography.Paragraph>
          <Space wrap style={{ marginBottom: 12 }}>
            <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy('prompt', promptValue)}>
              {copiedKey === 'prompt' ? '已复制' : '复制提示词'}
            </Button>
            <Button size="small" type="primary" icon={<SaveOutlined />} onClick={promptWorkspace.onSave}>
              保存修改
            </Button>
            <Button size="small" icon={<RedoOutlined />} onClick={promptWorkspace.onReset}>
              恢复默认
            </Button>
          </Space>
          <EditorShell
            value={promptValue}
            language="markdown"
            height={280}
            readOnly={false}
            onChange={promptWorkspace.onChange}
            visibilityToken={visibilityToken}
          />
        </div>
      ),
    })
  } else if (prompt) {
    const previewText = normalizeMultilineText(prompt)
    const previewStats = summarizeText(previewText)
    collapseItems.push({
      key: 'prompt',
      label: (
        <Space size={8}>
          <Typography.Text strong>提示词预览</Typography.Text>
          <StatTags value={`${previewStats.lines} 行`} />
          <StatTags value={`${previewStats.chars} 字符`} />
        </Space>
      ),
      children: (
        <div className="result-workspace-block">
          <Space style={{ marginBottom: 12 }}>
            <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy('prompt', previewText)}>
              {copiedKey === 'prompt' ? '已复制' : '复制'}
            </Button>
          </Space>
          <EditorShell
            value={previewText}
            language="markdown"
            height={240}
            readOnly={true}
            visibilityToken={visibilityToken}
          />
        </div>
      ),
    })
  }

  if (effectivePrompt && promptWorkspace && normalizeMultilineText(effectivePrompt) !== normalizeMultilineText(promptWorkspace.value)) {
    collapseItems.push({
      key: 'effective-prompt',
      label: (
        <Space size={8}>
          <Typography.Text strong>完整发送 Prompt</Typography.Text>
          <StatTags value={`${effectivePromptStats.lines} 行`} />
          <StatTags value={`${effectivePromptStats.chars} 字符`} />
        </Space>
      ),
      children: (
        <div className="result-workspace-block">
          <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
            这是系统最终发送给模型的完整内容，包含固定执行计划、清洗规则和当前可编辑提示词。
          </Typography.Paragraph>
          <Space style={{ marginBottom: 12 }}>
            <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy('effective-prompt', effectivePrompt)}>
              {copiedKey === 'effective-prompt' ? '已复制' : '复制完整 Prompt'}
            </Button>
          </Space>
          <EditorShell
            value={normalizeMultilineText(effectivePrompt)}
            language="markdown"
            height={260}
            readOnly={true}
            visibilityToken={visibilityToken}
          />
        </div>
      ),
    })
  }

  if (normalizedScript) {
    collapseItems.push({
      key: 'script',
      label: (
        <Space size={8} wrap>
          <Typography.Text strong>脚本工作区</Typography.Text>
          <StatTags value={filename} accent="blue" />
          <StatTags value={`${scriptStats.lines} 行`} />
          <StatTags value={`${scriptStats.chars} 字符`} />
          {scriptDirty ? <StatTags value="已编辑" accent="orange" /> : <StatTags value="原始版本" accent="green" />}
          {scriptEditable ? <StatTags value="编辑模式" accent="red" /> : <StatTags value="只读模式" />}
          {model ? <StatTags value={`via ${model}`} accent="green" /> : null}
        </Space>
      ),
      children: (
        <div className="result-workspace-block">
          <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
            支持在这里微调脚本、请求格式化，并将最终版本直接保存到当前项目目录。
          </Typography.Paragraph>
          <Space wrap style={{ marginBottom: 12 }}>
            <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy('script', scriptDraft)}>
              {copiedKey === 'script' ? '已复制' : '复制脚本'}
            </Button>
            <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(scriptDraft, filename)}>
              下载文件
            </Button>
            <Button size="small" icon={<EditOutlined />} type={scriptEditable ? 'primary' : 'default'} onClick={() => setScriptEditable((current) => !current)}>
              {scriptEditable ? '结束编辑' : '进入编辑'}
            </Button>
            <Button size="small" loading={formatBusy} onClick={() => void handleFormatScript()}>
              格式化
            </Button>
            <Button size="small" icon={<PlayCircleOutlined />} loading={sandboxBusy} onClick={() => void handleRunSandbox()}>
              运行沙箱
            </Button>
            <Button size="small" icon={<RedoOutlined />} onClick={() => {
              setScriptDraft(normalizedScript)
              setScriptNoticeTone('info')
              setScriptNotice('已恢复到最近一次生成结果。')
            }}>
              恢复生成结果
            </Button>
            <Button size="small" type="primary" icon={<SaveOutlined />} loading={saveBusy} onClick={() => void handleSaveScript()}>
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
          {scriptNotice ? (
            <Typography.Paragraph type={scriptNoticeTone === 'error' ? 'danger' : scriptNoticeTone === 'warning' ? 'warning' : 'secondary'} style={{ marginBottom: 12 }}>
              {scriptNotice}
            </Typography.Paragraph>
          ) : null}
          <EditorShell
            value={scriptDraft}
            language="python"
            height={360}
            readOnly={!scriptEditable}
            theme="vs-dark"
            wordWrap={scriptWrapMode}
            onChange={setScriptDraft}
            visibilityToken={visibilityToken}
          />
        </div>
      ),
    })
  }

  if (usage || model || filename || outputInfo || checkpoint || runId || jobId || sessionId || pagesProcessed !== null || emittedCount !== null || generationMode) {
    collapseItems.push({
      key: 'meta',
      label: <Typography.Text strong>生成元数据</Typography.Text>,
      children: (
        <Descriptions size="small" column={1} bordered style={{ borderRadius: 8, overflow: 'hidden' }}>
          {generationMode ? <Descriptions.Item label="生成模式">{generationMode}</Descriptions.Item> : null}
          {jobId ? <Descriptions.Item label="作业 ID">{jobId}</Descriptions.Item> : null}
          {runId ? <Descriptions.Item label="运行 ID">{runId}</Descriptions.Item> : null}
          {sessionId ? <Descriptions.Item label="会话 ID">{sessionId}</Descriptions.Item> : null}
          {jobId || runId ? <Descriptions.Item label="续跑状态">{resumed ? '已从 checkpoint 恢复' : '全新运行'}</Descriptions.Item> : null}
          {pagesProcessed !== null ? <Descriptions.Item label="处理页数">{pagesProcessed}</Descriptions.Item> : null}
          {emittedCount !== null ? <Descriptions.Item label="写入记录">{emittedCount}</Descriptions.Item> : null}
          <Descriptions.Item label="模型">{model || '—'}</Descriptions.Item>
          <Descriptions.Item label="文件名">{filename || '—'}</Descriptions.Item>
          <Descriptions.Item label="输出模式">{typeof outputInfo?.output_mode === 'string' ? outputInfo.output_mode : '—'}</Descriptions.Item>
          <Descriptions.Item label="输出目标">{typeof outputInfo?.output_path === 'string' ? outputInfo.output_path : '—'}</Descriptions.Item>
          <Descriptions.Item label="输出表">{typeof outputInfo?.sqlite_table === 'string' ? outputInfo.sqlite_table : '—'}</Descriptions.Item>
          <Descriptions.Item label="Checkpoint 页">{typeof checkpoint?.page_index === 'number' ? checkpoint.page_index : '—'}</Descriptions.Item>
          <Descriptions.Item label="Checkpoint URL">{typeof checkpoint?.current_url === 'string' ? checkpoint.current_url : '—'}</Descriptions.Item>
          <Descriptions.Item label="Checkpoint 状态">{checkpoint?.finished === true ? 'finished' : checkpoint ? 'in_progress' : '—'}</Descriptions.Item>
          <Descriptions.Item label="Prompt Tokens">
            {typeof usage?.prompt_tokens === 'number' ? usage.prompt_tokens : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Completion Tokens">
            {typeof usage?.completion_tokens === 'number' ? usage.completion_tokens : '—'}
          </Descriptions.Item>
        </Descriptions>
      ),
    })
  }

  if (generationTrace.length > 0 || warnings.length > 0 || reviewSummary) {
    collapseItems.push({
      key: 'generation-trace',
      label: <Typography.Text strong>生成轨迹</Typography.Text>,
      children: (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {warnings.length > 0 ? (
            <div>
              <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>Warnings</Typography.Text>
              {warnings.map((warning, index) => (
                <Tag key={`${warning}-${index}`} color="orange" style={{ marginBottom: 6, whiteSpace: 'normal' }}>
                  {warning}
                </Tag>
              ))}
            </div>
          ) : null}
          {generationTrace.length > 0 ? (
            <Descriptions size="small" column={1} bordered style={{ borderRadius: 8, overflow: 'hidden' }}>
              {generationTrace.map((item, index) => {
                const stage = typeof item.stage === 'string' ? item.stage : `stage_${index + 1}`
                const status = typeof item.status === 'string' ? item.status : 'unknown'
                const modelName = typeof item.model === 'string' ? item.model : '—'
                const finishReason = typeof item.finish_reason === 'string' ? item.finish_reason : '—'
                return (
                  <Descriptions.Item key={`${stage}-${index}`} label={`${index + 1}. ${stage}`}>
                    {`${status} | model=${modelName} | finish=${finishReason}`}
                  </Descriptions.Item>
                )
              })}
            </Descriptions>
          ) : null}
          {reviewSummary ? (
            <Descriptions size="small" column={1} bordered style={{ borderRadius: 8, overflow: 'hidden' }}>
              <Descriptions.Item label="Review Summary">
                {typeof reviewSummary.summary === 'string' ? reviewSummary.summary : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="Approved">
                {reviewSummary.approve === true ? 'true' : reviewSummary.approve === false ? 'false' : '—'}
              </Descriptions.Item>
            </Descriptions>
          ) : null}
        </Space>
      ),
    })
  }

  if (activeSandboxResult) {
    const sandboxSuccess = activeSandboxResult.success === true
    const sandboxFailed = activeSandboxResult.success === false
    const sandboxStdout = typeof activeSandboxResult.stdout_tail === 'string' ? activeSandboxResult.stdout_tail : ''
    const sandboxStderr = typeof activeSandboxResult.stderr_tail === 'string' ? activeSandboxResult.stderr_tail : ''
    const sandboxLogPath = typeof activeSandboxResult.log_path === 'string' ? activeSandboxResult.log_path : ''
    const sandboxExitCode = typeof activeSandboxResult.exit_code === 'number' ? String(activeSandboxResult.exit_code) : '—'
    collapseItems.push({
      key: 'sandbox',
      label: (
        <Space size={8}>
          <Typography.Text strong>脚本沙箱</Typography.Text>
          {sandboxSuccess ? <StatTags value="通过" accent="green" /> : null}
          {sandboxFailed ? <StatTags value="失败" accent="red" /> : null}
        </Space>
      ),
      children: (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Descriptions size="small" column={1} bordered style={{ borderRadius: 8, overflow: 'hidden' }}>
            <Descriptions.Item label="Run ID">{typeof activeSandboxResult.run_id === 'string' ? activeSandboxResult.run_id : '—'}</Descriptions.Item>
            <Descriptions.Item label="后端">{typeof activeSandboxResult.backend === 'string' ? activeSandboxResult.backend : '—'}</Descriptions.Item>
            <Descriptions.Item label="退出码">{sandboxExitCode}</Descriptions.Item>
            <Descriptions.Item label="超时">{activeSandboxResult.timed_out === true ? 'true' : 'false'}</Descriptions.Item>
            <Descriptions.Item label="耗时">{typeof activeSandboxResult.duration_seconds === 'number' ? `${activeSandboxResult.duration_seconds}s` : '—'}</Descriptions.Item>
            <Descriptions.Item label="日志文件">{sandboxLogPath || '—'}</Descriptions.Item>
            {typeof activeSandboxResult.error === 'string' && activeSandboxResult.error ? (
              <Descriptions.Item label="错误">{activeSandboxResult.error}</Descriptions.Item>
            ) : null}
          </Descriptions>
          {sandboxStderr ? (
            <div>
              <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>stderr</Typography.Text>
              <pre className="raw-json-pre">{sandboxStderr}</pre>
            </div>
          ) : null}
          {sandboxStdout ? (
            <div>
              <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>stdout</Typography.Text>
              <pre className="raw-json-pre">{sandboxStdout}</pre>
            </div>
          ) : null}
        </Space>
      ),
    })
  }

  if (logs.length > 0) {
    collapseItems.push({
      key: 'logs',
      label: <Typography.Text strong>运行日志（{logs.length} 条）</Typography.Text>,
      children: (
        <Table
          size="small"
          dataSource={logs.map((log, i) => ({ key: i, ...log }))}
          columns={[
            {
              title: '级别',
              dataIndex: 'level',
              width: 80,
              render: (level: string) => (
                <Tag color={LEVEL_COLORS[level] ?? 'default'}>{level ?? 'info'}</Tag>
              ),
            },
            {
              title: '节点',
              dataIndex: 'node_id',
              width: 120,
              render: (id: string) => id ? <Typography.Text code>{id}</Typography.Text> : '—',
            },
            {
              title: '消息',
              dataIndex: 'message',
              render: (msg: string) => <Typography.Text style={{ fontSize: 12 }}>{msg}</Typography.Text>,
            },
          ]}
          pagination={false}
          style={{ borderRadius: 8, overflow: 'hidden' }}
        />
      ),
    })
  }

  if (nodeResults.length > 0) {
    collapseItems.push({
      key: 'node-results',
      label: <Typography.Text strong>节点结果（{nodeResults.length} 个）</Typography.Text>,
      children: (
        <Descriptions size="small" column={1} bordered style={{ borderRadius: 8, overflow: 'hidden' }}>
          {nodeResults.map((nr, i) => (
            <Descriptions.Item
              key={i}
              label={(
                <Space>
                  <Typography.Text code style={{ fontSize: 11 }}>{nr.node_id ?? `node-${i}`}</Typography.Text>
                  {nr.success ? (
                    <CheckCircleFilled style={{ color: '#16a34a' }} />
                  ) : (
                    <CloseCircleFilled style={{ color: '#dc2626' }} />
                  )}
                </Space>
              )}
            >
              {nr.success === false
                ? <Typography.Text type="danger" style={{ fontSize: 12 }}>{nr.error ?? '执行失败'}</Typography.Text>
                : <Typography.Text type="secondary" style={{ fontSize: 12 }}>执行成功</Typography.Text>}
            </Descriptions.Item>
          ))}
        </Descriptions>
      ),
    })
  }

  if (records.length > 0) {
    collapseItems.push({
      key: 'records',
      label: <Typography.Text strong>样例记录（{records.length} 条）</Typography.Text>,
      children: (
        <Table
          size="small"
          dataSource={records.map((r, i) => ({ key: i, ...(typeof r === 'object' && r !== null ? r : {}) }))}
          columns={
            records[0] && typeof records[0] === 'object'
              ? Object.keys(records[0] as Record<string, unknown>).slice(0, 6).map((key) => ({
                title: key,
                dataIndex: key,
                width: 160,
                ellipsis: true,
                render: (val: unknown) => (
                  <Typography.Text style={{ fontSize: 12 }}>{String(val ?? '—')}</Typography.Text>
                ),
              }))
              : [{ title: 'value', dataIndex: 'value', render: (val: unknown) => String(val ?? '—') }]
          }
          pagination={{ pageSize: 5 }}
          style={{ borderRadius: 8, overflow: 'hidden' }}
        />
      ),
    })
  }

  if (!hasPayload) return null

  const itemOrder: Record<string, number> = {
    script: 0,
    'prompt-workspace': 1,
    prompt: 1,
    'effective-prompt': 2,
    records: 3,
    sandbox: 4,
    logs: 4,
    'node-results': 5,
    meta: 6,
    'generation-trace': 7,
  }
  const prioritizedCollapseItems = [...collapseItems].sort((left, right) => (
    (itemOrder[String(left.key)] ?? 50) - (itemOrder[String(right.key)] ?? 50)
  ))
  const defaultActiveKey = normalizedScript
    ? ['script']
    : prioritizedCollapseItems.map((item) => String(item.key))

  const viewFilterKeys: Record<Exclude<ResultDetailsView, 'all'>, string[]> = {
    script: ['script', 'sandbox', 'meta'],
    prompt: ['prompt-workspace', 'prompt', 'effective-prompt'],
    records: ['records', 'node-results'],
    logs: ['sandbox', 'logs', 'node-results', 'generation-trace'],
    diagnostics: [],
  }
  const filteredCollapseItems = view === 'all'
    ? prioritizedCollapseItems
    : prioritizedCollapseItems.filter((item) => viewFilterKeys[view].includes(String(item.key)))
  const filteredDefaultActiveKey = defaultActiveKey.filter((key) => (
    filteredCollapseItems.some((item) => String(item.key) === key)
  ))
  const finalDefaultActiveKey = filteredDefaultActiveKey.length > 0
    ? filteredDefaultActiveKey
    : filteredCollapseItems.map((item) => String(item.key))
  const shouldRenderStructuredBlocks = view !== 'diagnostics' && filteredCollapseItems.length > 0
  const shouldRenderRawJson = view === 'all' || view === 'diagnostics'

  const isSpecificView = view !== 'all' && view !== 'diagnostics'

  if (focusMode && view === 'script' && normalizedScript) {
    return (
      <div className="result-details-root result-details-focus">
        <div className="script-focus-header">
          <div className="script-focus-meta">
            <StatTags value={filename} accent="blue" />
            <StatTags value={`${scriptStats.lines} 行`} />
            <StatTags value={`${scriptStats.chars} 字符`} />
            {scriptDirty ? <StatTags value="已编辑" accent="orange" /> : <StatTags value="原始版本" accent="green" />}
            {scriptEditable ? <StatTags value="编辑模式" accent="red" /> : <StatTags value="只读模式" />}
            {model ? <StatTags value={`via ${model}`} accent="green" /> : null}
          </div>
          <Space wrap size={8} className="script-focus-actions">
            <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy('script', scriptDraft)}>
              {copiedKey === 'script' ? '已复制' : '复制'}
            </Button>
            <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(scriptDraft, filename)}>
              下载
            </Button>
            <Button size="small" icon={<EditOutlined />} type={scriptEditable ? 'primary' : 'default'} onClick={() => setScriptEditable((current) => !current)}>
              {scriptEditable ? '结束编辑' : '编辑'}
            </Button>
            <Button size="small" loading={formatBusy} onClick={() => void handleFormatScript()}>
              格式化
            </Button>
            <Button size="small" icon={<PlayCircleOutlined />} loading={sandboxBusy} onClick={() => void handleRunSandbox()}>
              运行沙箱
            </Button>
            <Button size="small" icon={<RedoOutlined />} onClick={() => {
              setScriptDraft(normalizedScript)
              setScriptNoticeTone('info')
              setScriptNotice('已恢复到最近一次生成结果。')
            }}>
              恢复
            </Button>
            <Button size="small" type="primary" icon={<SaveOutlined />} loading={saveBusy} onClick={() => void handleSaveScript()}>
              保存
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
        </div>

        <Collapse
          size="small"
          className="script-focus-collapse"
          items={[
            {
              key: 'save-options',
              label: <Typography.Text type="secondary">保存与元数据</Typography.Text>,
              children: (
                <div className="script-focus-secondary">
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
                  {(usage || model || filename || outputInfo || checkpoint || runId || jobId || sessionId || pagesProcessed !== null || emittedCount !== null || generationMode) ? (
                    <Descriptions size="small" column={2} bordered style={{ borderRadius: 8, overflow: 'hidden' }}>
                      {generationMode ? <Descriptions.Item label="生成模式">{generationMode}</Descriptions.Item> : null}
                      {model ? <Descriptions.Item label="模型">{model}</Descriptions.Item> : null}
                      <Descriptions.Item label="文件名">{filename || '—'}</Descriptions.Item>
                      {jobId ? <Descriptions.Item label="作业 ID">{jobId}</Descriptions.Item> : null}
                      {runId ? <Descriptions.Item label="运行 ID">{runId}</Descriptions.Item> : null}
                      {pagesProcessed !== null ? <Descriptions.Item label="处理页数">{pagesProcessed}</Descriptions.Item> : null}
                      {emittedCount !== null ? <Descriptions.Item label="写入记录">{emittedCount}</Descriptions.Item> : null}
                    </Descriptions>
                  ) : null}
                </div>
              ),
            },
          ]}
        />

        {scriptNotice ? (
          <Typography.Paragraph type={scriptNoticeTone === 'error' ? 'danger' : scriptNoticeTone === 'warning' ? 'warning' : 'secondary'} style={{ margin: '0 0 10px' }}>
            {scriptNotice}
          </Typography.Paragraph>
        ) : null}

        <div className="script-focus-editor">
          <EditorShell
            value={scriptDraft}
            language="python"
            height="100%"
            readOnly={!scriptEditable}
            theme="vs-dark"
            wordWrap={scriptWrapMode}
            onChange={setScriptDraft}
            visibilityToken={visibilityToken}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="result-details-root">
      {shouldRenderStructuredBlocks ? (
        isSpecificView ? (
          <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            {filteredCollapseItems.map((item) => (
              <div key={item.key} className="result-specific-block">
                <div className="result-block-header" style={{ marginBottom: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div className="result-block-title">{item.label}</div>
                  <div className="result-block-extra">{item.extra}</div>
                </div>
                <div className="result-block-content">
                  {item.children}
                </div>
              </div>
            ))}
          </Space>
        ) : (
          <Collapse
            items={filteredCollapseItems}
            defaultActiveKey={finalDefaultActiveKey}
            size="small"
            className="result-primary-collapse"
            style={{ borderRadius: 10, overflow: 'hidden' }}
          />
        )
      ) : null}

      {shouldRenderRawJson ? (
        <Collapse
          className="raw-json-collapse"
          size="small"
          defaultActiveKey={view === 'diagnostics' ? ['raw-json'] : []}
          items={[
            {
              key: 'raw-json',
              label: <Typography.Text type="secondary">原始 JSON 响应（调试用）</Typography.Text>,
              extra: (
                <Button size="small" icon={<CopyOutlined />} onClick={(event) => {
                  event.stopPropagation()
                  void handleCopy('raw-json', JSON.stringify(payload, null, 2))
                }}>
                  {copiedKey === 'raw-json' ? '已复制' : '复制 JSON'}
                </Button>
              ),
              children: (
                <pre className="raw-json-pre">
                  {JSON.stringify(payload, null, 2)}
                </pre>
              ),
            },
          ]}
        />
      ) : null}

      {view !== 'diagnostics' && !shouldRenderStructuredBlocks ? (
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
          当前暂无该类型输出，请先触发对应动作。
        </Typography.Paragraph>
      ) : null}
    </div>
  )
}
