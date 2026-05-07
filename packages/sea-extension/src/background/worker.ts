import { SCRIPT_REGISTRY } from '../scripts/registry'
import { RpcClient, type RpcMsg, type RpcResp } from './rpc'
import { TabQueue } from './tab_queue'

const tabQueue = new TabQueue()
let rpc: RpcClient | null = null

function waitTabLoad(tabId: number, timeoutMs = 30000): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Tab load timeout')), timeoutMs)

    function onUpdated(id: number, info: chrome.tabs.TabChangeInfo) {
      if (id === tabId && info.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(onUpdated)
        clearTimeout(timer)
        resolve()
      }
    }

    chrome.tabs.onUpdated.addListener(onUpdated)
    chrome.tabs.get(tabId).then((tab) => {
      if (tab.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(onUpdated)
        clearTimeout(timer)
        resolve()
      }
    }).catch(() => {})
  })
}

async function dispatch(message: RpcMsg): Promise<RpcResp> {
  const { id, method, params, tabId } = message

  try {
    let result: any

    if (method === 'new_tab') {
      const tab = await chrome.tabs.create({ url: params.url || 'about:blank' })
      await waitTabLoad(tab.id!)
      result = { tabId: tab.id }
    } else if (method === 'navigate') {
      if (typeof tabId !== 'number') throw new Error('navigate requires tabId')
      await chrome.tabs.update(tabId, { url: params.url })
      await waitTabLoad(tabId)
      result = { tabId, url: params.url }
    } else if (method === 'exec_script') {
      if (typeof tabId !== 'number') throw new Error('exec_script requires tabId')
      const fn = SCRIPT_REGISTRY[params.fn as keyof typeof SCRIPT_REGISTRY]
      if (!fn) throw new Error(`Unknown script function: ${params.fn}`)
      result = await tabQueue.enqueue(tabId, async () => {
        const response = await chrome.scripting.executeScript({
          target: { tabId },
          func: fn,
          args: params.args ?? [],
        })
        return response[0]?.result ?? {}
      })
    } else {
      throw new Error(`Unknown method: ${method}`)
    }

    return { id, ok: true, tabId, result }
  } catch (error) {
    return { id, ok: false, tabId, error: error instanceof Error ? error.message : 'Extension error' }
  }
}

chrome.tabs.onRemoved.addListener((tabId) => {
  rpc?.sendEvent({ event: 'tab_closed', tabId })
})

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.url) {
    rpc?.sendEvent({ event: 'tab_navigated', tabId, url: info.url })
  }
})

chrome.storage.local.get(['serverUrl', 'agentId'], ({ serverUrl, agentId }) => {
  if (serverUrl && agentId) {
    rpc = new RpcClient(serverUrl, agentId)
    rpc.setHandler(dispatch)
    rpc.connect()
  }
})

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'CONNECT') {
    rpc?.disconnect()
    rpc = new RpcClient(message.serverUrl, message.agentId)
    rpc.setHandler(dispatch)
    rpc.connect()
    chrome.storage.local.set({ serverUrl: message.serverUrl, agentId: message.agentId })
  }
  if (message.type === 'DISCONNECT') {
    rpc?.disconnect()
    rpc = null
  }
})
