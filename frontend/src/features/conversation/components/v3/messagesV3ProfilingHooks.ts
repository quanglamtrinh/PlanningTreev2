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

const NOOP_HOOKS: MessagesV3ProfilingHooks = {
  onRowRender: () => undefined,
  onParseCacheTrace: () => undefined,
}

let activeHooks: MessagesV3ProfilingHooks = NOOP_HOOKS
const seenParseKeys = new Set<string>()

export function setMessagesV3ProfilingHooks(overrides: Partial<MessagesV3ProfilingHooks> | null): void {
  if (!overrides) {
    activeHooks = NOOP_HOOKS
    return
  }
  activeHooks = {
    ...NOOP_HOOKS,
    ...overrides,
  }
}

export function resetMessagesV3ProfilingHooks(): void {
  activeHooks = NOOP_HOOKS
  seenParseKeys.clear()
}

export function resetMessagesV3ProfilingState(): void {
  seenParseKeys.clear()
}

export function emitRowRenderProfile(event: RowRenderProfileEvent): void {
  activeHooks.onRowRender?.(event)
}

export function emitParseCacheTrace(input: ParseCacheTraceInput): ParseCacheTraceEvent {
  const hit = seenParseKeys.has(input.key)
  seenParseKeys.add(input.key)
  const event: ParseCacheTraceEvent = {
    ...input,
    hit,
  }
  activeHooks.onParseCacheTrace?.(event)
  return event
}
