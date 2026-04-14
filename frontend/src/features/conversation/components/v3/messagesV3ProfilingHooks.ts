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

export type MessagesV3Phase10Mode = 'off' | 'shadow' | 'on'

export type Phase10ProgressiveBatchEvent = {
  threadId: string | null
  mode: MessagesV3Phase10Mode
  previousVisibleCount: number
  nextVisibleCount: number
  totalCount: number
  batchSize: number
  frameDurationMs: number
  frameBudgetMs: number
  budgetDegradeLevel: 0 | 1 | 2
  virtualized: boolean
}

export type Phase10AnchorRestoreEvent = {
  threadId: string | null
  mode: MessagesV3Phase10Mode
  entryKey: string | null
  restored: boolean
  appliedScrollAdjustment: boolean
  driftPx: number | null
  virtualized: boolean
  reason:
    | 'anchor_restored'
    | 'anchor_missing'
    | 'anchor_missing_after_stabilization'
    | 'anchor_drift_after_stabilization'
}

export type Phase10FallbackEvent = {
  threadId: string | null
  mode: MessagesV3Phase10Mode
  reason:
    | 'anchor_missing'
    | 'anchor_drift'
    | 'virtualization_anchor_missing'
    | 'virtualization_anchor_drift'
  entryKey: string | null
  driftPx: number | null
}

export type MessagesV3ProfilingHooks = {
  onRowRender?: (event: RowRenderProfileEvent) => void
  onParseCacheTrace?: (event: ParseCacheTraceEvent) => void
  onPhase10ProgressiveBatch?: (event: Phase10ProgressiveBatchEvent) => void
  onPhase10AnchorRestore?: (event: Phase10AnchorRestoreEvent) => void
  onPhase10Fallback?: (event: Phase10FallbackEvent) => void
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
  onPhase10ProgressiveBatch: () => undefined,
  onPhase10AnchorRestore: () => undefined,
  onPhase10Fallback: () => undefined,
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
    typeof overrides.onRowRender === 'function' ||
    typeof overrides.onParseCacheTrace === 'function' ||
    typeof overrides.onPhase10ProgressiveBatch === 'function' ||
    typeof overrides.onPhase10AnchorRestore === 'function' ||
    typeof overrides.onPhase10Fallback === 'function'
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

export function emitPhase10ProgressiveBatch(event: Phase10ProgressiveBatchEvent): void {
  if (!isProfilingEnabled()) {
    return
  }
  activeHooks.onPhase10ProgressiveBatch?.(event)
}

export function emitPhase10AnchorRestore(event: Phase10AnchorRestoreEvent): void {
  if (!isProfilingEnabled()) {
    return
  }
  activeHooks.onPhase10AnchorRestore?.(event)
}

export function emitPhase10Fallback(event: Phase10FallbackEvent): void {
  if (!isProfilingEnabled()) {
    return
  }
  activeHooks.onPhase10Fallback?.(event)
}

export function setMessagesV3ProfilingRuntimeOverrideForTests(
  override: ProfilingRuntimeOverrideForTests | null,
): void {
  runtimeOverrideForTests = override
}
