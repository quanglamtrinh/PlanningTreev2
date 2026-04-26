import { create } from 'zustand'
import { isItemKind } from '../contracts'
import type { ItemKind, SessionEventEnvelope, SessionItem, SessionThread, SessionTurn } from '../contracts'
import {
  applySessionEvent,
  applySessionEventsBatch,
  type SessionProjectionState,
} from '../state/applySessionEvent'

export type StreamState = {
  connectedByThread: Record<string, boolean>
  reconnectCountByThread: Record<string, number>
}

export type SetThreadTurnsOptions = {
  mode?: 'merge' | 'replace'
}

export type ThreadSessionStoreState = SessionProjectionState & {
  activeThreadId: string | null
  streamState: StreamState
  setThreadList: (threads: SessionThread[]) => void
  upsertThread: (thread: SessionThread, options?: { preserveUpdatedAt?: boolean }) => void
  markThreadActivity: (threadId: string, updatedAt?: number) => void
  setActiveThreadId: (threadId: string | null) => void
  setThreadTurns: (threadId: string, turns: SessionTurn[], options?: SetThreadTurnsOptions) => void
  setItemsForTurn: (threadId: string, turnId: string, items: SessionItem[]) => void
  applyEvent: (envelope: SessionEventEnvelope) => void
  applyEventsBatch: (envelopes: SessionEventEnvelope[]) => void
  markStreamConnected: (threadId: string) => void
  markStreamDisconnected: (threadId: string) => void
  markStreamReconnect: (threadId: string) => void
  clearGapDetected: (threadId: string) => void
  /** Align last event seq/id with server journal after hydrate (avoids stream gap-detect loops). */
  setReplayCursor: (threadId: string, lastEventSeq: number, lastEventId: string | null) => void
  resetReplayCursor: (threadId: string) => void
  clear: () => void
}

const initialState: SessionProjectionState = {
  threadsById: {},
  threadOrder: [],
  turnsByThread: {},
  itemsByTurn: {},
  lastEventSeqByThread: {},
  lastEventIdByThread: {},
  gapDetectedByThread: {},
  threadStatus: {},
  tokenUsageByThread: {},
}

const initialStreamState: StreamState = {
  connectedByThread: {},
  reconnectCountByThread: {},
}

const VALID_ITEM_STATUS: ReadonlyArray<SessionItem['status']> = ['inProgress', 'completed', 'failed']

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object'
}

function toNonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const text = value.trim()
  return text.length > 0 ? text : null
}

function normalizeItemKindValue(
  explicitKind: unknown,
  payload: Record<string, unknown>,
): { kind: string; normalizedKind: ItemKind | null } {
  const payloadType = toNonEmptyString(payload.type)
  if (!explicitKind && payloadType === 'message') {
    const role = toNonEmptyString(payload.role)
    if (role === 'user') {
      return { kind: 'message', normalizedKind: 'userMessage' }
    }
    if (role === 'assistant') {
      return { kind: 'message', normalizedKind: 'agentMessage' }
    }
    return { kind: 'message', normalizedKind: null }
  }
  const rawKind =
    toNonEmptyString(explicitKind) ??
    toNonEmptyString(payload.kind) ??
    payloadType ??
    'unknown'
  const normalizedKind =
    (isItemKind(explicitKind) ? explicitKind : null) ??
    (isItemKind(payload.kind) ? payload.kind : null) ??
    (isItemKind(payload.type) ? payload.type : null)
  return { kind: rawKind, normalizedKind }
}

function normalizeItemStatusValue(
  explicitStatus: unknown,
  payload: Record<string, unknown>,
  fallbackStatus: SessionItem['status'] = 'inProgress',
): SessionItem['status'] {
  if (VALID_ITEM_STATUS.includes(explicitStatus as SessionItem['status'])) {
    return explicitStatus as SessionItem['status']
  }
  const candidate = String(payload.status ?? explicitStatus ?? '').trim()
  if (!candidate) {
    return fallbackStatus
  }
  if (
    candidate === 'inProgress' ||
    candidate === 'running' ||
    candidate === 'requested' ||
    candidate === 'answer_submitted'
  ) {
    return 'inProgress'
  }
  if (
    candidate === 'completed' ||
    candidate === 'approved' ||
    candidate === 'answered' ||
    candidate === 'success'
  ) {
    return 'completed'
  }
  if (
    candidate === 'failed' ||
    candidate === 'declined' ||
    candidate === 'rejected' ||
    candidate === 'denied' ||
    candidate === 'aborted' ||
    candidate === 'cancelled' ||
    candidate === 'canceled' ||
    candidate === 'expired' ||
    candidate === 'stale'
  ) {
    return 'failed'
  }
  return fallbackStatus
}

function normalizeItemPayload(item: Partial<SessionItem>): Record<string, unknown> {
  if (isRecord(item.payload)) {
    return { ...(item.payload as Record<string, unknown>) }
  }
  const fallback = { ...item } as Record<string, unknown>
  delete fallback.id
  delete fallback.threadId
  delete fallback.turnId
  delete fallback.kind
  delete fallback.normalizedKind
  delete fallback.status
  delete fallback.createdAtMs
  delete fallback.updatedAtMs
  delete fallback.payload
  delete fallback.rawItem
  delete fallback.rawParams
  return fallback
}

function resolveItemTimestampMs(candidates: unknown[], fallback: number): number {
  for (const candidate of candidates) {
    const parsed = parseTimestampMs(candidate)
    if (parsed !== null) {
      return parsed
    }
  }
  return fallback
}

function resolveItemCreatedTimestampMs(item: SessionItem): number | null {
  const payload = isRecord(item.payload) ? item.payload : {}
  return (
    parseTimestampMs(item.createdAtMs) ??
    parseTimestampMs(payload.createdAtMs) ??
    parseTimestampMs(payload.createdAt) ??
    parseTimestampMs(payload.occurredAtMs) ??
    parseTimestampMs(payload.timestamp)
  )
}

function resolveItemUpdatedTimestampMs(item: SessionItem): number | null {
  const payload = isRecord(item.payload) ? item.payload : {}
  return (
    parseTimestampMs(item.updatedAtMs) ??
    parseTimestampMs(payload.updatedAtMs) ??
    parseTimestampMs(payload.updatedAt) ??
    resolveItemCreatedTimestampMs(item)
  )
}

function normalizeItemForStore(
  value: SessionItem,
  options: {
    threadId: string
    turnId: string
    fallbackId: string
    fallbackStatus: SessionItem['status']
  },
): SessionItem {
  const { threadId, turnId, fallbackId, fallbackStatus } = options
  const item = value && typeof value === 'object' ? (value as Partial<SessionItem>) : {}
  const itemRecord = item as unknown as Record<string, unknown>
  const payload = normalizeItemPayload(item)
  const { kind, normalizedKind } = normalizeItemKindValue(item.kind, payload)
  const status = normalizeItemStatusValue(item.status, payload, fallbackStatus)
  const now = Date.now()
  const createdAtMs = resolveItemTimestampMs(
    [item.createdAtMs, itemRecord.createdAt, payload.createdAtMs, payload.createdAt, payload.occurredAtMs, payload.timestamp],
    now,
  )
  const updatedAtMs = resolveItemTimestampMs(
    [item.updatedAtMs, itemRecord.updatedAt, payload.updatedAtMs, payload.updatedAt, createdAtMs],
    createdAtMs,
  )
  const normalized: SessionItem = {
    id: typeof item.id === 'string' && item.id.trim() ? item.id : fallbackId,
    threadId: typeof item.threadId === 'string' && item.threadId.trim() ? item.threadId : threadId,
    turnId: typeof item.turnId === 'string' && item.turnId.trim() ? item.turnId : turnId,
    kind,
    normalizedKind,
    status,
    createdAtMs,
    updatedAtMs,
    payload,
  }
  if (isRecord(item.rawItem)) {
    normalized.rawItem = { ...item.rawItem }
  } else if (normalizedKind === null && isRecord(itemRecord)) {
    normalized.rawItem = { ...itemRecord }
  }
  if (isRecord(item.rawParams)) {
    normalized.rawParams = { ...item.rawParams }
  }
  return normalized
}

function normalizeItemsForTurnByStatus(
  threadId: string,
  turnId: string,
  items: SessionItem[] | undefined,
  turnStatus: SessionTurn['status'] | undefined,
): SessionItem[] {
  if (!Array.isArray(items)) {
    return []
  }
  const fallbackStatus: SessionItem['status'] = (
    turnStatus === 'completed'
      ? 'completed'
      : turnStatus === 'failed' || turnStatus === 'interrupted'
        ? 'failed'
        : 'inProgress'
  )
  const normalized: SessionItem[] = []
  const indexById = new Map<string, number>()
  const firstSeenById = new Map<string, number>()
  items
    .filter((item): item is SessionItem => Boolean(item && typeof item === 'object'))
    .forEach((item, itemIndex) => {
      const nextItem = normalizeItemForStore(item, {
        threadId,
        turnId,
        fallbackId: `${turnId}:item-${itemIndex}`,
        fallbackStatus,
      })
      const existingIndex = indexById.get(nextItem.id)
      if (existingIndex === undefined) {
        indexById.set(nextItem.id, normalized.length)
        firstSeenById.set(nextItem.id, itemIndex)
        normalized.push(nextItem)
        return
      }
      const existing = normalized[existingIndex]
      normalized[existingIndex] = {
        ...existing,
        ...nextItem,
        createdAtMs: existing.createdAtMs,
      }
    })
  return [...normalized].sort((left, right) => {
    const leftCreated = resolveItemCreatedTimestampMs(left)
    const rightCreated = resolveItemCreatedTimestampMs(right)
    if (leftCreated !== null && rightCreated !== null && leftCreated !== rightCreated) {
      return leftCreated - rightCreated
    }
    if (leftCreated !== null && rightCreated === null) {
      return -1
    }
    if (leftCreated === null && rightCreated !== null) {
      return 1
    }

    const leftUpdated = resolveItemUpdatedTimestampMs(left)
    const rightUpdated = resolveItemUpdatedTimestampMs(right)
    if (leftUpdated !== null && rightUpdated !== null && leftUpdated !== rightUpdated) {
      return leftUpdated - rightUpdated
    }
    if (leftUpdated !== null && rightUpdated === null) {
      return -1
    }
    if (leftUpdated === null && rightUpdated !== null) {
      return 1
    }

    return (firstSeenById.get(left.id) ?? 0) - (firstSeenById.get(right.id) ?? 0)
  })
}

function parseTimestampMs(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Date.parse(value)
    if (Number.isFinite(parsed) && parsed >= 0) {
      return parsed
    }
  }
  return null
}

function compareTurnsChronologically(left: SessionTurn, right: SessionTurn): number {
  const leftRecord = left as unknown as Record<string, unknown>
  const rightRecord = right as unknown as Record<string, unknown>

  const leftTimestamp =
    parseTimestampMs(left.startedAtMs) ??
    parseTimestampMs(leftRecord.startedAt) ??
    parseTimestampMs(left.completedAtMs) ??
    parseTimestampMs(leftRecord.completedAt)
  const rightTimestamp =
    parseTimestampMs(right.startedAtMs) ??
    parseTimestampMs(rightRecord.startedAt) ??
    parseTimestampMs(right.completedAtMs) ??
    parseTimestampMs(rightRecord.completedAt)

  if (leftTimestamp !== null && rightTimestamp !== null && leftTimestamp !== rightTimestamp) {
    return leftTimestamp - rightTimestamp
  }
  if (leftTimestamp !== null && rightTimestamp === null) {
    return -1
  }
  if (leftTimestamp === null && rightTimestamp !== null) {
    return 1
  }
  return left.id.localeCompare(right.id)
}

function normalizeTurnsForThread(threadId: string, turns: SessionTurn[]): SessionTurn[] {
  const normalized = turns.map((turn) => {
    const normalizedItems = normalizeItemsForTurnByStatus(threadId, turn.id, turn.items, turn.status)
    return {
      ...turn,
      threadId,
      items: normalizedItems,
    }
  })
  return [...normalized].sort(compareTurnsChronologically)
}

function isTerminalTurnStatus(status: SessionTurn['status']): boolean {
  return status === 'completed' || status === 'failed' || status === 'interrupted'
}

function mergeTurnForStore(existing: SessionTurn | undefined, incoming: SessionTurn): SessionTurn {
  if (!existing) {
    return incoming
  }
  const preserveExistingTerminal = isTerminalTurnStatus(existing.status) && !isTerminalTurnStatus(incoming.status)
  const nextStatus = preserveExistingTerminal ? existing.status : incoming.status
  const nextLastCodexStatus = preserveExistingTerminal
    ? existing.lastCodexStatus
    : incoming.lastCodexStatus
  const nextCompletedAtMs = preserveExistingTerminal
    ? existing.completedAtMs ?? incoming.completedAtMs
    : incoming.completedAtMs ?? existing.completedAtMs
  const nextError = preserveExistingTerminal
    ? existing.error ?? incoming.error
    : incoming.error ?? existing.error
  const incomingItems = Array.isArray(incoming.items) ? incoming.items : []
  const existingItems = Array.isArray(existing.items) ? existing.items : []
  return {
    ...existing,
    ...incoming,
    status: nextStatus,
    lastCodexStatus: nextLastCodexStatus,
    completedAtMs: nextCompletedAtMs,
    items: incomingItems.length > 0 ? incomingItems : existingItems,
    error: nextError,
  }
}

function mergeItemsForTurn(existing: SessionItem[] | undefined, incoming: SessionItem[]): SessionItem[] {
  if (!Array.isArray(existing) || existing.length === 0) {
    return incoming
  }
  if (incoming.length === 0) {
    return existing
  }
  const byId = new Map<string, SessionItem>()
  const order: string[] = []
  for (const item of existing) {
    byId.set(item.id, item)
    order.push(item.id)
  }
  for (const item of incoming) {
    const previous = byId.get(item.id)
    if (!previous) {
      byId.set(item.id, item)
      order.push(item.id)
      continue
    }
    const shouldPreserveCompleted = previous.status === 'completed' && item.status !== 'completed'
    byId.set(
      item.id,
      shouldPreserveCompleted
        ? previous
        : {
            ...previous,
            ...item,
            createdAtMs: previous.createdAtMs,
          },
    )
  }
  return order.map((itemId) => byId.get(itemId)).filter((item): item is SessionItem => Boolean(item))
}

function areStringArraysEqual(left: string[] | undefined, right: string[] | undefined): boolean {
  if (left === right) {
    return true
  }
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
    return false
  }
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) {
      return false
    }
  }
  return true
}

function areThreadStatusEqual(left: SessionThread['status'], right: SessionThread['status']): boolean {
  if (left === right) {
    return true
  }
  if (left.type !== right.type) {
    return false
  }
  if (left.type !== 'active' || right.type !== 'active') {
    return true
  }
  return areStringArraysEqual(left.activeFlags, right.activeFlags)
}

function areThreadMetadataEqual(
  left: SessionThread['metadata'],
  right: SessionThread['metadata'],
): boolean {
  if (left === right) {
    return true
  }
  if (!left && !right) {
    return true
  }
  if (!left || !right) {
    return false
  }
  const leftKeys = Object.keys(left)
  const rightKeys = Object.keys(right)
  if (leftKeys.length !== rightKeys.length) {
    return false
  }
  for (const key of leftKeys) {
    if (!Object.prototype.hasOwnProperty.call(right, key)) {
      return false
    }
    if (!areUnknownValuesEqual(left[key], right[key])) {
      return false
    }
  }
  return true
}

function areUnknownValuesEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) {
    return true
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
      return false
    }
    for (let index = 0; index < left.length; index += 1) {
      if (!areUnknownValuesEqual(left[index], right[index])) {
        return false
      }
    }
    return true
  }
  if (!isRecord(left) || !isRecord(right)) {
    return false
  }
  const leftKeys = Object.keys(left)
  const rightKeys = Object.keys(right)
  if (leftKeys.length !== rightKeys.length) {
    return false
  }
  for (const key of leftKeys) {
    if (!Object.prototype.hasOwnProperty.call(right, key)) {
      return false
    }
    if (!areUnknownValuesEqual(left[key], right[key])) {
      return false
    }
  }
  return true
}

function areThreadTurnsEquivalent(left: SessionTurn[] | undefined, right: SessionTurn[] | undefined): boolean {
  if (left === right) {
    return true
  }
  const leftTurns = Array.isArray(left) ? left : []
  const rightTurns = Array.isArray(right) ? right : []
  return leftTurns.length === 0 && rightTurns.length === 0
}

function areThreadsEquivalent(left: SessionThread, right: SessionThread): boolean {
  return (
    left.id === right.id &&
    left.name === right.name &&
    left.preview === right.preview &&
    left.model === right.model &&
    left.modelProvider === right.modelProvider &&
    left.cwd === right.cwd &&
    left.path === right.path &&
    left.ephemeral === right.ephemeral &&
    left.archived === right.archived &&
    left.createdAt === right.createdAt &&
    left.updatedAt === right.updatedAt &&
    areThreadStatusEqual(left.status, right.status) &&
    areThreadMetadataEqual(left.metadata, right.metadata) &&
    areThreadTurnsEquivalent(left.turns, right.turns)
  )
}

function mergeThreadForStore(
  existing: SessionThread | undefined,
  incoming: SessionThread,
  options?: { preserveUpdatedAt?: boolean },
): SessionThread {
  const updatedAt = options?.preserveUpdatedAt && existing ? existing.updatedAt : incoming.updatedAt
  const status = existing && areThreadStatusEqual(existing.status, incoming.status) ? existing.status : incoming.status
  const metadata =
    existing && areThreadMetadataEqual(existing.metadata, incoming.metadata) ? existing.metadata : incoming.metadata
  const turns = existing ? existing.turns : incoming.turns
  return {
    ...incoming,
    updatedAt,
    status,
    metadata,
    turns,
  }
}

function areThreadOrdersEqual(left: string[], right: string[]): boolean {
  if (left === right) {
    return true
  }
  if (left.length !== right.length) {
    return false
  }
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) {
      return false
    }
  }
  return true
}

function parseThreadTimestampMs(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Date.parse(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return 0
}

export function selectThreadsSorted(state: ThreadSessionStoreState): SessionThread[] {
  const indexById = new Map<string, number>()
  state.threadOrder.forEach((threadId, index) => {
    indexById.set(threadId, index)
  })
  return state.threadOrder
    .map((threadId) => state.threadsById[threadId])
    .filter((thread): thread is SessionThread => Boolean(thread))
    .sort((left, right) => {
      const diff = parseThreadTimestampMs(right.updatedAt) - parseThreadTimestampMs(left.updatedAt)
      if (diff !== 0) {
        return diff
      }
      return (indexById.get(left.id) ?? 0) - (indexById.get(right.id) ?? 0)
    })
}

export function selectActiveThread(state: ThreadSessionStoreState): SessionThread | null {
  if (!state.activeThreadId) {
    return null
  }
  return state.threadsById[state.activeThreadId] ?? null
}

export function selectActiveTurns(state: ThreadSessionStoreState): SessionTurn[] {
  if (!state.activeThreadId) {
    return []
  }
  return state.turnsByThread[state.activeThreadId] ?? []
}

export function selectActiveRunningTurn(state: ThreadSessionStoreState): SessionTurn | null {
  const turns = selectActiveTurns(state)
  const running = [...turns]
    .reverse()
    .find((turn) => turn.status === 'inProgress' || turn.status === 'waitingUserInput')
  return running ?? null
}

export function selectActiveItemsByTurn(state: ThreadSessionStoreState): Record<string, SessionItem[]> {
  const activeThreadId = state.activeThreadId
  if (!activeThreadId) {
    return {}
  }
  const turns = state.turnsByThread[activeThreadId] ?? []
  const rows: Record<string, SessionItem[]> = {}
  for (const turn of turns) {
    const key = `${activeThreadId}:${turn.id}`
    rows[key] = state.itemsByTurn[key] ?? []
  }
  return rows
}

export function selectActiveTranscriptModel(state: ThreadSessionStoreState): {
  threadId: string | null
  turns: SessionTurn[]
  itemsByTurn: Record<string, SessionItem[]>
} {
  return {
    threadId: state.activeThreadId,
    turns: selectActiveTurns(state),
    itemsByTurn: selectActiveItemsByTurn(state),
  }
}

export const useThreadSessionStore = create<ThreadSessionStoreState>((set) => ({
  ...initialState,
  activeThreadId: null,
  streamState: initialStreamState,
  setThreadList(threads) {
    set((state) => {
      let nextThreadsById = state.threadsById
      let nextThreadStatus = state.threadStatus
      const incomingOrder: string[] = []
      for (const thread of threads) {
        incomingOrder.push(thread.id)
        const existing = state.threadsById[thread.id]
        const merged = mergeThreadForStore(existing, thread)
        if (!existing || !areThreadsEquivalent(existing, merged)) {
          if (nextThreadsById === state.threadsById) {
            nextThreadsById = { ...state.threadsById }
          }
          nextThreadsById[thread.id] = merged
        }
        if (state.threadStatus[thread.id] !== merged.status) {
          if (nextThreadStatus === state.threadStatus) {
            nextThreadStatus = { ...state.threadStatus }
          }
          nextThreadStatus[thread.id] = merged.status
        }
      }

      const incomingOrderSet = new Set(incomingOrder)
      const nextThreadOrderCandidate = [
        ...incomingOrder,
        ...state.threadOrder.filter((threadId) => !incomingOrderSet.has(threadId)),
      ]
      const nextThreadOrder = areThreadOrdersEqual(state.threadOrder, nextThreadOrderCandidate)
        ? state.threadOrder
        : nextThreadOrderCandidate

      if (
        nextThreadsById === state.threadsById &&
        nextThreadStatus === state.threadStatus &&
        nextThreadOrder === state.threadOrder
      ) {
        return state
      }

      return {
        ...state,
        threadsById: nextThreadsById,
        threadOrder: nextThreadOrder,
        threadStatus: nextThreadStatus,
      }
    })
  },
  upsertThread(thread, options) {
    set((state) => {
      const existing = state.threadsById[thread.id]
      const merged = mergeThreadForStore(existing, thread, options)
      const hasThreadInOrder = state.threadOrder.includes(thread.id)
      const statusChanged = state.threadStatus[thread.id] !== merged.status
      const threadChanged = !existing || !areThreadsEquivalent(existing, merged)

      if (!threadChanged && hasThreadInOrder && !statusChanged) {
        return state
      }

      return {
        ...state,
        threadsById: threadChanged ? { ...state.threadsById, [thread.id]: merged } : state.threadsById,
        threadOrder: hasThreadInOrder ? state.threadOrder : [...state.threadOrder, thread.id],
        threadStatus: statusChanged ? { ...state.threadStatus, [thread.id]: merged.status } : state.threadStatus,
      }
    })
  },
  markThreadActivity(threadId, updatedAt = Date.now()) {
    set((state) => {
      const thread = state.threadsById[threadId]
      if (!thread) {
        return state
      }
      return {
        ...state,
        threadsById: {
          ...state.threadsById,
          [threadId]: {
            ...thread,
            updatedAt: Math.max(thread.updatedAt, updatedAt),
          },
        },
      }
    })
  },
  setActiveThreadId(threadId) {
    set({ activeThreadId: threadId })
  },
  setThreadTurns(threadId, turns, options) {
    const normalizedTurns = normalizeTurnsForThread(threadId, turns)
    const mode = options?.mode === 'replace' ? 'replace' : 'merge'
    set((state) => {
      let nextTurns: SessionTurn[]
      let nextItemsByTurn: Record<string, SessionItem[]>

      if (mode === 'replace') {
        nextTurns = normalizedTurns
        const prefix = `${threadId}:`
        nextItemsByTurn = {}
        for (const [key, items] of Object.entries(state.itemsByTurn)) {
          if (key.startsWith(prefix)) {
            continue
          }
          nextItemsByTurn[key] = items
        }
        for (const turn of nextTurns) {
          const key = `${threadId}:${turn.id}`
          nextItemsByTurn[key] = normalizeItemsForTurnByStatus(threadId, turn.id, turn.items, turn.status)
        }
      } else {
        const existingTurns = state.turnsByThread[threadId] ?? []
        const mergedById = new Map<string, SessionTurn>()
        const order: string[] = []

        for (const turn of existingTurns) {
          mergedById.set(turn.id, turn)
          order.push(turn.id)
        }
        for (const turn of normalizedTurns) {
          const merged = mergeTurnForStore(mergedById.get(turn.id), turn)
          mergedById.set(turn.id, merged)
          if (!order.includes(turn.id)) {
            order.push(turn.id)
          }
        }

        nextTurns = order
          .map((turnId) => mergedById.get(turnId))
          .filter((turn): turn is SessionTurn => Boolean(turn))
          .sort(compareTurnsChronologically)

        nextItemsByTurn = { ...state.itemsByTurn }
        for (const turn of nextTurns) {
          const key = `${threadId}:${turn.id}`
          const hydratedItems = normalizeItemsForTurnByStatus(threadId, turn.id, turn.items, turn.status)
          nextItemsByTurn[key] = mergeItemsForTurn(state.itemsByTurn[key], hydratedItems)
        }
      }

      return {
        ...state,
        turnsByThread: { ...state.turnsByThread, [threadId]: nextTurns },
        itemsByTurn: nextItemsByTurn,
      }
    })
  },
  setItemsForTurn(threadId, turnId, items) {
    set((state) => ({
      ...state,
      itemsByTurn: {
        ...state.itemsByTurn,
        [`${threadId}:${turnId}`]: normalizeItemsForTurnByStatus(
          threadId,
          turnId,
          items,
          state.turnsByThread[threadId]?.find((turn) => turn.id === turnId)?.status,
        ),
      },
    }))
  },
  applyEvent(envelope) {
    set((state) => applySessionEvent(state, envelope))
  },
  applyEventsBatch(envelopes) {
    if (!Array.isArray(envelopes) || envelopes.length === 0) {
      return
    }
    set((state) => applySessionEventsBatch(state, envelopes))
  },
  markStreamConnected(threadId) {
    set((state) => ({
      streamState: {
        ...state.streamState,
        connectedByThread: { ...state.streamState.connectedByThread, [threadId]: true },
      },
    }))
  },
  markStreamDisconnected(threadId) {
    set((state) => ({
      streamState: {
        ...state.streamState,
        connectedByThread: { ...state.streamState.connectedByThread, [threadId]: false },
      },
    }))
  },
  markStreamReconnect(threadId) {
    set((state) => ({
      streamState: {
        ...state.streamState,
        reconnectCountByThread: {
          ...state.streamState.reconnectCountByThread,
          [threadId]: (state.streamState.reconnectCountByThread[threadId] ?? 0) + 1,
        },
      },
    }))
  },
  clearGapDetected(threadId) {
    set((state) => ({
      gapDetectedByThread: { ...state.gapDetectedByThread, [threadId]: false },
    }))
  },
  setReplayCursor(threadId, lastEventSeq, lastEventId) {
    const tid = String(threadId ?? '').trim()
    if (!tid) {
      return
    }
    set((state) => {
      const nextSeq = { ...state.lastEventSeqByThread }
      const nextId = { ...state.lastEventIdByThread }
      const nextGap = { ...state.gapDetectedByThread }
      if (lastEventSeq <= 0 && (lastEventId == null || String(lastEventId).trim() === '')) {
        delete nextSeq[tid]
        delete nextId[tid]
      } else {
        const seq = Math.max(0, lastEventSeq)
        nextSeq[tid] = seq
        if (lastEventId != null && String(lastEventId).trim() !== '') {
          nextId[tid] = String(lastEventId).trim()
        } else {
          nextId[tid] = `${tid}:${seq}`
        }
      }
      nextGap[tid] = false
      return {
        ...state,
        lastEventSeqByThread: nextSeq,
        lastEventIdByThread: nextId,
        gapDetectedByThread: nextGap,
      }
    })
  },
  resetReplayCursor(threadId) {
    set((state) => {
      const nextLastEventSeqByThread = { ...state.lastEventSeqByThread }
      const nextLastEventIdByThread = { ...state.lastEventIdByThread }
      const nextGapDetectedByThread = { ...state.gapDetectedByThread, [threadId]: false }
      delete nextLastEventSeqByThread[threadId]
      delete nextLastEventIdByThread[threadId]
      return {
        ...state,
        lastEventSeqByThread: nextLastEventSeqByThread,
        lastEventIdByThread: nextLastEventIdByThread,
        gapDetectedByThread: nextGapDetectedByThread,
      }
    })
  },
  clear() {
    set({
      ...initialState,
      activeThreadId: null,
      streamState: initialStreamState,
    })
  },
}))
