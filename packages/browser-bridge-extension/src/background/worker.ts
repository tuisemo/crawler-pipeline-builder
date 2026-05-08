import { SCRIPT_REGISTRY } from '../scripts/registry'
import { TabQueue } from './tab_queue'

const tabQueue = new TabQueue()
let managedTabId: number | null = null
let managedTargetUrl = ''

type ExtensionAction =
  | 'ping'
  | 'autoDetect'
  | 'testSelector'
  | 'highlightSelector'
  | 'extractHtml'
  | 'extractPaginationContext'

type ExtensionRequest = {
  type: 'SEA_RPC'
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

type BuiltinResult = Record<string, any>

function ok<T>(data: T): ExtensionResponse<T> {
  return { ok: true, data }
}

function fail(code: ExtensionErrorCode, message: string): ExtensionResponse<never> {
  return { ok: false, error: { code, message } }
}

async function getActiveTabId(): Promise<number> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (typeof tab?.id !== 'number') {
    throw new Error('No active tab available')
  }
  return tab.id
}

function normalizeUrl(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

async function waitTabLoad(tabId: number, timeoutMs = 30000): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Tab load timeout')), timeoutMs)

    function finish() {
      chrome.tabs.onUpdated.removeListener(onUpdated)
      clearTimeout(timer)
      resolve()
    }

    function onUpdated(id: number, info: chrome.tabs.TabChangeInfo) {
      if (id === tabId && info.status === 'complete') {
        finish()
      }
    }

    chrome.tabs.onUpdated.addListener(onUpdated)
    void chrome.tabs.get(tabId).then((tab) => {
      if (tab.status === 'complete') {
        finish()
      }
    }).catch(() => {})
  })
}

async function focusWindow(windowId: number) {
  try {
    await chrome.windows.update(windowId, { focused: true, drawAttention: true })
  } catch {
    // Ignore if window is gone
  }
}

async function resolveTargetTabId(targetUrl?: string, senderTabId?: number): Promise<number> {
  const normalizedTargetUrl = normalizeUrl(targetUrl);
  if (!normalizedTargetUrl) {
    console.log("[Bridge] No target URL provided, using active tab.");
    return getActiveTabId();
  }

  const cleanUrl = (url: string) => url.split("#")[0].replace(/\/$/, "");
  const targetClean = cleanUrl(normalizedTargetUrl);

  console.log(`[Bridge] Resolving tab for: ${normalizedTargetUrl} (clean: ${targetClean})`);

  // Helper to ensure tab is active and focused
  const ensureVisible = async (tabId: number) => {
    const tab = await chrome.tabs.update(tabId, { active: true });
    if (typeof tab?.windowId === "number") {
      await focusWindow(tab.windowId);
    }
  };

  // 1. Check if we already have a managed tab
  if (managedTabId !== null) {
    try {
      const existingManaged = await chrome.tabs.get(managedTabId);
      if (typeof existingManaged.id === "number") {
        const currentClean = cleanUrl(existingManaged.url || "");
        if (currentClean === targetClean) {
          console.log(`[Bridge] Reusing existing managed tab: ${managedTabId}`);
          await ensureVisible(managedTabId);
          return managedTabId;
        } else {
          console.log(`[Bridge] Managed tab URL mismatch (${currentClean} vs ${targetClean}), updating...`);
          await chrome.tabs.update(managedTabId, { url: normalizedTargetUrl, active: true });
          await waitTabLoad(managedTabId);
          await ensureVisible(managedTabId);
          managedTargetUrl = normalizedTargetUrl;
          return managedTabId;
        }
      }
    } catch {
      managedTabId = null;
      managedTargetUrl = "";
    }
  }

  // 2. Search all tabs for a match (excluding the sender tab if provided)
  const allTabs = await chrome.tabs.query({});
  const reusableTab = allTabs.find((tab) => {
    if (typeof tab.id !== "number" || tab.id === senderTabId) return false;
    return cleanUrl(tab.url || "") === targetClean;
  });

  if (reusableTab?.id !== undefined) {
    console.log(`[Bridge] Found reusable tab: ${reusableTab.id}`);
    managedTabId = reusableTab.id;
    managedTargetUrl = normalizedTargetUrl;
    if (reusableTab.status !== "complete") {
      await waitTabLoad(reusableTab.id);
    }
    await ensureVisible(reusableTab.id);
    return reusableTab.id;
  }

  // 3. Create a new tab if no match found
  console.log("[Bridge] No matching tab found, creating new one.");
  const createdTab = await chrome.tabs.create({ url: normalizedTargetUrl, active: true });
  if (typeof createdTab.id !== "number") {
    throw new Error("Failed to create target tab");
  }
  managedTabId = createdTab.id;
  managedTargetUrl = normalizedTargetUrl;
  await waitTabLoad(createdTab.id);
  await ensureVisible(createdTab.id);
  return createdTab.id;
}

async function runScript(
  targetUrl: string | undefined,
  name: keyof typeof SCRIPT_REGISTRY,
  args: unknown[] = [],
  senderTabId?: number,
): Promise<BuiltinResult> {
  const tabId = await resolveTargetTabId(targetUrl, senderTabId)
  const fn = SCRIPT_REGISTRY[name]
  console.log(`[Bridge] Running script ${name} on tab ${tabId}`);
  return tabQueue.enqueue(tabId, async () => {
    const response = await chrome.scripting.executeScript({
      target: { tabId },
      func: fn,
      args,
    })
    return (response[0]?.result ?? {}) as BuiltinResult
  })
}

function mapScriptFailure(error: unknown): ExtensionResponse<never> {
  const message = error instanceof Error ? error.message : 'Extension error'
  if (message.includes('No active tab')) {
    return fail('no_active_tab', 'No active tab available')
  }
  return fail('script_execution_failed', message)
}

async function handleRequest(
  message: ExtensionRequest,
  senderTabId?: number,
): Promise<ExtensionResponse<unknown>> {
  try {
    if (message.type !== 'SEA_RPC') {
      return fail('extension_unreachable', 'Unsupported message type')
    }

    const payload = message.payload ?? {}
    const targetUrl = normalizeUrl(payload.targetUrl)

    if (message.action === 'ping') {
      return ok({
        ready: true,
        version: '1.0.0',
        managedTabId,
        managedTargetUrl,
      })
    }

    if (message.action === 'autoDetect') {
      const result = await runScript(targetUrl, 'bridge_auto_detect', [], senderTabId)
      if (result.success === false) {
        return fail('script_execution_failed', result.reason || result.error || 'Auto detect failed')
      }
      return ok({
        itemSelector: typeof result.item_selector === 'string' ? result.item_selector : '',
        paginationSelector: typeof result.pagination_selector === 'string' ? result.pagination_selector : '',
        paginationStrategy: typeof result.pagination_strategy === 'string' ? result.pagination_strategy : 'none',
        fields: Array.isArray(result.fields) ? result.fields : [],
        htmlFragment: typeof result.html_fragment === 'string' ? result.html_fragment : '',
        confidence: typeof result.confidence === 'number' ? result.confidence : undefined,
      })
    }

    if (message.action === 'testSelector') {
      const selector = String(payload.selector || '').trim()
      const clearAfterMs = Number(payload.clearAfterMs ?? 2200)
      const maxSamples = Number(payload.maxSamples ?? 5)
      const query = await runScript(targetUrl, 'bridge_query_selector', [selector, maxSamples], senderTabId)
      if (query.ok === false) {
        return fail('invalid_selector', query.error || 'Invalid selector')
      }
      let highlightedCount = 0
      if (Number(query.count || 0) > 0) {
        const highlight = await runScript(targetUrl, 'bridge_highlight_selector', [selector, clearAfterMs], senderTabId)
        if (highlight.error) {
          return fail('script_execution_failed', highlight.error)
        }
        highlightedCount = Number(highlight.highlighted_count || 0)
      }
      return ok({
        matchCount: Number(query.count || 0),
        highlightedCount,
        clearAfterMs,
        elements: Array.isArray(query.elements) ? query.elements : [],
      })
    }

    if (message.action === 'highlightSelector') {
      const selector = String(payload.selector || '').trim()
      const clearAfterMs = Number(payload.clearAfterMs ?? 2200)
      const highlight = await runScript(targetUrl, 'bridge_highlight_selector', [selector, clearAfterMs], senderTabId)
      if (highlight.error) {
        return fail('invalid_selector', highlight.error)
      }
      return ok({
        highlightedCount: Number(highlight.highlighted_count || 0),
      })
    }

    if (message.action === 'extractHtml') {
      const itemSelector = String(payload.itemSelector || '').trim()
      const maxItems = Number(payload.maxItems ?? 3)
      const result = await runScript(targetUrl, 'bridge_extract_items', [itemSelector, maxItems], senderTabId)
      if (result.error) {
        return fail('invalid_selector', result.error)
      }
      return ok({
        htmlFragment: typeof result.html === 'string' ? result.html : '',
        itemCount: Number(result.item_count || 0),
        truncated: result.truncated === true,
        originalSize: Number(result.original_size || 0),
        truncatedSize: Number(result.truncated_size || 0),
      })
    }

    if (message.action === 'extractPaginationContext') {
      const result = await runScript(targetUrl, 'bridge_extract_pagination_context', [], senderTabId)
      if (result.error) {
        return fail('script_execution_failed', result.error)
      }
      return ok({
        htmlFragment: typeof result.html === 'string' ? result.html : '',
        paginationComponentHtml: typeof result.pagination_component_html === 'string' ? result.pagination_component_html : '',
        prunedBodyHtml: typeof result.pruned_body_html === 'string' ? result.pruned_body_html : '',
      })
    }

    return fail('extension_unreachable', 'Unsupported action')
  } catch (error) {
    return mapScriptFailure(error)
  }
}

function addMessageHandler(
  listener: (
    message: ExtensionRequest,
    sender: chrome.runtime.MessageSender,
    sendResponse: (response: ExtensionResponse<unknown>) => void,
  ) => void,
) {
  return (
    message: ExtensionRequest,
    sender: chrome.runtime.MessageSender,
    sendResponse: (response: ExtensionResponse<unknown>) => void,
  ) => {
    listener(message, sender, sendResponse)
    return true
  }
}

const respond = addMessageHandler((message, sender, sendResponse) => {
  void handleRequest(message, sender.tab?.id).then(sendResponse)
})

chrome.tabs.onRemoved.addListener((tabId) => {
  if (managedTabId === tabId) {
    managedTabId = null
    managedTargetUrl = ''
  }
})

chrome.runtime.onMessage.addListener(respond)
chrome.runtime.onMessageExternal.addListener(respond)
