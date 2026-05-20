type ExtensionAction =
  | 'ping'
  | 'autoDetect'
  | 'testSelector'
  | 'highlightSelector'
  | 'extractHtml'
  | 'extractPaginationContext'

const BRIDGE_RPC_TYPE = 'BROWSER_BRIDGE_RPC'

type ExtensionRequest = {
  type: typeof BRIDGE_RPC_TYPE
  action: ExtensionAction
  payload?: Record<string, unknown>
}

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

const TRUSTED_WORKBENCH_ORIGINS = new Set([
  'http://127.0.0.1:3101',
  'http://localhost:3101',
  'https://test.zhongshu.tech',
])

function isBridgeRequest(value: unknown): value is PageBridgeRequest {
  return Boolean(value)
    && typeof value === 'object'
    && (value as PageBridgeRequest).source === 'BROWSER_BRIDGE_PAGE'
    && typeof (value as PageBridgeRequest).requestId === 'string'
    && typeof (value as PageBridgeRequest).action === 'string'
}

function respond(requestId: string, response: ExtensionResponse<unknown>) {
  const message: PageBridgeResponse = {
    source: 'BROWSER_BRIDGE_EXTENSION',
    requestId,
    response,
  }
  window.postMessage(message, window.location.origin)
}

window.addEventListener('message', (event) => {
  if (
    event.source !== window
    || !TRUSTED_WORKBENCH_ORIGINS.has(window.location.origin)
    || !isBridgeRequest(event.data)
  ) {
    return
  }

  const request: ExtensionRequest = {
    type: BRIDGE_RPC_TYPE,
    action: event.data.action,
    payload: event.data.payload,
  }

  try {
    chrome.runtime.sendMessage(request, (response: ExtensionResponse<unknown> | undefined) => {
      if (chrome.runtime.lastError) {
        respond(event.data.requestId, {
          ok: false,
          error: {
            code: 'extension_unreachable',
            message: chrome.runtime.lastError.message || 'Extension unreachable',
          },
        })
        return
      }

      respond(
        event.data.requestId,
        response ?? {
          ok: false,
          error: {
            code: 'extension_unreachable',
            message: 'Empty extension response',
          },
        },
      )
    })
  } catch (error) {
    respond(
      event.data.requestId,
      {
        ok: false,
        error: {
          code: 'extension_unreachable',
          message: error instanceof Error ? error.message : 'Extension unreachable',
        },
      },
    )
  }
})
