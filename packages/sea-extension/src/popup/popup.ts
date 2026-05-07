const statusNode = document.getElementById('status') as HTMLDivElement
const serverUrlInput = document.getElementById('serverUrl') as HTMLInputElement
const agentIdInput = document.getElementById('agentId') as HTMLInputElement
const connectBtn = document.getElementById('connect') as HTMLButtonElement
const disconnectBtn = document.getElementById('disconnect') as HTMLButtonElement

function renderStatus(text: string) {
  statusNode.textContent = text
}

chrome.storage.local.get(['serverUrl', 'agentId'], ({ serverUrl, agentId }) => {
  serverUrlInput.value = serverUrl || ''
  agentIdInput.value = agentId || ''
  if (serverUrl && agentId) {
    renderStatus(`🟢 已配置 ${agentId}`)
  }
})

connectBtn.addEventListener('click', () => {
  const serverUrl = serverUrlInput.value.trim()
  const agentId = agentIdInput.value.trim()
  chrome.runtime.sendMessage({ type: 'CONNECT', serverUrl, agentId })
  chrome.storage.local.set({ serverUrl, agentId })
  renderStatus(`🟢 已连接 ${agentId || '未命名 Agent'}`)
})

disconnectBtn.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'DISCONNECT' })
  renderStatus('⚪ 已断开')
})
