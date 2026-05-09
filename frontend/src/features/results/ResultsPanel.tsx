import { Alert, Card, Result, Spin, Tabs, Tag, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { ResultDetails } from './ResultDetails'
import type { PromptWorkspaceProps } from './components/PromptWorkspace'
import type { ResultDetailsView } from './ResultDetails'
import type { WorkbenchAction } from '../../app/components/WorkbenchToolbar'

type ResultTone = 'idle' | 'loading' | 'success' | 'validation-error' | 'runtime-error'

type ResultState = {
  tone: ResultTone
  title: string
  message: string
  payload?: unknown
  action?: WorkbenchAction
}

type ResultsPanelProps = {
  resultState: ResultState
  runningAction: string | null
  promptWorkspace: PromptWorkspaceProps | null
  selectedNodeId: string
  visibilityToken?: number
}

const toneConfig: Record<ResultTone, { alertType: 'success' | 'info' | 'warning' | 'error' | null; resultStatus?: 'success' | 'info' | 'warning' | 'error' | '403' | '404' | '500' | 403 | 404 | 500; label: string }> = {
  idle:          { alertType: null, label: '待执行' },
  loading:       { alertType: 'info', label: '运行中' },
  success:       { alertType: 'success', resultStatus: 'success', label: '已完成' },
  'validation-error': { alertType: 'warning', resultStatus: 'warning', label: '需修正' },
  'runtime-error':     { alertType: 'error', resultStatus: 'error', label: '运行失败' },
}

type ArtifactTabKey = Exclude<ResultDetailsView, 'all'>
type ArtifactAvailability = Record<ArtifactTabKey, boolean>
const ARTIFACT_TAB_VISIBILITY_INDEX: Record<ArtifactTabKey, number> = {
  script: 1,
  prompt: 2,
  records: 3,
  logs: 4,
  diagnostics: 5,
}

const actionLabels: Partial<Record<WorkbenchAction, string>> = {
  validate: '校验 DSL',
  prompt: '预览 Prompt',
  'compile-plan': '编排计划',
  'generate-skeleton': '生成骨架',
  'generate-script': '生成爬虫脚本',
  'auto-layout': '优化布局',
}

function buildPayloadSignature(value: unknown): string {
  if (typeof value === 'string') {
    return `${value.length}:${value.slice(0, 80)}:${value.slice(-80)}`
  }
  if (Array.isArray(value)) {
    return `array:${value.length}:${JSON.stringify(value.slice(0, 2))}`
  }
  if (value && typeof value === 'object') {
    const json = JSON.stringify(value)
    return `${json.length}:${json.slice(0, 120)}:${json.slice(-120)}`
  }
  return String(value ?? '')
}

function resolvePreferredArtifactTab(
  action: WorkbenchAction | undefined,
  availability: ArtifactAvailability,
): ArtifactTabKey {
  if (action === 'generate-script' || action === 'generate-skeleton') {
    if (availability.script) return 'script'
    if (availability.diagnostics) return 'diagnostics'
  }
  if (action === 'prompt') {
    if (availability.prompt) return 'prompt'
    if (availability.diagnostics) return 'diagnostics'
  }
  if (action === 'validate' || action === 'compile-plan') {
    if (availability.diagnostics) return 'diagnostics'
  }
  return (Object.entries(availability).find(([, enabled]) => enabled)?.[0] as ArtifactTabKey | undefined) ?? 'diagnostics'
}

type ArtifactTabsViewProps = {
  cfg: typeof toneConfig[ResultTone]
  resultState: ResultState
  promptWorkspace: PromptWorkspaceProps | null
  selectedNodeId: string
  visibilityToken?: number
  artifactAvailability: ArtifactAvailability
  enabledArtifactCount: number
  actionLabel: string
  hasScriptPayload: boolean
  defaultArtifactTab: ArtifactTabKey
}

function ArtifactTabsView({
  cfg,
  resultState,
  promptWorkspace,
  selectedNodeId,
  visibilityToken,
  artifactAvailability,
  enabledArtifactCount,
  actionLabel,
  hasScriptPayload,
  defaultArtifactTab,
}: ArtifactTabsViewProps) {
  const [activeArtifactTab, setActiveArtifactTab] = useState<ArtifactTabKey>(defaultArtifactTab)
  const detailVisibilityToken = (visibilityToken ?? 0) * 10 + ARTIFACT_TAB_VISIBILITY_INDEX[activeArtifactTab]
  const artifactTabItems: Array<{ key: ArtifactTabKey; label: string; disabled: boolean }> = [
    { key: 'script', label: '脚本', disabled: !artifactAvailability.script },
    { key: 'prompt', label: '提示词', disabled: !artifactAvailability.prompt },
    { key: 'records', label: '记录', disabled: !artifactAvailability.records },
    { key: 'logs', label: '日志', disabled: !artifactAvailability.logs },
    { key: 'diagnostics', label: '诊断', disabled: !artifactAvailability.diagnostics },
  ]
  const scriptFocusMode = (
    activeArtifactTab === 'script'
    && hasScriptPayload
    && (resultState.action === 'generate-skeleton' || resultState.action === 'generate-script')
  )

  return (
    <>
      {!scriptFocusMode ? (
        <div className="workspace-context-strip">
          <Typography.Text className="workspace-context-chip">
            当前节点 {selectedNodeId || '未选择'}
          </Typography.Text>
          <Typography.Text className="workspace-context-chip">
            当前动作 {actionLabel}
          </Typography.Text>
          <Typography.Text className="workspace-context-chip">
            可查看 {enabledArtifactCount} 类结果
          </Typography.Text>
        </div>
      ) : (
        <div className="workspace-context-strip workspace-context-strip-compact">
          <Typography.Text className="workspace-context-chip">
            {actionLabel}
          </Typography.Text>
          <Typography.Text className="workspace-context-chip">
            当前节点 {selectedNodeId || '未选择'}
          </Typography.Text>
          <Typography.Text className="workspace-context-chip">
            脚本工作区
          </Typography.Text>
        </div>
      )}

      {cfg.alertType && !(cfg.alertType === 'success' && hasScriptPayload) && !scriptFocusMode && (
        <Alert
          className="results-status-alert"
          type={cfg.alertType}
          title={resultState.title}
          description={resultState.message}
          showIcon
          style={{ marginBottom: 12, borderRadius: 'var(--sd-radius-lg)', border: 'none', boxShadow: 'var(--sd-shadow-border)' }}
        />
      )}
      {cfg.alertType === 'success' && hasScriptPayload && !scriptFocusMode && (
        <div className="result-compact-status">
          <Typography.Text strong>{resultState.title}</Typography.Text>
          <Tag color="green">success</Tag>
          <Typography.Text type="secondary">{resultState.message}</Typography.Text>
        </div>
      )}
      <Tabs
        className="result-artifact-tabs"
        activeKey={activeArtifactTab}
        onChange={(nextKey) => setActiveArtifactTab(nextKey as ArtifactTabKey)}
        destroyOnHidden={false}
        animated={false}
        items={artifactTabItems.map((item) => ({
          key: item.key,
          label: item.label,
          disabled: item.disabled,
          children: (
            <ResultDetails
              payload={resultState.payload}
              promptWorkspace={promptWorkspace}
              view={item.key}
              visibilityToken={detailVisibilityToken}
            />
          ),
        }))}
      />
    </>
  )
}

export function ResultsPanel({ resultState, runningAction, promptWorkspace, selectedNodeId, visibilityToken }: ResultsPanelProps) {
  const cfg = toneConfig[resultState.tone]
  const payloadRecord = resultState.payload && typeof resultState.payload === 'object'
    ? resultState.payload as Record<string, unknown>
    : {}
  const hasScriptPayload = typeof payloadRecord.script === 'string' && payloadRecord.script.trim().length > 0
  const hasPromptPayload = (
    typeof payloadRecord.prompt === 'string' && payloadRecord.prompt.trim().length > 0
  ) || (
    typeof promptWorkspace?.value === 'string' && promptWorkspace.value.trim().length > 0
  )
  const hasRecordsPayload = Array.isArray(payloadRecord.records) && payloadRecord.records.length > 0
    || Array.isArray(payloadRecord.records_sample) && payloadRecord.records_sample.length > 0
  const hasLogsPayload = (
    Array.isArray(payloadRecord.logs) && payloadRecord.logs.length > 0
  ) || (
    Array.isArray(payloadRecord.node_results) && payloadRecord.node_results.length > 0
  )
  const hasPayload = Boolean(resultState.payload)
  const artifactAvailability = useMemo<ArtifactAvailability>(() => ({
    script: hasScriptPayload,
    prompt: hasPromptPayload,
    records: hasRecordsPayload,
    logs: hasLogsPayload,
    diagnostics: hasPayload,
  }), [hasLogsPayload, hasPayload, hasPromptPayload, hasRecordsPayload, hasScriptPayload])
  const defaultArtifactTab = useMemo(
    () => resolvePreferredArtifactTab(resultState.action, artifactAvailability),
    [artifactAvailability, resultState.action],
  )
  const artifactTabItems: Array<{ key: ArtifactTabKey; label: string; disabled: boolean }> = [
    { key: 'script', label: '脚本', disabled: !artifactAvailability.script },
    { key: 'prompt', label: '提示词', disabled: !artifactAvailability.prompt },
    { key: 'records', label: '记录', disabled: !artifactAvailability.records },
    { key: 'logs', label: '日志', disabled: !artifactAvailability.logs },
    { key: 'diagnostics', label: '诊断', disabled: !artifactAvailability.diagnostics },
  ]
  const enabledArtifactCount = artifactTabItems.filter((item) => !item.disabled).length
  const actionLabel = resultState.action ? actionLabels[resultState.action] ?? resultState.action : '等待操作'
  const artifactSessionKey = [
    resultState.action ?? 'idle',
    resultState.tone,
    defaultArtifactTab,
    `script:${buildPayloadSignature(payloadRecord.script)}`,
    `detail-batch:${buildPayloadSignature(payloadRecord['detail-batch-runner'])}`,
    `prompt:${buildPayloadSignature(payloadRecord.prompt)}`,
    `records:${buildPayloadSignature(payloadRecord.records ?? payloadRecord.records_sample)}`,
    `logs:${buildPayloadSignature(payloadRecord.logs ?? payloadRecord.node_results)}`,
    hasPayload ? 'payload:1' : 'payload:0',
  ].join('|')

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Typography.Text strong style={{ fontSize: 16, color: 'var(--sd-color-ink)', letterSpacing: '-0.32px' }}>执行结果</Typography.Text>
          <Tag
            color={cfg.alertType === 'success' ? 'green' : cfg.alertType === 'error' ? 'red' : cfg.alertType === 'warning' ? 'orange' : cfg.alertType === 'info' ? 'blue' : 'default'}
            style={{ margin: 0, border: 'none', boxShadow: 'var(--sd-shadow-border-light)' }}
          >
            {cfg.label}
          </Tag>
        </div>
      }
      extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>实时工作区</Typography.Text>}
      styles={{ body: { padding: '12px 16px', flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 } }}
      className="results-area ant-results-card"
      variant="outlined"
    >
      {resultState.tone === 'idle' && (
        <Result
          status="info"
          title="等待执行"
          subTitle="请配置工作流节点后，点击顶部操作按钮运行。"
          style={{ padding: '24px 0' }}
        />
      )}

      {resultState.tone === 'loading' && (
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin size="large" />
          <Typography.Paragraph style={{ margin: '16px 0 0', color: 'var(--sd-color-text-secondary)', fontWeight: 500 }}>
            {runningAction ? `正在执行：${runningAction}` : '请求处理中，请稍候…'}
          </Typography.Paragraph>
          <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: '8px 0 0' }}>
            浏览器型任务会串行运行以保证状态一致。
          </Typography.Paragraph>
        </div>
      )}

      {(resultState.tone !== 'idle' && resultState.tone !== 'loading') && (
        <ArtifactTabsView
          key={artifactSessionKey}
          cfg={cfg}
          resultState={resultState}
          promptWorkspace={promptWorkspace}
          selectedNodeId={selectedNodeId}
          visibilityToken={visibilityToken}
          artifactAvailability={artifactAvailability}
          enabledArtifactCount={enabledArtifactCount}
          actionLabel={actionLabel}
          hasScriptPayload={hasScriptPayload}
          defaultArtifactTab={defaultArtifactTab}
        />
      )}
    </Card>
  )
}

export type { ResultState, ResultTone }
