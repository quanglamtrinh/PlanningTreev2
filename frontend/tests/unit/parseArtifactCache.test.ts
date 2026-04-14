import { afterEach, describe, expect, it } from 'vitest'

import {
  buildParseCacheKey,
  PARSE_CACHE_RENDERER_VERSION,
} from '../../src/features/conversation/components/v3/parseCacheContract'
import {
  buildParseArtifactJobToken,
  buildParseArtifactVariantKey,
  getParseArtifactCacheSizeForTests,
  isLatestParseArtifactRequest,
  markLatestParseArtifactRequest,
  readOrComputeParseArtifactAsync,
  readOrComputeParseArtifact,
  resetParseArtifactCache,
  resetParseArtifactCacheForThread,
  resetParseArtifactRequestTrackingForTests,
  setParseArtifactCacheNowOverrideForTests,
} from '../../src/features/conversation/components/v3/parseArtifactCache'

afterEach(() => {
  setParseArtifactCacheNowOverrideForTests(null)
  resetParseArtifactCache()
  resetParseArtifactRequestTrackingForTests()
})

describe('parseArtifactCache', () => {
  it('returns miss then hit for the same key', () => {
    let computeCount = 0
    const key = 'cache_schema=1|renderer=v1|mode=message_markdown|thread=t|item=i|updated_at=u|artifact=sample'

    const first = readOrComputeParseArtifact(key, () => {
      computeCount += 1
      return { value: 'A' }
    })
    const second = readOrComputeParseArtifact(key, () => {
      computeCount += 1
      return { value: 'B' }
    })

    expect(first.hit).toBe(false)
    expect(second.hit).toBe(true)
    expect(first.value).toEqual({ value: 'A' })
    expect(second.value).toEqual({ value: 'A' })
    expect(computeCount).toBe(1)
  })

  it('keeps artifacts isolated by mode-specific keys', () => {
    const markdownKey = buildParseArtifactVariantKey(
      buildParseCacheKey({
        threadId: 'thread-1',
        itemId: 'item-1',
        updatedAt: '2026-04-13T00:00:00Z',
        mode: 'message_markdown',
        rendererVersion: PARSE_CACHE_RENDERER_VERSION,
      }),
      'payload',
    )
    const diffKey = buildParseArtifactVariantKey(
      buildParseCacheKey({
        threadId: 'thread-1',
        itemId: 'item-1',
        updatedAt: '2026-04-13T00:00:00Z',
        mode: 'diff_unified',
        rendererVersion: PARSE_CACHE_RENDERER_VERSION,
      }),
      'payload',
    )

    const markdown = readOrComputeParseArtifact(markdownKey, () => 'markdown')
    const diff = readOrComputeParseArtifact(diffKey, () => 'diff')

    expect(markdown.hit).toBe(false)
    expect(diff.hit).toBe(false)
    expect(readOrComputeParseArtifact(markdownKey, () => 'changed').value).toBe('markdown')
    expect(readOrComputeParseArtifact(diffKey, () => 'changed').value).toBe('diff')
  })

  it('expires entries when TTL elapsed', () => {
    let now = 1_000
    setParseArtifactCacheNowOverrideForTests(() => now)

    const key = 'cache_schema=1|renderer=v1|mode=diff_stats|thread=t|item=i|updated_at=u|artifact=stats'
    const first = readOrComputeParseArtifact(
      key,
      () => 7,
      { ttlMs: 50 },
    )
    now += 25
    const second = readOrComputeParseArtifact(
      key,
      () => 9,
      { ttlMs: 50 },
    )
    now += 30
    const third = readOrComputeParseArtifact(
      key,
      () => 11,
      { ttlMs: 50 },
    )

    expect(first.hit).toBe(false)
    expect(second.hit).toBe(true)
    expect(second.value).toBe(7)
    expect(third.hit).toBe(false)
    expect(third.value).toBe(11)
  })

  it('evicts least-recently-used entry when max entries exceeded', () => {
    const k1 = 'k1'
    const k2 = 'k2'
    const k3 = 'k3'
    const k4 = 'k4'

    readOrComputeParseArtifact(k1, () => 'v1', { maxEntries: 3, ttlMs: 10_000 })
    readOrComputeParseArtifact(k2, () => 'v2', { maxEntries: 3, ttlMs: 10_000 })
    readOrComputeParseArtifact(k3, () => 'v3', { maxEntries: 3, ttlMs: 10_000 })
    // Touch k1 to make it recently used.
    readOrComputeParseArtifact(k1, () => 'new-v1', { maxEntries: 3, ttlMs: 10_000 })
    // Insert k4, should evict k2.
    readOrComputeParseArtifact(k4, () => 'v4', { maxEntries: 3, ttlMs: 10_000 })

    expect(getParseArtifactCacheSizeForTests()).toBe(3)
    expect(readOrComputeParseArtifact(k1, () => 'changed', { maxEntries: 3, ttlMs: 10_000 }).hit).toBe(true)
    expect(readOrComputeParseArtifact(k2, () => 'recomputed', { maxEntries: 3, ttlMs: 10_000 }).hit).toBe(false)
  })

  it('resets only targeted thread artifacts', () => {
    const threadAKey = buildParseArtifactVariantKey(
      buildParseCacheKey({
        threadId: 'thread-A',
        itemId: 'item-1',
        updatedAt: '2026-04-13T00:00:00Z',
        mode: 'message_markdown',
        rendererVersion: PARSE_CACHE_RENDERER_VERSION,
      }),
      'artifact',
    )
    const threadBKey = buildParseArtifactVariantKey(
      buildParseCacheKey({
        threadId: 'thread-B',
        itemId: 'item-1',
        updatedAt: '2026-04-13T00:00:00Z',
        mode: 'message_markdown',
        rendererVersion: PARSE_CACHE_RENDERER_VERSION,
      }),
      'artifact',
    )

    readOrComputeParseArtifact(threadAKey, () => 'A')
    readOrComputeParseArtifact(threadBKey, () => 'B')

    resetParseArtifactCacheForThread('thread-A')

    expect(readOrComputeParseArtifact(threadAKey, () => 'A2').hit).toBe(false)
    expect(readOrComputeParseArtifact(threadBKey, () => 'B2').hit).toBe(true)
  })

  it('deduplicates concurrent async compute for the same key', async () => {
    const key = 'cache_schema=1|renderer=v1|mode=diff_unified|thread=t|item=i|updated_at=u|artifact=async'
    let computeCount = 0
    const compute = async () => {
      computeCount += 1
      await Promise.resolve()
      return { value: 'async' }
    }

    const [left, right] = await Promise.all([
      readOrComputeParseArtifactAsync(key, compute),
      readOrComputeParseArtifactAsync(key, compute),
    ])

    expect(computeCount).toBe(1)
    expect(left.value).toEqual({ value: 'async' })
    expect(right.value).toEqual({ value: 'async' })
  })

  it('tracks latest request sequence per version token base', () => {
    const tokenBase = buildParseArtifactVariantKey('base', 'phase11_worker_diff_artifacts')

    markLatestParseArtifactRequest(tokenBase, 3)
    expect(isLatestParseArtifactRequest(tokenBase, 2)).toBe(false)
    expect(isLatestParseArtifactRequest(tokenBase, 3)).toBe(true)

    markLatestParseArtifactRequest(tokenBase, 4)
    expect(isLatestParseArtifactRequest(tokenBase, 3)).toBe(false)
    expect(isLatestParseArtifactRequest(tokenBase, 4)).toBe(true)
  })

  it('builds deterministic parse artifact job token format', () => {
    const token = buildParseArtifactJobToken('base-key', 'worker_artifact', 7)
    expect(token).toContain('base-key')
    expect(token).toContain('artifact=worker_artifact')
    expect(token).toContain('request_seq=7')
  })
})
