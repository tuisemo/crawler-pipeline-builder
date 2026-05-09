import { Spin, Tabs, Typography } from 'antd'
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
  visibilityToken?: number
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
  resultState: ResultState
  promptWorkspace: PromptWorkspaceProps | null
  visibilityToken?: number
  artifactAvailability: ArtifactAvailability
  defaultArtifactTab: ArtifactTabKey
}

function ArtifactTabsView({
  resultState,
  promptWorkspace,
  visibilityToken,
  artifactAvailability,
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


  return (
    <>

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

export function ResultsPanel({ resultState, runningAction, promptWorkspace, visibilityToken }: ResultsPanelProps) {
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
    <div className="results-area-minimal" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {resultState.tone === 'idle' && (
        <div style={{ padding: '40px 0', textAlign: 'center' }}>
          <Typography.Text type="secondary">等待执行。请配置工作流节点后运行。</Typography.Text>
        </div>
      )}

      {resultState.tone === 'loading' && (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin size="default" />
          <Typography.Paragraph style={{ margin: '12px 0 0', color: 'var(--sd-color-text-secondary)', fontWeight: 500, fontSize: 13 }}>
            {runningAction ? `正在执行：${runningAction}` : '请求处理中…'}
          </Typography.Paragraph>
        </div>
      )}

      {(resultState.tone !== 'idle' && resultState.tone !== 'loading') && (
        <ArtifactTabsView
          key={artifactSessionKey}
          resultState={resultState}
          promptWorkspace={promptWorkspace}
          visibilityToken={visibilityToken}
          artifactAvailability={artifactAvailability}
          defaultArtifactTab={defaultArtifactTab}
        />
      )}
    </div>
  )
}

export type { ResultState, ResultTone }
