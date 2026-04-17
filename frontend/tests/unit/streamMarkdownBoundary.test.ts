import { describe, expect, it } from 'vitest'

import {
  SAFE_BOUNDARY_MIN_CHARS,
  shouldStreamRenderPlainText,
} from '../../src/features/conversation/components/v3/streamMarkdownBoundary'

describe('streamMarkdownBoundary', () => {
  it('does not force plain text when not streaming', () => {
    expect(
      shouldStreamRenderPlainText('Hello **world**.', {
        isStreaming: false,
      }),
    ).toBe(false)
  })

  it('keeps plain text for short streaming snippets', () => {
    expect(
      shouldStreamRenderPlainText('Short text', {
        isStreaming: true,
        minChars: SAFE_BOUNDARY_MIN_CHARS,
      }),
    ).toBe(true)
  })

  it('keeps plain text when fenced code block is unclosed', () => {
    const text = '```ts\nconst value = 1\n'
    expect(
      shouldStreamRenderPlainText(text, {
        isStreaming: true,
      }),
    ).toBe(true)
  })

  it('keeps plain text when markdown link is dangling', () => {
    const text = 'Refer to [spec](https://example.com/docs'
    expect(
      shouldStreamRenderPlainText(text, {
        isStreaming: true,
      }),
    ).toBe(true)
  })

  it('allows markdown render when stable boundary exists and markdown looks closed', () => {
    const text = 'This is a stable sentence with **markdown** and a closed link [a](https://example.com).\n'
    expect(
      shouldStreamRenderPlainText(text, {
        isStreaming: true,
      }),
    ).toBe(false)
  })
})
