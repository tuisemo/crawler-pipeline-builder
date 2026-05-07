import { describe, expect, it } from 'vitest'
import { buildRuntimeAgentId } from './executionTarget'

describe('buildRuntimeAgentId', () => {
  it('omits agent id in cloud mode', () => {
    expect(buildRuntimeAgentId('cloud', 'desktop-a')).toBeUndefined()
  })

  it('prefixes ext: in extension mode', () => {
    expect(buildRuntimeAgentId('extension', 'desktop-a')).toBe('ext:desktop-a')
  })

  it('trims whitespace before prefixing', () => {
    expect(buildRuntimeAgentId('extension', '  desktop-a  ')).toBe('ext:desktop-a')
  })
})
