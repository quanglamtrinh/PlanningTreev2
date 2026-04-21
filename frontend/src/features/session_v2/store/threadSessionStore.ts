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
    const turnsByThread = { [threadId]: turns }
    const nextItemsByTurn: Record<string, SessionItem[]> = {}
    for (const turn of turns) {
      const key = `${threadId}:${turn.id}`
      nextItemsByTurn[key] = Array.isArray(turn.items) ? turn.items : []
    }
    set((state) => ({
      ...state,
      turnsByThread: { ...state.turnsByThread, ...turnsByThread },
      itemsByTurn: { ...state.itemsByTurn, ...nextItemsByTurn },
    }))
  },
  setItemsForTurn(threadId, turnId, items) {
    const key = `${threadId}:${turnId}`
    set((state) => ({
      ...state,
      itemsByTurn: { ...state.itemsByTurn, [key]: items },
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
