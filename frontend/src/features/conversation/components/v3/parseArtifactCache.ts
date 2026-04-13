import {
  PARSE_CACHE_LRU_MAX_ENTRIES_DEFAULT,
  PARSE_CACHE_TTL_MS_DEFAULT,
} from './parseCacheContract'

type ParseArtifactCacheEntry = {
  value: unknown
  expiresAtMs: number
}

type ParseArtifactCacheOptions = {
  maxEntries?: number
  ttlMs?: number
}

type ParseArtifactCacheResult<T> = {
  value: T
  hit: boolean
}

const parseArtifactCache = new Map<string, ParseArtifactCacheEntry>()

let nowOverrideForTests: (() => number) | null = null

function nowMs(): number {
  return nowOverrideForTests ? nowOverrideForTests() : Date.now()
}

function normalizeThreadId(threadId: string | null | undefined): string {
  const normalized = String(threadId ?? '').trim()
  return normalized.length > 0 ? normalized : '_'
}

function evictExpiredEntries(now: number): void {
  for (const [key, entry] of parseArtifactCache) {
    if (entry.expiresAtMs <= now) {
      parseArtifactCache.delete(key)
    }
  }
}

function enforceMaxEntries(maxEntries: number): void {
  while (parseArtifactCache.size > maxEntries) {
    const oldestKey = parseArtifactCache.keys().next().value
    if (oldestKey == null) {
      return
    }
    parseArtifactCache.delete(oldestKey)
  }
}

export function buildParseArtifactVariantKey(baseKey: string, artifactId: string): string {
  return `${baseKey}|artifact=${encodeURIComponent(artifactId)}`
}

export function readOrComputeParseArtifact<T>(
  key: string,
  compute: () => T,
  options?: ParseArtifactCacheOptions,
): ParseArtifactCacheResult<T> {
  const ttlMs = options?.ttlMs ?? PARSE_CACHE_TTL_MS_DEFAULT
  const maxEntries = options?.maxEntries ?? PARSE_CACHE_LRU_MAX_ENTRIES_DEFAULT
  const now = nowMs()

  evictExpiredEntries(now)

  const existing = parseArtifactCache.get(key)
  if (existing && existing.expiresAtMs > now) {
    // Promote recency for LRU behavior.
    parseArtifactCache.delete(key)
    parseArtifactCache.set(key, existing)
    return {
      value: existing.value as T,
      hit: true,
    }
  }
  if (existing) {
    parseArtifactCache.delete(key)
  }

  const computedValue = compute()
  parseArtifactCache.set(key, {
    value: computedValue,
    expiresAtMs: now + Math.max(0, ttlMs),
  })
  enforceMaxEntries(Math.max(1, maxEntries))

  return {
    value: computedValue,
    hit: false,
  }
}

export function resetParseArtifactCache(): void {
  parseArtifactCache.clear()
}

export function resetParseArtifactCacheForThread(threadId: string | null | undefined): void {
  const threadToken = `|thread=${encodeURIComponent(normalizeThreadId(threadId))}|`
  for (const key of parseArtifactCache.keys()) {
    if (key.includes(threadToken)) {
      parseArtifactCache.delete(key)
    }
  }
}

export function setParseArtifactCacheNowOverrideForTests(
  override: (() => number) | null,
): void {
  nowOverrideForTests = override
}

export function getParseArtifactCacheSizeForTests(): number {
  return parseArtifactCache.size
}
