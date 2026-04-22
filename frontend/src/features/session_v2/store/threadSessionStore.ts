import { create } from 'zustand'
import type { SessionEventEnvelope, SessionItem, SessionThread, SessionTurn } from '../contracts'
import { applySessionEvent, type SessionProjectionState } from '../state/applySessionEvent'

export type StreamState = {
  connectedByThread: Record<string, boolean>
  reconnectCountByThread: Record<string, number>
}

type ThreadSessionStoreState = SessionProjectionState & {
  activeThreadId: string | null
  streamState: StreamState
  setThreadList: (threads: SessionThread[]) => void
  upsertThread: (thread: SessionThread) => void
  setActiveThreadId: (threadId: string | null) => void
  setThreadTurns: (threadId: string, turns: SessionTurn[]) => void
  setItemsForTurn: (threadId: string, turnId: string, items: SessionItem[]) => void
  applyEvent: (envelope: SessionEventEnvelope) => void
  markStreamConnected: (threadId: string) => void
  markStreamDisconnected: (threadId: string) => void
  markStreamReconnect: (threadId: string) => void
  clearGapDetected: (threadId: string) => void
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

const VALID_ITEM_KINDS: ReadonlyArray<SessionItem['kind']> = [
  'userMessage',
  'agentMessage',
  'reasoning',
  'plan',
  'commandExecution',
  'fileChange',
  'userInput',
  'error',
]

const VALID_ITEM_STATUS: ReadonlyArray<SessionItem['status']> = ['inProgress', 'completed', 'failed']

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object'
}

function kindFromType(type: unknown): SessionItem['kind'] | null {
  if (type === 'userMessage') {
    return 'userMessage'
  }
  if (type === 'agentMessage') {
    return 'agentMessage'
  }
  if (type === 'reasoning') {
    return 'reasoning'
  }
  if (type === 'plan') {
    return 'plan'
  }
  if (type === 'commandExecution') {
    return 'commandExecution'
  }
  if (type === 'fileChange') {
    return 'fileChange'
  }
  if (type === 'userInput') {
    return 'userInput'
  }
  if (type === 'error') {
    return 'error'
  }
  return null
}

function normalizeItemKindValue(
  explicitKind: unknown,
  payload: Record<string, unknown>,
): SessionItem['kind'] {
  if (VALID_ITEM_KINDS.includes(explicitKind as SessionItem['kind'])) {
    return explicitKind as SessionItem['kind']
  }
  const payloadKind = payload.kind
  if (VALID_ITEM_KINDS.includes(payloadKind as SessionItem['kind'])) {
    return payloadKind as SessionItem['kind']
  }
  return kindFromType(payload.type) ?? 'agentMessage'
}

function normalizeItemStatusValue(
  explicitStatus: unknown,
  payload: Record<string, unknown>,
): SessionItem['status'] {
  if (VALID_ITEM_STATUS.includes(explicitStatus as SessionItem['status'])) {
    return explicitStatus as SessionItem['status']
  }
  const candidate = String(payload.status ?? explicitStatus ?? '').trim()
  if (!candidate) {
    return 'inProgress'
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
  return 'inProgress'
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
  delete fallback.status
  delete fallback.createdAtMs
  delete fallback.updatedAtMs
  delete fallback.payload
  return fallback
}

function normalizeItemForStore(
  value: SessionItem,
  options: {
    threadId: string
    turnId: string
    fallbackId: string
  },
): SessionItem {
  const { threadId, turnId, fallbackId } = options
  const item = value && typeof value === 'object' ? (value as Partial<SessionItem>) : {}
  const payload = normalizeItemPayload(item)
  const kind = normalizeItemKindValue(item.kind, payload)
  const status = normalizeItemStatusValue(item.status, payload)
  return {
    id: typeof item.id === 'string' && item.id.trim() ? item.id : fallbackId,
    threadId: typeof item.threadId === 'string' && item.threadId.trim() ? item.threadId : threadId,
    turnId: typeof item.turnId === 'string' && item.turnId.trim() ? item.turnId : turnId,
    kind,
    status,
    createdAtMs: typeof item.createdAtMs === 'number' ? item.createdAtMs : Date.now(),
    updatedAtMs: typeof item.updatedAtMs === 'number' ? item.updatedAtMs : Date.now(),
    payload,
  }
}

function normalizeItemsForTurn(threadId: string, turnId: string, items: SessionItem[] | undefined): SessionItem[] {
  if (!Array.isArray(items)) {
    return []
  }
  return items
    .filter((item): item is SessionItem => Boolean(item && typeof item === 'object'))
    .map((item, itemIndex) =>
      normalizeItemForStore(item, {
        threadId,
        turnId,
        fallbackId: `${turnId}:item-${itemIndex}`,
      }),
    )
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
    const normalizedItems = normalizeItemsForTurn(threadId, turn.id, turn.items)
    return {
      ...turn,
      threadId,
      items: normalizedItems,
    }
  })
  return [...normalized].sort(compareTurnsChronologically)
}

export const useThreadSessionStore = create<ThreadSessionStoreState>((set) => ({
  ...initialState,
  activeThreadId: null,
  streamState: initialStreamState,
  setThreadList(threads) {
    const threadsById: Record<string, SessionThread> = {}
    const threadOrder: string[] = []
    const threadStatus: Record<string, SessionProjectionState['threadStatus'][string]> = {}
    for (const thread of threads) {
      threadsById[thread.id] = thread
      threadOrder.push(thread.id)
      threadStatus[thread.id] = thread.status
    }
    set((state) => ({
      ...state,
      threadsById: { ...state.threadsById, ...threadsById },
      threadOrder: [...new Set([...state.threadOrder, ...threadOrder])],
      threadStatus: { ...state.threadStatus, ...threadStatus },
    }))
  },
  upsertThread(thread) {
    set((state) => ({
      ...state,
      threadsById: { ...state.threadsById, [thread.id]: thread },
      threadOrder: state.threadOrder.includes(thread.id) ? state.threadOrder : [...state.threadOrder, thread.id],
      threadStatus: { ...state.threadStatus, [thread.id]: thread.status },
    }))
  },
  setActiveThreadId(threadId) {
    set({ activeThreadId: threadId })
  },
  setThreadTurns(threadId, turns) {
    const normalizedTurns = normalizeTurnsForThread(threadId, turns)
    const turnsByThread = { [threadId]: normalizedTurns }
    const nextItemsByTurn: Record<string, SessionItem[]> = {}
    for (const turn of normalizedTurns) {
      const key = `${threadId}:${turn.id}`
      nextItemsByTurn[key] = normalizeItemsForTurn(threadId, turn.id, turn.items)
    }
    set((state) => ({
      ...state,
      turnsByThread: { ...state.turnsByThread, ...turnsByThread },
      itemsByTurn: { ...state.itemsByTurn, ...nextItemsByTurn },
    }))
  },
  setItemsForTurn(threadId, turnId, items) {
    const key = `${threadId}:${turnId}`
    const normalizedItems = normalizeItemsForTurn(threadId, turnId, items)
    set((state) => ({
      ...state,
      itemsByTurn: { ...state.itemsByTurn, [key]: normalizedItems },
    }))
  },
  applyEvent(envelope) {
    set((state) => applySessionEvent(state, envelope))
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
  clear() {
    set({
      ...initialState,
      activeThreadId: null,
      streamState: initialStreamState,
    })
  },
}))
