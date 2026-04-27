import { Alert, Card, Result, Spin, Tabs, Tag, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { ResultDetails } from './ResultDetails'
import type { PromptWorkspace, ResultDetailsView } from './ResultDetails'
import type { WorkbenchAction } from './WorkbenchToolbar'

type ResultTone = 'idle' | 'loading' | 'success' | 'validation-error' | 'runtime-error' | 'partial' | 'session-expired'

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
  promptWorkspace: PromptWorkspace | null
  selectedNodeId: string
  visibilityToken?: number
}

const toneConfig: Record<ResultTone, { alertType: 'success' | 'info' | 'warning' | 'error' | null; resultStatus?: 'success' | 'info' | 'warning' | 'error' | '403' | '404' | '500' | 403 | 404 | 500; label: string }> = {
  idle:          { alertType: null, label: '待执行' },
  loading:       { alertType: 'info', label: '运行中' },
  success:       { alertType: 'success', resultStatus: 'success', label: '已完成' },
  'validation-error': { alertType: 'warning', resultStatus: 'warning', label: '需修正' },
  'runtime-error':     { alertType: 'error', resultStatus: 'error', label: '运行失败' },
  partial:       { alertType: 'info', resultStatus: 'warning', label: '部分完成' },
  'session-expired':   { alertType: 'error', resultStatus: '403', label: '会话失效' },
}

type ArtifactTabKey = Exclude<ResultDetailsView, 'all'>

const actionLabels: Partial<Record<WorkbenchAction, string>> = {
  validate: '校验 DSL',
  prompt: '预览 Prompt',
  'compile-plan': '编排计划',
  'generate-skeleton': '生成骨架',
  'test-node': '节点测试',
  'test-subflow': '子流测试',
  'generate-script': '生成爬虫脚本',
  'auto-layout': '优化布局',
}

function resolvePreferredArtifactTab(
  action: WorkbenchAction | undefined,
  availability: Record<ArtifactTabKey, boolean>,
): ArtifactTabKey {
  if (action === 'generate-script' || action === 'generate-skeleton') {
    if (availability.script) return 'script'
    if (availability.diagnostics) return 'diagnostics'
  }
  if (action === 'prompt') {
    if (availability.prompt) return 'prompt'
    if (availability.diagnostics) return 'diagnostics'
  }
  if (action === 'test-node' || action === 'test-subflow') {
    if (availability.records) return 'records'
    if (availability.logs) return 'logs'
    if (availability.diagnostics) return 'diagnostics'
  }
  if (action === 'validate' || action === 'compile-plan') {
    if (availability.diagnostics) return 'diagnostics'
  }
  return (Object.entries(availability).find(([, enabled]) => enabled)?.[0] as ArtifactTabKey | undefined) ?? 'diagnostics'
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
  const artifactAvailability = useMemo<Record<ArtifactTabKey, boolean>>(() => ({
    script: hasScriptPayload,
    prompt: hasPromptPayload,
    records: hasRecordsPayload,
    logs: hasLogsPayload,
    diagnostics: hasPayload,
  }), [hasLogsPayload, hasPayload, hasPromptPayload, hasRecordsPayload, hasScriptPayload])
  const [activeArtifactTab, setActiveArtifactTab] = useState<ArtifactTabKey>(() => (
    resolvePreferredArtifactTab(resultState.action, artifactAvailability)
  ))
  const [detailVisibilityToken, setDetailVisibilityToken] = useState(0)

  useEffect(() => {
    setActiveArtifactTab(resolvePreferredArtifactTab(resultState.action, artifactAvailability))
  }, [artifactAvailability, resultState.action, resultState.payload, resultState.tone])

  useEffect(() => {
    setDetailVisibilityToken((current) => current + 1)
  }, [activeArtifactTab, visibilityToken])

  const artifactTabItems: Array<{ key: ArtifactTabKey; label: string; disabled: boolean }> = [
    { key: 'script', label: '脚本', disabled: !artifactAvailability.script },
    { key: 'prompt', label: '提示词', disabled: !artifactAvailability.prompt },
    { key: 'records', label: '记录', disabled: !artifactAvailability.records },
    { key: 'logs', label: '日志', disabled: !artifactAvailability.logs },
    { key: 'diagnostics', label: '诊断', disabled: !artifactAvailability.diagnostics },
  ]
  const enabledArtifactCount = artifactTabItems.filter((item) => !item.disabled).length
  const actionLabel = resultState.action ? actionLabels[resultState.action] ?? resultState.action : '等待操作'
  const scriptFocusMode = (
    activeArtifactTab === 'script'
    && hasScriptPayload
    && (resultState.action === 'generate-skeleton' || resultState.action === 'generate-script')
  )

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
        <>
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
            destroyInactiveTabPane={false}
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
                  focusMode={scriptFocusMode && item.key === 'script'}
                  visibilityToken={detailVisibilityToken}
                />
              ),
            }))}
          />
        </>
      )}
    </Card>
  )
}

export type { ResultState, ResultTone }
