export const CACHE_SCHEMA_VERSION = 1
export const PARSE_CACHE_RENDERER_VERSION = 'v1'
export const PARSE_CACHE_LRU_MAX_ENTRIES_DEFAULT = 1500
export const PARSE_CACHE_TTL_MS_DEFAULT = 10 * 60 * 1000

export const PARSE_CACHE_MODES = [
  'message_markdown',
  'reasoning_summary',
  'reasoning_detail',
  'tool_output_markdown',
  'diff_stats',
  'diff_unified',
] as const

export type ParseCacheMode = (typeof PARSE_CACHE_MODES)[number]

export type ParseCacheKeyInput = {
  threadId: string | null | undefined
  itemId: string
  updatedAt: string
  mode: ParseCacheMode
  rendererVersion?: string | null
}

function normalizeSegment(value: string | null | undefined, fallback: string): string {
  const normalized = String(value ?? '').trim()
  return encodeURIComponent(normalized.length > 0 ? normalized : fallback)
}

export function isParseCacheMode(value: string): value is ParseCacheMode {
  return (PARSE_CACHE_MODES as readonly string[]).includes(value)
}

export function buildParseCacheKey(input: ParseCacheKeyInput): string {
  const rendererVersion = normalizeSegment(
    input.rendererVersion ?? PARSE_CACHE_RENDERER_VERSION,
    PARSE_CACHE_RENDERER_VERSION,
  )
  const threadId = normalizeSegment(input.threadId, '_')
  const itemId = normalizeSegment(input.itemId, '_')
  const updatedAt = normalizeSegment(input.updatedAt, '_')
  const mode = normalizeSegment(input.mode, 'message_markdown')
  return `cache_schema=${CACHE_SCHEMA_VERSION}|renderer=${rendererVersion}|mode=${mode}|thread=${threadId}|item=${itemId}|updated_at=${updatedAt}`
}
