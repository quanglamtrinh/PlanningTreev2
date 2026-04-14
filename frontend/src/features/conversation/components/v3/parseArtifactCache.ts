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
const parseArtifactPending = new Map<string, Promise<unknown>>()
const latestRequestSeqByTokenBase = new Map<string, number>()

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

export function buildParseArtifactJobToken(
  baseKey: string,
  artifactId: string,
  requestSeq: number,
): string {
  return `${buildParseArtifactVariantKey(baseKey, artifactId)}|request_seq=${Math.max(0, Math.floor(requestSeq))}`
}

export function markLatestParseArtifactRequest(
  versionTokenBase: string,
  requestSeq: number,
): void {
  latestRequestSeqByTokenBase.set(
    versionTokenBase,
    Math.max(0, Math.floor(requestSeq)),
  )
}

export function isLatestParseArtifactRequest(
  versionTokenBase: string,
  requestSeq: number,
): boolean {
  const latest = latestRequestSeqByTokenBase.get(versionTokenBase)
  if (latest == null) {
    return false
  }
  return latest === Math.max(0, Math.floor(requestSeq))
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

export async function readOrComputeParseArtifactAsync<T>(
  key: string,
  compute: () => Promise<T>,
  options?: ParseArtifactCacheOptions,
): Promise<ParseArtifactCacheResult<T>> {
  const ttlMs = options?.ttlMs ?? PARSE_CACHE_TTL_MS_DEFAULT
  const maxEntries = options?.maxEntries ?? PARSE_CACHE_LRU_MAX_ENTRIES_DEFAULT
  const now = nowMs()

  evictExpiredEntries(now)

  const existing = parseArtifactCache.get(key)
  if (existing && existing.expiresAtMs > now) {
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

  const pending = parseArtifactPending.get(key)
  if (pending) {
    const value = (await pending) as T
    return {
      value,
      hit: false,
    }
  }

  const nextPromise = (async () => {
    const computedValue = await compute()
    parseArtifactCache.set(key, {
      value: computedValue,
      expiresAtMs: nowMs() + Math.max(0, ttlMs),
    })
    enforceMaxEntries(Math.max(1, maxEntries))
    return computedValue
  })()
  parseArtifactPending.set(key, nextPromise)

  try {
    const value = (await nextPromise) as T
    return {
      value,
      hit: false,
    }
  } finally {
    parseArtifactPending.delete(key)
  }
}

export function resetParseArtifactCache(): void {
  parseArtifactCache.clear()
  parseArtifactPending.clear()
  latestRequestSeqByTokenBase.clear()
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

export function resetParseArtifactRequestTrackingForTests(): void {
  latestRequestSeqByTokenBase.clear()
}
