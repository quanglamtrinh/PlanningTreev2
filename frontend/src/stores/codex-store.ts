import { create } from 'zustand'
import { api } from '../api/client'
import type { CodexSnapshot } from '../api/types'

const SSE_RECONNECT_RETRY_MS = 1000

export type CodexConnectionState = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'error'

export type CodexStoreState = {
  hasInitialized: boolean
  snapshot: CodexSnapshot | null
  isLoading: boolean
  error: string | null
  connectionState: CodexConnectionState
  initialize: () => Promise<void>
  refresh: () => Promise<void>
  disconnect: () => void
}

type CodexStoreSetter = (
  partial:
    | Partial<CodexStoreState>
    | ((state: CodexStoreState) => Partial<CodexStoreState>),
) => void

let eventSource: EventSource | null = null
let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null
let snapshotGeneration = 0

function closeEventSource() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    globalThis.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function isCurrentGeneration(generation: number) {
  return generation === snapshotGeneration
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function scheduleStreamReopen(
  get: () => CodexStoreState,
  set: CodexStoreSetter,
  generation: number,
) {
  clearReconnectTimer()
  reconnectTimer = globalThis.setTimeout(() => {
    if (!isCurrentGeneration(generation) || !get().hasInitialized) {
      return
    }
    openEventStream(get, set, generation)
  }, SSE_RECONNECT_RETRY_MS)
}

function scheduleRecoverAndReconnect(
  get: () => CodexStoreState,
  set: CodexStoreSetter,
  generation: number,
) {
  clearReconnectTimer()
  reconnectTimer = globalThis.setTimeout(() => {
    if (!isCurrentGeneration(generation) || !get().hasInitialized) {
      return
    }

    set({ connectionState: 'reconnecting' })

    void api.getCodexSnapshot()
      .then((snapshot) => {
        if (!isCurrentGeneration(generation) || !get().hasInitialized) {
          return
        }
        set({
          snapshot,
          error: null,
          connectionState: 'reconnecting',
        })
        scheduleStreamReopen(get, set, generation)
      })
      .catch((error) => {
        if (!isCurrentGeneration(generation) || !get().hasInitialized) {
          return
        }
        set({
          error: toErrorMessage(error),
          connectionState: 'error',
        })
        scheduleRecoverAndReconnect(get, set, generation)
      })
  }, SSE_RECONNECT_RETRY_MS)
}

function openEventStream(
  get: () => CodexStoreState,
  set: CodexStoreSetter,
  generation: number,
) {
  closeEventSource()

  if (typeof EventSource === 'undefined') {
    set({ connectionState: 'error' })
    return
  }

  const es = new EventSource('/v1/codex/events')
  eventSource = es

  es.onopen = () => {
    if (eventSource !== es || !isCurrentGeneration(generation)) {
      return
    }
    set({ connectionState: 'live', error: null })
  }

  es.addEventListener('snapshot_updated', (event) => {
    try {
      if (eventSource !== es || !isCurrentGeneration(generation)) {
        return
      }
      const snapshot = JSON.parse(event.data) as CodexSnapshot
      set({
        snapshot,
        error: null,
        connectionState: 'live',
      })
    } catch {
      // Ignore malformed SSE payloads and wait for the next snapshot.
    }
  })

  es.onerror = () => {
    if (eventSource !== es || !isCurrentGeneration(generation)) {
      return
    }

    closeEventSource()
    clearReconnectTimer()

    if (!get().hasInitialized) {
      return
    }

    set({ connectionState: 'reconnecting' })

    void api.getCodexSnapshot()
      .then((snapshot) => {
        if (!isCurrentGeneration(generation) || !get().hasInitialized) {
          return
        }
        set({
          snapshot,
          error: null,
          connectionState: 'reconnecting',
        })
        scheduleStreamReopen(get, set, generation)
      })
      .catch((error) => {
        if (!isCurrentGeneration(generation) || !get().hasInitialized) {
          return
        }
        set({
          error: toErrorMessage(error),
          connectionState: 'error',
        })
        scheduleRecoverAndReconnect(get, set, generation)
      })
  }
}

export const useCodexStore = create<CodexStoreState>((set, get) => ({
  hasInitialized: false,
  snapshot: null,
  isLoading: false,
  error: null,
  connectionState: 'idle',
  async initialize() {
    if (get().isLoading || get().hasInitialized) {
      return
    }

    const generation = ++snapshotGeneration
    clearReconnectTimer()
    closeEventSource()

    set({
      hasInitialized: true,
      isLoading: true,
      error: null,
      connectionState: 'connecting',
    })

    try {
      const snapshot = await api.getCodexSnapshot()
      if (!isCurrentGeneration(generation) || !get().hasInitialized) {
        return
      }
      set({
        snapshot,
        isLoading: false,
        error: null,
        connectionState: 'connecting',
      })
      openEventStream(get, set, generation)
    } catch (error) {
      if (!isCurrentGeneration(generation) || !get().hasInitialized) {
        return
      }
      set({
        isLoading: false,
        error: toErrorMessage(error),
        connectionState: 'error',
      })
      scheduleRecoverAndReconnect(get, set, generation)
    }
  },
  async refresh() {
    set({ isLoading: true, error: null })
    try {
      const snapshot = await api.getCodexSnapshot()
      set({
        snapshot,
        isLoading: false,
        error: null,
      })
    } catch (error) {
      set({
        isLoading: false,
        error: toErrorMessage(error),
      })
      throw error
    }
  },
  disconnect() {
    snapshotGeneration += 1
    clearReconnectTimer()
    closeEventSource()
    set({
      hasInitialized: false,
      isLoading: false,
      error: null,
      connectionState: 'idle',
    })
  },
}))
