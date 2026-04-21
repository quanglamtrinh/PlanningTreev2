import { describe, expect, it } from 'vitest'
import {
  normalizeMarkdownHashLocationSuffix,
  parseLocalLinkTarget,
  renderLocalLinkTarget,
} from '../../src/features/markdown/localLink'

describe('localLink normalization', () => {
  it('normalizes #L..C.. into :line:col', () => {
    expect(normalizeMarkdownHashLocationSuffix('#L74C3')).toBe(':74:3')
  })

  it('normalizes #L..C..-L..C.. ranges', () => {
    expect(normalizeMarkdownHashLocationSuffix('#L74C3-L76C9')).toBe(':74:3-76:9')
  })

  it('parses file URLs and keeps normalized hash suffix', () => {
    expect(
      parseLocalLinkTarget('file:///Users/example/workspace/frame.md#L74C3'),
    ).toEqual({
      normalizedPathText: '/Users/example/workspace/frame.md',
      locationSuffix: ':74:3',
    })
  })

  it('shortens absolute local paths under project root', () => {
    expect(
      renderLocalLinkTarget('/Users/example/workspace/docs/frame.md#L74', {
        projectRootPath: '/Users/example/workspace',
      }),
    ).toBe('docs/frame.md:74')
  })

  it('keeps absolute local paths outside project root', () => {
    expect(
      renderLocalLinkTarget('/Users/example/other/spec.md#L12C8', {
        projectRootPath: '/Users/example/workspace',
      }),
    ).toBe('/Users/example/other/spec.md:12:8')
  })
})
