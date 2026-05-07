export type ExecutionMode = 'cloud' | 'extension'

export function buildRuntimeAgentId(mode: ExecutionMode, agentId: string): string | undefined {
  const trimmed = agentId.trim()
  if (mode !== 'extension' || !trimmed) return undefined
  return `ext:${trimmed}`
}
