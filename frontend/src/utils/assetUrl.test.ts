// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { getPublicAssetUrl } from './assetUrl'

describe('getPublicAssetUrl', () => {
  it('resolves assets at the site root in local development', () => {
    window.history.replaceState(null, '', 'http://localhost:3000/')

    expect(getPublicAssetUrl('logo.svg')).toBe('http://localhost:3000/logo.svg')
  })

  it('resolves assets under the current deploy subpath', () => {
    window.history.replaceState(null, '', '/crawler-studio/')

    expect(getPublicAssetUrl('logo.svg')).toBe('http://localhost:3000/crawler-studio/logo.svg')
  })
})
