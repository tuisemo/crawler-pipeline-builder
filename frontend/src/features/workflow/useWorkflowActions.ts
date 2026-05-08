import { useState } from 'react'
import { getErrorMessage } from './workflowState'
import type { ScriptGenerationMode, WorkflowGraph } from './workflowContracts'
import { postWorkflowAction, type WorkflowActionPath } from '../../services/workflowApi'
import type { WorkbenchAction } from '../../app/components/WorkbenchToolbar'

type ResultTone = 'idle' | 'loading' | 'success' | 'validation-error' | 'runtime-error'

export type ResultState = {
  tone: ResultTone
  title: string
  message: string
  payload?: unknown
  action?: WorkbenchAction
  graphKey?: string
}

type UseWorkflowActionsArgs = {
  canonicalGraph: WorkflowGraph
  graphKey: string
  getPromptOverride: (graphKey: string) => string
  generationMode: ScriptGenerationMode
}

const actionLabels: Record<WorkbenchAction, string> = {
  validate: '校验 DSL',
  prompt: '生成提示词',
  'compile-plan': '编译执行计划',
  'generate-skeleton': '生成代码骨架',
  'generate-script': '合成采集脚本',
  'auto-layout': '自动布局',
}

function classifyResult(action: WorkbenchAction, responseOk: boolean, payload: unknown): ResultTone {
  const record = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {}
  if (responseOk && record.success !== false) return 'success'
  if (['validate', 'prompt', 'compile-plan'].includes(action)) return 'validation-error'
  return 'runtime-error'
}

function resolveResultMessage(action: WorkbenchAction, responseOk: boolean, payload: unknown, tone: ResultTone): string {
  if (tone === 'success') {
    return '操作已成功完成。可以在下方查看结构化输出或生成的工件。'
  }

  const parsedError = getErrorMessage(payload)
  if (parsedError && parsedError !== 'Workflow schema validation failed.') {
    return parsedError
  }

  if (!responseOk) {
    return `请求失败：${actionLabels[action]}。请检查网络连接或后端服务状态。`
  }
  return `${actionLabels[action]} 执行失败。请查看下方的详细诊断信息。`
}

export function useWorkflowActions({ canonicalGraph, graphKey, getPromptOverride, generationMode }: UseWorkflowActionsArgs) {
  const [resultState, setResultState] = useState<ResultState>({
    tone: 'idle',
    title: '就绪',
    message: '从工具栏选择一个动作（如：合成脚本）来在此处查看 AI 生成的结果。',
  })
  const [runningAction, setRunningAction] = useState<WorkbenchAction | null>(null)

  async function runWorkflowAction(action: WorkbenchAction) {
    if (action === 'auto-layout') return // Handled in App.tsx

    const previousPayload = resultState.payload
    setRunningAction(action)
    setResultState({
      tone: 'loading',
      title: `${actionLabels[action]} 运行中`,
      message: previousPayload
        ? `正在加载新结果；旧结果保留在下方。${action === 'generate-script' ? ` 生成模式：${generationMode}。` : ''}`
        : action === 'generate-script'
          ? `正在合成采集脚本（模式：${generationMode}）...`
          : `正在执行 ${actionLabels[action]}...`,
      payload: previousPayload,
      action,
      graphKey,
    })

    try {
      const promptOverride = action === 'generate-script' ? getPromptOverride(graphKey) : ''
      const requestBody = action === 'generate-script'
        ? { graph: canonicalGraph, prompt_override: promptOverride || undefined, generation_mode: generationMode }
        : { graph: canonicalGraph }

      const pathMap: Record<Exclude<WorkbenchAction, 'auto-layout'>, WorkflowActionPath> = {
        validate: '/api/workflows/validate',
        prompt: '/api/workflows/to-prompt',
        'compile-plan': '/api/workflows/compile-plan',
        'generate-skeleton': '/api/workflows/generate-skeleton',
        'generate-script': '/api/workflows/generate-crawler',
      }

      const path = pathMap[action as Exclude<WorkbenchAction, 'auto-layout'>]

      const { response, payload } = await postWorkflowAction(path, requestBody)
      const tone = classifyResult(action, response.ok, payload)
      setResultState({
        tone,
        title: actionLabels[action],
        message: resolveResultMessage(action, response.ok, payload, tone),
        payload,
        action,
        graphKey,
      })
    } catch (error) {
      setResultState({
        tone: 'runtime-error',
        title: `${actionLabels[action]} 失败`,
        message: error instanceof Error ? error.message : '执行过程中发生未知错误。',
        payload: previousPayload,
        action,
        graphKey,
      })
    } finally {
      setRunningAction(null)
    }
  }

  return {
    resultState,
    runningAction,
    runWorkflowAction,
  }
}
