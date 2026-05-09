type ExtensionAction =
  | 'ping'
  | 'autoDetect'
  | 'testSelector'
  | 'highlightSelector'
  | 'extractHtml'
  | 'extractPaginationContext'

type ExtensionErrorCode =
  | 'extension_not_installed'
  | 'extension_unreachable'
  | 'no_active_tab'
  | 'script_execution_failed'
  | 'invalid_selector'
  | 'timeout'

type ExtensionResponse<T> =
  | { ok: true; data: T }
  | { ok: false; error: { code: ExtensionErrorCode; message: string } }

type PageBridgeRequest = {
  source: 'BROWSER_BRIDGE_PAGE'
  requestId: string
  action: ExtensionAction
  payload?: Record<string, unknown>
}

type PageBridgeResponse = {
  source: 'BROWSER_BRIDGE_EXTENSION'
  requestId: string
  response: ExtensionResponse<unknown>
}

export type ExtensionStatus = {
  installed: boolean
  ready: boolean
  version: string
  managedTabId?: number
  managedTargetUrl?: string
}

export type ExtensionDetectedField = {
  name: string
  selector: string
  type: string
  confidence?: number
}

export type AutoDetectResult = {
  itemSelector: string
  paginationSelector: string
  paginationStrategy: string
  fields: ExtensionDetectedField[]
  htmlFragment: string
  confidence?: number
}

export type SelectorTestResult = {
  matchCount: number
  highlightedCount: number
  clearAfterMs: number
  elements: Array<{
    tagName?: string
    text?: string
    className?: string
  }>
}

export type ExtractHtmlResult = {
  htmlFragment: string
  itemCount: number
  truncated: boolean
  originalSize: number
  truncatedSize: number
}

export type PaginationContextResult = {
  htmlFragment: string
  paginationComponentHtml: string
  prunedBodyHtml: string
}

class ExtensionBridgeError extends Error {
  code: ExtensionErrorCode

  constructor(code: ExtensionErrorCode, message: string) {
    super(message)
    this.name = 'ExtensionBridgeError'
    this.code = code
  }
}

const UNAVAILABLE: ExtensionStatus = {
  installed: false,
  ready: false,
  version: '',
}

function canUsePageBridge(): boolean {
  return typeof window !== 'undefined' && typeof window.postMessage === 'function'
}

function normalizeBridgeError(code: ExtensionErrorCode, fallback: string): ExtensionBridgeError {
  const messageByCode: Record<ExtensionErrorCode, string> = {
    extension_not_installed: '未检测到 Browser Bridge 扩展，请先在 Chrome/Chromium 中加载本地扩展。',
    extension_unreachable: 'Browser Bridge 扩展暂时不可用，请刷新扩展或重新打开当前工作台页面。',
    no_active_tab: '未找到匹配的目标标签页。请检查：\n1. open_page 节点的目标 URL 是否正确\n2. 目标页面是否已在浏览器中打开',
    script_execution_failed: fallback || '扩展脚本执行失败，请检查当前页面是否已完成加载，或尝试刷新页面。',
    invalid_selector: fallback || '选择器无效，请检查语法后重试。',
    timeout: '扩展响应超时。这通常是因为目标页面加载过慢或扩展无法在该页面上运行。请尝试刷新页面。',
  }
  return new ExtensionBridgeError(code, messageByCode[code])
}

function isBridgeResponse(value: unknown): value is PageBridgeResponse {
  return Boolean(value)
    && typeof value === 'object'
    && (value as PageBridgeResponse).source === 'BROWSER_BRIDGE_EXTENSION'
    && typeof (value as PageBridgeResponse).requestId === 'string'
    && typeof (value as PageBridgeResponse).response === 'object'
}

function sendExtensionRequest<T>(
  action: ExtensionAction,
  payload?: Record<string, unknown>,
  timeoutMs = 2500,
): Promise<T> {
  if (!canUsePageBridge()) {
    return Promise.reject(normalizeBridgeError('extension_not_installed', ''))
  }

  return new Promise((resolve, reject) => {
    const requestId = `bridge-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    const timer = setTimeout(() => {
      window.removeEventListener('message', onMessage)
      reject(normalizeBridgeError('timeout', ''))
    }, timeoutMs)

    const onMessage = (event: MessageEvent<unknown>) => {
      if (event.source !== window || !isBridgeResponse(event.data) || event.data.requestId !== requestId) {
        return
      }

      clearTimeout(timer)
      window.removeEventListener('message', onMessage)

      const { response } = event.data
      if (!response.ok) {
        reject(normalizeBridgeError(response.error.code, response.error.message))
        return
      }
      resolve(response.data as T)
    }

    window.addEventListener('message', onMessage)

    const request: PageBridgeRequest = {
      source: 'BROWSER_BRIDGE_PAGE',
      requestId,
      action,
      payload,
    }

    try {
      window.postMessage(request, window.location.origin)
    } catch (error) {
      clearTimeout(timer)
      window.removeEventListener('message', onMessage)
      reject(normalizeBridgeError('extension_unreachable', error instanceof Error ? error.message : ''))
    }
  })
}

export async function detectExtension(timeoutMs = 1500): Promise<ExtensionStatus> {
  try {
    const data = await sendExtensionRequest<{ ready: boolean; version?: string; managedTabId?: number; managedTargetUrl?: string }>('ping', undefined, timeoutMs)
    return {
      installed: true,
      ready: data.ready === true,
      version: typeof data.version === 'string' ? data.version : '',
      managedTabId: typeof data.managedTabId === 'number' ? data.managedTabId : undefined,
      managedTargetUrl: typeof data.managedTargetUrl === 'string' ? data.managedTargetUrl : undefined,
    }
  } catch {
    return UNAVAILABLE
  }
}

export function autoDetectLocally(targetUrl?: string): Promise<AutoDetectResult> {
  return sendExtensionRequest<AutoDetectResult>('autoDetect', {
    targetUrl,
  })
}

export function testSelectorLocally(selector: string, clearAfterMs = 2200, maxSamples = 5, targetUrl?: string): Promise<SelectorTestResult> {
  return sendExtensionRequest<SelectorTestResult>('testSelector', {
    selector,
    clearAfterMs,
    maxSamples,
    targetUrl,
  })
}

export function highlightSelectorLocally(selector: string, clearAfterMs = 2200, targetUrl?: string): Promise<{ highlightedCount: number }> {
  return sendExtensionRequest<{ highlightedCount: number }>('highlightSelector', {
    selector,
    clearAfterMs,
    targetUrl,
  })
}

export function extractHtmlLocally(itemSelector: string, maxItems = 3, targetUrl?: string): Promise<ExtractHtmlResult> {
  return sendExtensionRequest<ExtractHtmlResult>('extractHtml', {
    itemSelector,
    maxItems,
    targetUrl,
  })
}

export function extractPaginationContextLocally(targetUrl?: string): Promise<PaginationContextResult> {
  return sendExtensionRequest<PaginationContextResult>('extractPaginationContext', {
    targetUrl,
  })
}
