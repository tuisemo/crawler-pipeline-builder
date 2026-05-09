const statusBar = document.getElementById('status') as HTMLDivElement
const statusText = document.getElementById('statusText') as HTMLSpanElement
const pageHint = document.getElementById('pageHint') as HTMLParagraphElement

type StatusLevel = 'disconnected' | 'connecting' | 'connected'
const BRIDGE_RPC_TYPE = 'BROWSER_BRIDGE_RPC'

function renderStatus(level: StatusLevel, detail: string) {
  statusBar.className = `status-bar ${level}`
  statusText.textContent = detail
}

async function init() {
  renderStatus('connecting', '检查扩展状态中…')

  try {
    const response = await chrome.runtime.sendMessage({
      type: BRIDGE_RPC_TYPE,
      action: 'ping',
    })
    if (response?.ok && response.data?.ready) {
      renderStatus('connected', '已就绪（本地扩展直连）')
    } else {
      renderStatus('disconnected', '扩展未就绪')
    }
  } catch {
    renderStatus('disconnected', '扩展未就绪')
  }

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    pageHint.textContent = tab?.url
      ? `当前活动页：${tab.url}`
      : '未检测到当前活动页，请先切换到目标网页。'
  } catch {
    pageHint.textContent = '未检测到当前活动页，请先切换到目标网页。'
  }
}

void init()
