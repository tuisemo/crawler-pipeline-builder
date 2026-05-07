export class TabQueue {
  private queues = new Map<number, Promise<void>>()

  async enqueue<T>(tabId: number, fn: () => Promise<T>): Promise<T> {
    let release!: () => void
    const token = new Promise<void>((resolve) => {
      release = resolve
    })
    const prev = this.queues.get(tabId) ?? Promise.resolve()
    this.queues.set(tabId, prev.then(() => token))

    await prev
    try {
      return await fn()
    } finally {
      release()
      if (this.queues.get(tabId) === token) {
        this.queues.delete(tabId)
      }
    }
  }
}
