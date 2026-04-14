import { describe, expect, it } from 'vitest'

import {
  buildParseCacheKey,
  CACHE_SCHEMA_VERSION,
  isParseCacheMode,
  PARSE_CACHE_MODES,
  PARSE_CACHE_RENDERER_VERSION,
} from '../../src/features/conversation/components/v3/parseCacheContract'

describe('parseCacheContract', () => {
  it('accepts only whitelisted parse cache modes', () => {
    for (const mode of PARSE_CACHE_MODES) {
      expect(isParseCacheMode(mode)).toBe(true)
    }
    expect(isParseCacheMode('not_a_mode')).toBe(false)
    expect(isParseCacheMode('review_markdown')).toBe(false)
  })

  it('builds deterministic keys from the same input', () => {
    const input = {
      threadId: 'thread-1',
      itemId: 'item-7',
      updatedAt: '2026-04-13T00:00:00Z',
      mode: 'message_markdown' as const,
      rendererVersion: PARSE_CACHE_RENDERER_VERSION,
    }
    const first = buildParseCacheKey(input)
    const second = buildParseCacheKey(input)

    expect(first).toBe(second)
    expect(first).toContain(`cache_schema=${CACHE_SCHEMA_VERSION}`)
    expect(first).toContain(`renderer=${PARSE_CACHE_RENDERER_VERSION}`)
    expect(first).toContain('mode=message_markdown')
  })

  it('invalidates key when freshness fields change', () => {
    const base = buildParseCacheKey({
      threadId: 'thread-1',
      itemId: 'item-1',
      updatedAt: '2026-04-13T00:00:00Z',
      mode: 'diff_unified',
      rendererVersion: 'v1',
    })
    const withUpdatedAt = buildParseCacheKey({
      threadId: 'thread-1',
      itemId: 'item-1',
      updatedAt: '2026-04-13T00:00:01Z',
      mode: 'diff_unified',
      rendererVersion: 'v1',
    })
    const withMode = buildParseCacheKey({
      threadId: 'thread-1',
      itemId: 'item-1',
      updatedAt: '2026-04-13T00:00:00Z',
      mode: 'diff_stats',
      rendererVersion: 'v1',
    })
    const withRendererVersion = buildParseCacheKey({
      threadId: 'thread-1',
      itemId: 'item-1',
      updatedAt: '2026-04-13T00:00:00Z',
      mode: 'diff_unified',
      rendererVersion: 'v2',
    })

    expect(withUpdatedAt).not.toBe(base)
    expect(withMode).not.toBe(base)
    expect(withRendererVersion).not.toBe(base)
  })

  it('normalizes and URL-encodes segments safely', () => {
    const key = buildParseCacheKey({
      threadId: ' thread/1 ',
      itemId: ' item id ',
      updatedAt: ' 2026-04-13T00:00:00Z ',
      mode: 'tool_output_markdown',
      rendererVersion: ' v1 custom ',
    })

    expect(key).toContain('thread=thread%2F1')
    expect(key).toContain('item=item%20id')
    expect(key).toContain('renderer=v1%20custom')
    expect(key).toContain('updated_at=2026-04-13T00%3A00%3A00Z')
  })
})
