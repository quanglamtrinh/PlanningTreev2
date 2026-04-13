import type { ConversationItemV3 } from '../../../../api/types'
import type { ParseCacheMode } from './parseCacheContract'

export type RowRenderProfileEvent = {
  threadId: string
  itemId: string
  kind: ConversationItemV3['kind']
  status: ConversationItemV3['status']
  updatedAt: string
  sequence: number
}

export type ParseCacheTraceEvent = {
  source: string
  threadId: string | null
  itemId: string
  updatedAt: string
  mode: ParseCacheMode
  rendererVersion: string
  key: string
  hit: boolean
}

export type ParseCacheTraceInput = Omit<ParseCacheTraceEvent, 'hit'>

export type MessagesV3ProfilingHooks = {
  onRowRender?: (event: RowRenderProfileEvent) => void
  onParseCacheTrace?: (event: ParseCacheTraceEvent) => void
}

type ProfilingRuntimeOverrideForTests = {
  mode?: string
  envFlagValue?: string | null
}

export const MAX_TRACKED_PARSE_KEYS = 2000
export const PROFILING_ENV_FLAG = 'VITE_ENABLE_MESSAGES_V3_PROFILING'

const NOOP_HOOKS: MessagesV3ProfilingHooks = {
  onRowRender: () => undefined,
  onParseCacheTrace: () => undefined,
}

let activeHooks: MessagesV3ProfilingHooks = NOOP_HOOKS
let hasHookSubscribers = false
const seenParseKeys = new Set<string>()
const parseKeyQueue: string[] = []
let runtimeOverrideForTests: ProfilingRuntimeOverrideForTests | null = null

function resolveRuntimeMode(): string {
  if (runtimeOverrideForTests?.mode != null) {
    return String(runtimeOverrideForTests.mode)
  }
  return String(import.meta.env.MODE ?? '')
}

function resolveRuntimeFlag(): string {
  if (runtimeOverrideForTests && 'envFlagValue' in runtimeOverrideForTests) {
    return String(runtimeOverrideForTests.envFlagValue ?? '')
  }
  const env = import.meta.env as Record<string, unknown>
  return String(env[PROFILING_ENV_FLAG] ?? '')
}

function isProfilingEnabled(): boolean {
  if (hasHookSubscribers) {
    return true
  }
  if (resolveRuntimeMode() === 'test') {
    return true
  }
  return resolveRuntimeFlag() === '1'
}

function trackParseKey(key: string): void {
  if (seenParseKeys.has(key)) {
    return
  }
  seenParseKeys.add(key)
  parseKeyQueue.push(key)
  while (parseKeyQueue.length > MAX_TRACKED_PARSE_KEYS) {
    const oldestKey = parseKeyQueue.shift()
    if (oldestKey != null) {
      seenParseKeys.delete(oldestKey)
    }
  }
}

function clearTrackedParseKeys(): void {
  seenParseKeys.clear()
  parseKeyQueue.length = 0
}

export function setMessagesV3ProfilingHooks(overrides: Partial<MessagesV3ProfilingHooks> | null): void {
  if (!overrides) {
    activeHooks = NOOP_HOOKS
    hasHookSubscribers = false
    return
  }
  activeHooks = {
    ...NOOP_HOOKS,
    ...overrides,
  }
  hasHookSubscribers =
    typeof overrides.onRowRender === 'function' || typeof overrides.onParseCacheTrace === 'function'
}

export function resetMessagesV3ProfilingHooks(): void {
  activeHooks = NOOP_HOOKS
  hasHookSubscribers = false
  clearTrackedParseKeys()
}

export function resetMessagesV3ProfilingState(): void {
  clearTrackedParseKeys()
}

export function emitRowRenderProfile(event: RowRenderProfileEvent): void {
  if (!isProfilingEnabled()) {
    return
  }
  activeHooks.onRowRender?.(event)
}

export function emitParseCacheTrace(input: ParseCacheTraceInput): ParseCacheTraceEvent {
  if (!isProfilingEnabled()) {
    return {
      ...input,
      hit: false,
    }
  }
  const hit = seenParseKeys.has(input.key)
  trackParseKey(input.key)
  const event: ParseCacheTraceEvent = {
    ...input,
    hit,
  }
  activeHooks.onParseCacheTrace?.(event)
  return event
}

export function setMessagesV3ProfilingRuntimeOverrideForTests(
  override: ProfilingRuntimeOverrideForTests | null,
): void {
  runtimeOverrideForTests = override
}
