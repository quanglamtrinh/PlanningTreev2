import { create } from 'zustand'
import type { PendingServerRequest, PendingRequestStatus, ServerRequestMethod, SessionEventEnvelope } from '../contracts'

type PendingRequestsStoreState = {
  pendingById: Record<string, PendingServerRequest>
  queue: string[]
  activeRequestId: string | null
  lastPollAtMs: number | null
  hydrateFromServer: (rows: PendingServerRequest[]) => void
  reconcileFromServer: (rows: PendingServerRequest[]) => void
  applyRequestEvent: (envelope: SessionEventEnvelope) => void
  applyRequestEventsBatch: (envelopes: SessionEventEnvelope[]) => void
  markSubmitted: (requestId: string) => void
  markResolved: (requestId: string) => void
  markRejected: (requestId: string) => void
  markExpired: (requestId: string) => void
  setActiveRequest: (requestId: string | null) => void
  clear: () => void
}

function sortedQueue(entries: PendingServerRequest[]): string[] {
  return [...entries]
    .sort((a, b) => {
      if (a.createdAtMs !== b.createdAtMs) {
        return a.createdAtMs - b.createdAtMs
      }
      return a.requestId.localeCompare(b.requestId)
    })
    .map((entry) => entry.requestId)
}

function isRequestEventMethod(method: string): boolean {
  return method === 'serverRequest/created' || method === 'serverRequest/updated' || method === 'serverRequest/resolved'
}

function isActionableRequest(request: PendingServerRequest): boolean {
  return request.status === 'pending' && request.inactiveByReconcile !== true
}

function deriveQueue(pendingById: Record<string, PendingServerRequest>): string[] {
  return sortedQueue(Object.values(pendingById).filter(isActionableRequest))
}

function resolveActiveRequestId(activeRequestId: string | null, queue: string[]): string | null {
  return activeRequestId && queue.includes(activeRequestId) ? activeRequestId : (queue[0] ?? null)
}

function withDerivedQueue(
  state: PendingRequestsStoreState,
  pendingById: Record<string, PendingServerRequest>,
  extra?: Partial<Pick<PendingRequestsStoreState, 'lastPollAtMs'>>,
): Partial<PendingRequestsStoreState> {
  const queue = deriveQueue(pendingById)
  return {
    pendingById,
    queue,
    activeRequestId: resolveActiveRequestId(state.activeRequestId, queue),
    ...extra,
  }
}

function normalizeStatus(value: unknown): PendingRequestStatus {
  if (
    value === 'pending' ||
    value === 'submitted' ||
    value === 'resolved' ||
    value === 'rejected' ||
    value === 'expired'
  ) {
    return value
  }
  return 'pending'
}

function statusRank(status: PendingRequestStatus): number {
  if (status === 'pending') {
    return 0
  }
  if (status === 'submitted') {
    return 1
  }
  return 2
}

function mergeRequestRecord(
  existing: PendingServerRequest | undefined,
  incoming: PendingServerRequest,
): PendingServerRequest {
  if (!existing || statusRank(incoming.status) >= statusRank(existing.status)) {
    return {
      ...existing,
      ...incoming,
      inactiveByReconcile: false,
      reconciledAtMs: undefined,
    }
  }

  return {
    ...existing,
    ...incoming,
    status: existing.status,
    submittedAtMs: existing.submittedAtMs ?? incoming.submittedAtMs,
    resolvedAtMs: existing.resolvedAtMs ?? incoming.resolvedAtMs,
    inactiveByReconcile: false,
    reconciledAtMs: undefined,
  }
}

function normalizeRequest(value: unknown): PendingServerRequest | null {
  if (!value || typeof value !== 'object') {
    return null
  }
  const record = value as Record<string, unknown>
  const requestId = String(record.requestId ?? '').trim()
  const method = String(record.method ?? '').trim() as ServerRequestMethod
  const threadId = String(record.threadId ?? '').trim()
  if (!requestId || !method || !threadId) {
    return null
  }
  const turnId = typeof record.turnId === 'string' && record.turnId.trim() ? record.turnId.trim() : null
  const itemId = typeof record.itemId === 'string' && record.itemId.trim() ? record.itemId.trim() : null
  const createdAtMs = typeof record.createdAtMs === 'number' && Number.isFinite(record.createdAtMs)
    ? record.createdAtMs
    : Date.now()
  const submittedAtMs = typeof record.submittedAtMs === 'number' && Number.isFinite(record.submittedAtMs)
    ? record.submittedAtMs
    : null
  const resolvedAtMs = typeof record.resolvedAtMs === 'number' && Number.isFinite(record.resolvedAtMs)
    ? record.resolvedAtMs
    : null
  const payload = record.payload && typeof record.payload === 'object'
    ? { ...(record.payload as Record<string, unknown>) }
    : {}
  return {
    requestId,
    method,
    threadId,
    turnId,
    itemId,
    status: normalizeStatus(record.status),
    createdAtMs,
    submittedAtMs,
    resolvedAtMs,
    payload,
  }
}

function requestFromEvent(envelope: SessionEventEnvelope): PendingServerRequest | null {
  if (!isRequestEventMethod(envelope.method)) {
    return null
  }
  return normalizeRequest(envelope.params?.request)
}

export const usePendingRequestsStore = create<PendingRequestsStoreState>((set, get) => ({
  pendingById: {},
  queue: [],
  activeRequestId: null,
  lastPollAtMs: null,
  hydrateFromServer(rows) {
    get().reconcileFromServer(rows)
  },
  reconcileFromServer(rows) {
    set((state) => {
      const now = Date.now()
      const nextById: Record<string, PendingServerRequest> = { ...state.pendingById }
      const activeIds = new Set<string>()
      for (const row of rows) {
        const normalized = normalizeRequest(row)
        if (!normalized) {
          continue
        }
        activeIds.add(normalized.requestId)
        nextById[normalized.requestId] = mergeRequestRecord(state.pendingById[normalized.requestId], normalized)
      }
      for (const [requestId, request] of Object.entries(state.pendingById)) {
        if (!activeIds.has(requestId) && (request.status === 'pending' || request.status === 'submitted')) {
          nextById[requestId] = {
            ...request,
            inactiveByReconcile: true,
            reconciledAtMs: now,
          }
        }
      }
      return withDerivedQueue(state, nextById, { lastPollAtMs: now })
    })
  },
  applyRequestEvent(envelope) {
    get().applyRequestEventsBatch([envelope])
  },
  applyRequestEventsBatch(envelopes) {
    if (!Array.isArray(envelopes) || envelopes.length === 0) {
      return
    }
    set((state) => {
      let changed = false
      const nextById: Record<string, PendingServerRequest> = { ...state.pendingById }
      for (const envelope of envelopes) {
        const request = requestFromEvent(envelope)
        if (!request) {
          continue
        }
        changed = true
        nextById[request.requestId] = mergeRequestRecord(nextById[request.requestId], request)
      }
      return changed ? withDerivedQueue(state, nextById) : state
    })
  },
  markSubmitted(requestId) {
    set((state) => {
      const existing = state.pendingById[requestId]
      if (!existing) {
        return state
      }
      const pendingById = {
        ...state.pendingById,
        [requestId]: {
          ...existing,
          status: 'submitted' as const,
          submittedAtMs: Date.now(),
          inactiveByReconcile: false,
          reconciledAtMs: undefined,
        },
      }
      return withDerivedQueue(state, pendingById)
    })
  },
  markResolved(requestId) {
    set((state) => {
      const existing = state.pendingById[requestId]
      if (!existing) {
        return state
      }
      const pendingById = {
        ...state.pendingById,
        [requestId]: {
          ...existing,
          status: 'resolved' as const,
          resolvedAtMs: Date.now(),
          inactiveByReconcile: false,
          reconciledAtMs: undefined,
        },
      }
      return withDerivedQueue(state, pendingById)
    })
  },
  markRejected(requestId) {
    set((state) => {
      const existing = state.pendingById[requestId]
      if (!existing) {
        return state
      }
      const pendingById = {
        ...state.pendingById,
        [requestId]: {
          ...existing,
          status: 'rejected' as const,
          resolvedAtMs: Date.now(),
          inactiveByReconcile: false,
          reconciledAtMs: undefined,
        },
      }
      return withDerivedQueue(state, pendingById)
    })
  },
  markExpired(requestId) {
    set((state) => {
      const existing = state.pendingById[requestId]
      if (!existing) {
        return state
      }
      const pendingById = {
        ...state.pendingById,
        [requestId]: {
          ...existing,
          status: 'expired' as const,
          resolvedAtMs: Date.now(),
          inactiveByReconcile: false,
          reconciledAtMs: undefined,
        },
      }
      return withDerivedQueue(state, pendingById)
    })
  },
  setActiveRequest(requestId) {
    set({ activeRequestId: requestId })
  },
  clear() {
    set({ pendingById: {}, queue: [], activeRequestId: null, lastPollAtMs: null })
  },
}))
