import { create } from 'zustand'
import type { PendingServerRequest } from '../contracts'

type PendingRequestsStoreState = {
  pendingById: Record<string, PendingServerRequest>
  queue: string[]
  activeRequestId: string | null
  lastPollAtMs: number | null
  hydrateFromServer: (rows: PendingServerRequest[]) => void
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

function isQueueableStatus(status: PendingServerRequest['status']): boolean {
  return status === 'pending' || status === 'submitted'
}

export const usePendingRequestsStore = create<PendingRequestsStoreState>((set, get) => ({
  pendingById: {},
  queue: [],
  activeRequestId: null,
  lastPollAtMs: null,
  hydrateFromServer(rows) {
    const nextById: Record<string, PendingServerRequest> = {}
    for (const row of rows) {
      nextById[row.requestId] = row
    }
    const queueEntries = rows.filter((row) => isQueueableStatus(row.status))
    const queue = sortedQueue(queueEntries)
    const active = get().activeRequestId
    const activeRequestId = active && queue.includes(active) ? active : (queue[0] ?? null)
    set({
      pendingById: nextById,
      queue,
      activeRequestId,
      lastPollAtMs: Date.now(),
    })
  },
  markSubmitted(requestId) {
    set((state) => {
      const existing = state.pendingById[requestId]
      if (!existing) {
        return state
      }
      return {
        pendingById: {
          ...state.pendingById,
          [requestId]: { ...existing, status: 'submitted', submittedAtMs: Date.now() },
        },
      }
    })
  },
  markResolved(requestId) {
    set((state) => {
      const existing = state.pendingById[requestId]
      if (!existing) {
        return state
      }
      const queue = state.queue.filter((id) => id !== requestId)
      const activeRequestId = state.activeRequestId === requestId ? (queue[0] ?? null) : state.activeRequestId
      return {
        pendingById: {
          ...state.pendingById,
          [requestId]: { ...existing, status: 'resolved', resolvedAtMs: Date.now() },
        },
        queue,
        activeRequestId,
      }
    })
  },
  markRejected(requestId) {
    set((state) => {
      const existing = state.pendingById[requestId]
      if (!existing) {
        return state
      }
      const queue = state.queue.filter((id) => id !== requestId)
      const activeRequestId = state.activeRequestId === requestId ? (queue[0] ?? null) : state.activeRequestId
      return {
        pendingById: {
          ...state.pendingById,
          [requestId]: { ...existing, status: 'rejected', resolvedAtMs: Date.now() },
        },
        queue,
        activeRequestId,
      }
    })
  },
  markExpired(requestId) {
    set((state) => {
      const existing = state.pendingById[requestId]
      if (!existing) {
        return state
      }
      const queue = state.queue.filter((id) => id !== requestId)
      const activeRequestId = state.activeRequestId === requestId ? (queue[0] ?? null) : state.activeRequestId
      return {
        pendingById: {
          ...state.pendingById,
          [requestId]: { ...existing, status: 'expired', resolvedAtMs: Date.now() },
        },
        queue,
        activeRequestId,
      }
    })
  },
  setActiveRequest(requestId) {
    set({ activeRequestId: requestId })
  },
  clear() {
    set({ pendingById: {}, queue: [], activeRequestId: null, lastPollAtMs: null })
  },
}))

