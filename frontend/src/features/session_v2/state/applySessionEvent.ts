import type {
  ItemKind,
  ItemStatus,
  SessionEventEnvelope,
  SessionErrorCode,
  SessionItem,
  SessionThread,
  SessionTurn,
  ThreadStatus,
  TurnCodexStatus,
  TurnRuntimeStatus,
} from '../contracts'

export type SessionProjectionState = {
  threadsById: Record<string, SessionThread>
  threadOrder: string[]
  turnsByThread: Record<string, SessionTurn[]>
  itemsByTurn: Record<string, SessionItem[]>
  lastEventSeqByThread: Record<string, number>
  lastEventIdByThread: Record<string, string>
  gapDetectedByThread: Record<string, boolean>
  threadStatus: Record<string, ThreadStatus>
  tokenUsageByThread: Record<string, Record<string, unknown> | null>
}

function normalizeThreadStatus(value: unknown): ThreadStatus {
  if (!value || typeof value !== 'object') {
    return { type: 'idle' }
  }
  const parsed = value as { type?: string; activeFlags?: unknown }
  if (parsed.type === 'active') {
    const flags = Array.isArray(parsed.activeFlags) ? parsed.activeFlags.filter((flag): flag is string => typeof flag === 'string') : []
    return { type: 'active', activeFlags: flags }
  }
  if (parsed.type === 'notLoaded' || parsed.type === 'idle' || parsed.type === 'systemError') {
    return { type: parsed.type }
  }
  return { type: 'idle' }
}

function normalizeTurnStatus(value: unknown): TurnRuntimeStatus {
  if (
    value === 'idle' ||
    value === 'inProgress' ||
    value === 'waitingUserInput' ||
    value === 'completed' ||
    value === 'failed' ||
    value === 'interrupted'
  ) {
    return value
  }
  return 'inProgress'
}

function normalizeCodexStatus(value: unknown): TurnCodexStatus | null {
  if (value === 'inProgress' || value === 'completed' || value === 'failed' || value === 'interrupted') {
    return value
  }
  return null
}

function normalizeSessionErrorCode(value: unknown): SessionErrorCode {
  if (
    value === 'ERR_SESSION_NOT_INITIALIZED' ||
    value === 'ERR_CURSOR_INVALID' ||
    value === 'ERR_CURSOR_EXPIRED' ||
    value === 'ERR_TURN_TERMINAL' ||
    value === 'ERR_TURN_NOT_STEERABLE' ||
    value === 'ERR_ACTIVE_TURN_MISMATCH' ||
    value === 'ERR_REQUEST_STALE' ||
    value === 'ERR_IDEMPOTENCY_PAYLOAD_MISMATCH' ||
    value === 'ERR_PROVIDER_UNAVAILABLE' ||
    value === 'ERR_SANDBOX_FAILURE' ||
    value === 'ERR_INTERNAL'
  ) {
    return value
  }
  return 'ERR_INTERNAL'
}

function normalizeItemKind(value: unknown): ItemKind {
  if (
    value === 'userMessage' ||
    value === 'agentMessage' ||
    value === 'reasoning' ||
    value === 'plan' ||
    value === 'commandExecution' ||
    value === 'fileChange' ||
    value === 'userInput' ||
    value === 'error'
  ) {
    return value
  }
  return 'agentMessage'
}

function normalizeItemStatus(value: unknown): ItemStatus {
  if (value === 'inProgress' || value === 'completed' || value === 'failed') {
    return value
  }
  return 'inProgress'
}

function ensureThread(
  state: SessionProjectionState,
  threadId: string,
): SessionThread {
  const existing = state.threadsById[threadId]
  if (existing) {
    return existing
  }
  const fallback: SessionThread = {
    id: threadId,
    name: null,
    modelProvider: 'unknown',
    cwd: '',
    ephemeral: false,
    archived: false,
    status: { type: 'idle' },
    createdAt: Date.now(),
    updatedAt: Date.now(),
    turns: [],
  }
  state.threadsById = { ...state.threadsById, [threadId]: fallback }
  state.threadOrder = state.threadOrder.includes(threadId) ? state.threadOrder : [...state.threadOrder, threadId]
  state.threadStatus = { ...state.threadStatus, [threadId]: fallback.status }
  return fallback
}

function upsertTurn(state: SessionProjectionState, threadId: string, turn: SessionTurn): void {
  const list = state.turnsByThread[threadId] ?? []
  const index = list.findIndex((entry) => entry.id === turn.id)
  let nextList: SessionTurn[]
  if (index >= 0) {
    nextList = [...list]
    nextList[index] = turn
  } else {
    nextList = [...list, turn]
  }
  state.turnsByThread = { ...state.turnsByThread, [threadId]: nextList }
}

function upsertItem(state: SessionProjectionState, threadId: string, turnId: string | null, item: SessionItem): void {
  if (!turnId) {
    return
  }
  const key = `${threadId}:${turnId}`
  const list = state.itemsByTurn[key] ?? []
  const index = list.findIndex((entry) => entry.id === item.id)
  let nextList: SessionItem[]
  if (index >= 0) {
    nextList = [...list]
    nextList[index] = item
  } else {
    nextList = [...list, item]
  }
  state.itemsByTurn = { ...state.itemsByTurn, [key]: nextList }
}

function normalizeTurnFromEvent(
  threadId: string,
  turnId: string,
  payload: Record<string, unknown>,
): SessionTurn {
  return {
    id: turnId,
    threadId,
    status: normalizeTurnStatus(payload.status),
    lastCodexStatus: normalizeCodexStatus(payload.status),
    startedAtMs: typeof payload.startedAtMs === 'number' ? payload.startedAtMs : Date.now(),
    completedAtMs: typeof payload.completedAtMs === 'number' ? payload.completedAtMs : null,
    items: Array.isArray(payload.items) ? (payload.items as SessionItem[]) : [],
    error: payload.error && typeof payload.error === 'object'
      ? {
          code: normalizeSessionErrorCode((payload.error as Record<string, unknown>).code),
          message: String((payload.error as Record<string, unknown>).message ?? 'Unknown turn error.'),
          details: (payload.error as Record<string, unknown>).details as Record<string, unknown> | undefined,
        }
      : null,
  }
}

function resolveItemKindFromMethod(method: string): ItemKind {
  if (method.includes('/plan/')) {
    return 'plan'
  }
  if (method.includes('/reasoning/')) {
    return 'reasoning'
  }
  if (method.includes('/commandExecution/')) {
    return 'commandExecution'
  }
  if (method.includes('/fileChange/')) {
    return 'fileChange'
  }
  if (method.includes('userInput')) {
    return 'userInput'
  }
  return 'agentMessage'
}

function normalizeItemFromParams(
  threadId: string,
  turnId: string | null,
  method: string,
  params: Record<string, unknown>,
  statusOverride?: ItemStatus,
): SessionItem | null {
  const rawItem = params.item
  if (rawItem && typeof rawItem === 'object') {
    const itemRecord = rawItem as Record<string, unknown>
    const itemId = String(itemRecord.id ?? '').trim()
    if (!itemId) {
      return null
    }
    return {
      id: itemId,
      threadId,
      turnId: typeof itemRecord.turnId === 'string' ? itemRecord.turnId : turnId,
      kind: normalizeItemKind(itemRecord.kind),
      status: statusOverride ?? normalizeItemStatus(itemRecord.status),
      createdAtMs: typeof itemRecord.createdAtMs === 'number' ? itemRecord.createdAtMs : Date.now(),
      updatedAtMs: Date.now(),
      payload: itemRecord,
    }
  }

  const itemId = String(params.itemId ?? '').trim()
  if (!itemId) {
    return null
  }
  return {
    id: itemId,
    threadId,
    turnId,
    kind: resolveItemKindFromMethod(method),
    status: statusOverride ?? 'inProgress',
    createdAtMs: Date.now(),
    updatedAtMs: Date.now(),
    payload: { ...params },
  }
}

export function applySessionEvent(
  previous: SessionProjectionState,
  envelope: SessionEventEnvelope,
): SessionProjectionState {
  const threadId = String(envelope.threadId ?? '').trim()
  if (!threadId) {
    return previous
  }
  const previousSeq = previous.lastEventSeqByThread[threadId] ?? 0
  if (envelope.eventSeq <= previousSeq) {
    return previous
  }

  let state: SessionProjectionState = {
    ...previous,
    threadsById: { ...previous.threadsById },
    turnsByThread: { ...previous.turnsByThread },
    itemsByTurn: { ...previous.itemsByTurn },
    lastEventSeqByThread: { ...previous.lastEventSeqByThread, [threadId]: envelope.eventSeq },
    lastEventIdByThread: { ...previous.lastEventIdByThread, [threadId]: envelope.eventId },
    gapDetectedByThread: { ...previous.gapDetectedByThread },
    threadStatus: { ...previous.threadStatus },
    tokenUsageByThread: { ...previous.tokenUsageByThread },
  }

  if (previousSeq > 0 && envelope.eventSeq > previousSeq + 1) {
    state.gapDetectedByThread[threadId] = true
  }

  const params = envelope.params ?? {}
  const ensuredThread = ensureThread(state, threadId)

  switch (envelope.method) {
    case 'thread/started': {
      const threadPayload = params.thread
      if (threadPayload && typeof threadPayload === 'object') {
        const merged: SessionThread = {
          ...ensuredThread,
          ...(threadPayload as SessionThread),
          id: threadId,
          status: normalizeThreadStatus((threadPayload as Record<string, unknown>).status),
        }
        state.threadsById[threadId] = merged
        state.threadStatus[threadId] = merged.status
      }
      break
    }
    case 'thread/status/changed': {
      const nextStatus = normalizeThreadStatus(params.status)
      state.threadStatus[threadId] = nextStatus
      state.threadsById[threadId] = { ...ensuredThread, status: nextStatus, updatedAt: Date.now() }
      break
    }
    case 'thread/closed': {
      const nextStatus: ThreadStatus = { type: 'notLoaded' }
      state.threadStatus[threadId] = nextStatus
      state.threadsById[threadId] = { ...ensuredThread, status: nextStatus, updatedAt: Date.now() }
      break
    }
    case 'thread/tokenUsage/updated': {
      const usage = params.tokenUsage
      state.tokenUsageByThread[threadId] = usage && typeof usage === 'object' ? (usage as Record<string, unknown>) : null
      break
    }
    case 'turn/started':
    case 'turn/completed': {
      const turnPayload = params.turn && typeof params.turn === 'object' ? (params.turn as Record<string, unknown>) : {}
      const resolvedTurnId = String(turnPayload.id ?? envelope.turnId ?? '').trim()
      if (resolvedTurnId) {
        const normalizedTurn = normalizeTurnFromEvent(threadId, resolvedTurnId, turnPayload)
        upsertTurn(state, threadId, normalizedTurn)
        if (Array.isArray(turnPayload.items)) {
          for (const raw of turnPayload.items) {
            if (!raw || typeof raw !== 'object') {
              continue
            }
            const item = normalizeItemFromParams(
              threadId,
              resolvedTurnId,
              envelope.method,
              { item: raw as Record<string, unknown> },
            )
            if (item) {
              upsertItem(state, threadId, resolvedTurnId, item)
            }
          }
        }
      }
      break
    }
    case 'item/started':
    case 'item/completed':
    case 'item/agentMessage/delta':
    case 'item/plan/delta':
    case 'item/reasoning/summaryTextDelta':
    case 'item/reasoning/summaryPartAdded':
    case 'item/reasoning/textDelta':
    case 'item/commandExecution/outputDelta':
    case 'item/fileChange/outputDelta': {
      const item = normalizeItemFromParams(
        threadId,
        envelope.turnId,
        envelope.method,
        params,
        envelope.method === 'item/completed' ? 'completed' : undefined,
      )
      if (item) {
        upsertItem(state, threadId, item.turnId, item)
      }
      break
    }
    case 'serverRequest/resolved':
    case 'error':
    case 'thread/archived':
    case 'thread/unarchived':
    case 'thread/name/updated':
    default:
      break
  }

  return state
}
