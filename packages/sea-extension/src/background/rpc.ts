export interface RpcMsg {
  id: string
  method: string
  params: Record<string, any>
  tabId?: number
}

export interface RpcResp {
  id: string
  ok: boolean
  tabId?: number
  result?: any
  error?: string
}

export class RpcClient {
  private ws: WebSocket | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private onMessage?: (msg: RpcMsg) => Promise<RpcResp>

  constructor(private serverUrl: string, private agentId: string) {}

  setHandler(fn: (msg: RpcMsg) => Promise<RpcResp>) {
    this.onMessage = fn
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return
    const url = `${this.serverUrl}/api/ext-relay/agent/${this.agentId}`
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      this.ws?.send(JSON.stringify({ type: 'event', event: 'connected', agentId: this.agentId, version: '1.0' }))
    }

    this.ws.onmessage = async (event) => {
      let message: RpcMsg
      try {
        message = JSON.parse(event.data) as RpcMsg
      } catch {
        return
      }
      if (!this.onMessage) return
      const response = await this.onMessage(message)
      this.ws?.send(JSON.stringify(response))
    }

    this.ws.onclose = () => {
      this.reconnectTimer = setTimeout(() => this.connect(), 3000)
    }
  }

  sendEvent(event: Record<string, unknown>) {
    this.ws?.send(JSON.stringify({ type: 'event', ...event }))
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this.ws = null
  }
}
