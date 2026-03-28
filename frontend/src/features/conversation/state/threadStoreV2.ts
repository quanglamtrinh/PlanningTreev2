import { create } from 'zustand'
import { api, appendAuthToken, buildThreadEventsUrlV2 } from '../../../api/client'
import type {
  ResolveUserInputV2Response,
  ThreadEventV2,
  ThreadRole,
  ThreadSnapshotV2,
} from '../../../api/types'
import { useDetailStateStore } from '../../../stores/detail-state-store'
import { applyThreadEvent, ThreadEventApplyError } from './applyThreadEvent'
import { parseThreadEventEnvelope } from './threadEventRouter'

const DEFAULT_THREAD_ROLE: ThreadRole = 'ask_planning'
const SSE_RECONNECT_RETRY_MS = 1000
const RESET_FALLBACK_RELOAD_MS = 1500

export type ThreadStreamStatusV2 = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'error'

export type ConversationThreadStoreV2State = {
  snapshot: ThreadSnapshotV2 | null
  activeProjectId: string | null
  activeNodeId: string | null
  activeThreadRole: ThreadRole
  isLoading: boolean
  isSending: boolean
  isResetting: boolean
  streamStatus: ThreadStreamStatusV2
  lastEventId: string | null
  lastSnapshotVersion: number | null
  error: string | null

  loadThread: (projectId: string, nodeId: string, threadRole?: ThreadRole) => Promise<void>
  sendTurn: (text: string, metadata?: Record<string, unknown>) => Promise<void>
  resolveUserInput: (
    requestId: string,
    answers: ResolveUserInputV2Response['answers'],
  ) => Promise<void>
  resetThread: () => Promise<void>
  disconnectThread: () => void
}

let threadEventSource: EventSource | null = null
let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null
let resetFallbackTimer: ReturnType<typeof globalThis.setTimeout> | null = null
let threadGeneration = 0

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    globalThis.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function clearResetFallbackTimer() {
  if (resetFallbackTimer !== null) {
    globalThis.clearTimeout(resetFallbackTimer)
    resetFallbackTimer = null
  }
}

function closeThreadEventSource() {
  if (threadEventSource) {
    threadEventSource.close()
    threadEventSource = null
  }
}

function isActiveTarget(
  state: Pick<ConversationThreadStoreV2State, 'activeProjectId' | 'activeNodeId' | 'activeThreadRole'>,
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
) {
  return (
    state.activeProjectId === projectId &&
    state.activeNodeId === nodeId &&
    state.activeThreadRole === threadRole
  )
}

function isCurrentGeneration(generation: number) {
  return generation === threadGeneration
}

async function reloadThreadSnapshot(
  get: () => ConversationThreadStoreV2State,
  set: (
    partial:
      | Partial<ConversationThreadStoreV2State>
      | ((state: ConversationThreadStoreV2State) => Partial<ConversationThreadStoreV2State>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
  generation: number,
  options: {
    setLoading?: boolean
    keepResetting?: boolean
    reason?: string | null
  } = {},
) {
  clearReconnectTimer()
  closeThreadEventSource()

  if (options.setLoading) {
    set({
      isLoading: true,
      streamStatus: 'connecting',
      error: options.reason ?? null,
    })
  }

  try {
    const snapshot = await api.getThreadSnapshotV2(projectId, nodeId, threadRole)
    const latestState = get()
    if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
      return
    }
    set({
      snapshot,
      isLoading: false,
      isResetting: options.keepResetting ?? false,
      error: null,
      lastSnapshotVersion: snapshot.snapshotVersion,
      streamStatus: 'connecting',
    })
    openThreadEventStream(get, set, projectId, nodeId, threadRole, generation, snapshot.snapshotVersion)
  } catch (error) {
    const latestState = get()
    if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
      return
    }
    set({
      isLoading: false,
      streamStatus: 'error',
      error: error instanceof Error ? error.message : String(error),
    })
  }
}

function scheduleStreamReopen(
  get: () => ConversationThreadStoreV2State,
  set: (
    partial:
      | Partial<ConversationThreadStoreV2State>
      | ((state: ConversationThreadStoreV2State) => Partial<ConversationThreadStoreV2State>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
  generation: number,
) {
  clearReconnectTimer()
  set({ streamStatus: 'reconnecting' })
  reconnectTimer = globalThis.setTimeout(() => {
    reconnectTimer = null
    const state = get()
    if (!isCurrentGeneration(generation) || !isActiveTarget(state, projectId, nodeId, threadRole)) {
      return
    }
    void reloadThreadSnapshot(get, set, projectId, nodeId, threadRole, generation, {
      setLoading: false,
      keepResetting: state.isResetting,
      reason: state.error,
    })
  }, SSE_RECONNECT_RETRY_MS)
}

function scheduleResetFallbackReload(
  get: () => ConversationThreadStoreV2State,
  set: (
    partial:
      | Partial<ConversationThreadStoreV2State>
      | ((state: ConversationThreadStoreV2State) => Partial<ConversationThreadStoreV2State>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
  generation: number,
  expectedSnapshotVersion: number,
) {
  clearResetFallbackTimer()
  resetFallbackTimer = globalThis.setTimeout(() => {
    resetFallbackTimer = null
    const state = get()
    if (!isCurrentGeneration(generation) || !isActiveTarget(state, projectId, nodeId, threadRole)) {
      return
    }
    if (!state.isResetting || (state.lastSnapshotVersion ?? 0) >= expectedSnapshotVersion) {
      return
    }
    void reloadThreadSnapshot(get, set, projectId, nodeId, threadRole, generation, {
      setLoading: false,
      keepResetting: false,
      reason: null,
    })
  }, RESET_FALLBACK_RELOAD_MS)
}

function openThreadEventStream(
  get: () => ConversationThreadStoreV2State,
  set: (
    partial:
      | Partial<ConversationThreadStoreV2State>
      | ((state: ConversationThreadStoreV2State) => Partial<ConversationThreadStoreV2State>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
  generation: number,
  afterSnapshotVersion: number | null,
) {
  clearReconnectTimer()
  closeThreadEventSource()

  const url = appendAuthToken(
    buildThreadEventsUrlV2(projectId, nodeId, threadRole, afterSnapshotVersion),
  )
  const eventSource = new EventSource(url)
  threadEventSource = eventSource
  set({ streamStatus: 'connecting' })

  const applyEnvelope = (event: ThreadEventV2) => {
    const currentState = get()
    if (!isCurrentGeneration(generation) || !isActiveTarget(currentState, projectId, nodeId, threadRole)) {
      return
    }
    if (
      event.projectId !== projectId ||
      event.nodeId !== nodeId ||
      event.threadRole !== threadRole
    ) {
      return
    }

    let nextSnapshot: ThreadSnapshotV2
    try {
      nextSnapshot = applyThreadEvent(currentState.snapshot, event)
    } catch (error) {
      if (error instanceof ThreadEventApplyError) {
        set({
          error: error.message,
          streamStatus: 'error',
        })
        void reloadThreadSnapshot(get, set, projectId, nodeId, threadRole, generation, {
          setLoading: false,
          keepResetting: currentState.isResetting,
          reason: error.message,
        })
        return
      }
      throw error
    }

    set((state) => {
      if (!isCurrentGeneration(generation) || !isActiveTarget(state, projectId, nodeId, threadRole)) {
        return {}
      }

      const nextState: Partial<ConversationThreadStoreV2State> = {
        snapshot: nextSnapshot,
        lastEventId: event.eventId,
        lastSnapshotVersion: event.snapshotVersion ?? nextSnapshot.snapshotVersion,
        streamStatus: 'open',
      }

      if (event.type === 'thread.snapshot') {
        nextState.isLoading = false
        nextState.isResetting = false
        nextState.error = null
      } else if (event.type === 'thread.reset') {
        nextState.isResetting = true
      } else if (event.type === 'thread.error') {
        nextState.error = event.payload.errorItem.message
      }

      return nextState
    })
  }

  eventSource.onopen = () => {
    if (threadEventSource !== eventSource || !isCurrentGeneration(generation)) {
      return
    }
    const state = get()
    if (!isActiveTarget(state, projectId, nodeId, threadRole)) {
      return
    }
    set({ streamStatus: 'open' })
  }

  eventSource.onmessage = (message) => {
    if (threadEventSource !== eventSource || !isCurrentGeneration(generation)) {
      return
    }
    try {
      const event = parseThreadEventEnvelope(message.data)
      applyEnvelope(event)
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : String(error),
        streamStatus: 'error',
      })
      void reloadThreadSnapshot(get, set, projectId, nodeId, threadRole, generation, {
        setLoading: false,
        keepResetting: get().isResetting,
        reason: error instanceof Error ? error.message : String(error),
      })
    }
  }

  eventSource.onerror = () => {
    if (threadEventSource !== eventSource || !isCurrentGeneration(generation)) {
      return
    }
    const state = get()
    if (!isActiveTarget(state, projectId, nodeId, threadRole)) {
      return
    }
    closeThreadEventSource()
    scheduleStreamReopen(get, set, projectId, nodeId, threadRole, generation)
  }
}

export const useConversationThreadStoreV2 = create<ConversationThreadStoreV2State>((set, get) => ({
  snapshot: null,
  activeProjectId: null,
  activeNodeId: null,
  activeThreadRole: DEFAULT_THREAD_ROLE,
  isLoading: false,
  isSending: false,
  isResetting: false,
  streamStatus: 'idle',
  lastEventId: null,
  lastSnapshotVersion: null,
  error: null,

  async loadThread(projectId: string, nodeId: string, threadRole: ThreadRole = DEFAULT_THREAD_ROLE) {
    const current = get()
    if (
      current.activeProjectId === projectId &&
      current.activeNodeId === nodeId &&
      current.activeThreadRole === threadRole &&
      current.snapshot &&
      (threadEventSource !== null || reconnectTimer !== null)
    ) {
      return
    }

    clearReconnectTimer()
    clearResetFallbackTimer()
    closeThreadEventSource()

    const generation = ++threadGeneration
    set({
      snapshot: null,
      activeProjectId: projectId,
      activeNodeId: nodeId,
      activeThreadRole: threadRole,
      isLoading: true,
      isSending: false,
      isResetting: false,
      streamStatus: 'connecting',
      lastEventId: null,
      lastSnapshotVersion: null,
      error: null,
    })

    try {
      const snapshot = await api.getThreadSnapshotV2(projectId, nodeId, threadRole)
      const latestState = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
        return
      }
      set({
        snapshot,
        isLoading: false,
        error: null,
        lastSnapshotVersion: snapshot.snapshotVersion,
        streamStatus: 'connecting',
      })
      openThreadEventStream(get, set, projectId, nodeId, threadRole, generation, snapshot.snapshotVersion)
    } catch (error) {
      const latestState = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
        return
      }
      set({
        isLoading: false,
        streamStatus: 'error',
        error: error instanceof Error ? error.message : String(error),
      })
    }
  },

  async sendTurn(text: string, metadata: Record<string, unknown> = {}) {
    const { activeProjectId, activeNodeId, activeThreadRole, snapshot } = get()
    if (!activeProjectId || !activeNodeId || !snapshot) {
      return
    }

    const generation = threadGeneration
    set({ isSending: true, error: null })

    try {
      const response = await api.startThreadTurnV2(
        activeProjectId,
        activeNodeId,
        activeThreadRole,
        text,
        metadata,
      )
      set((state) => {
        if (
          !isCurrentGeneration(generation) ||
          !state.snapshot ||
          !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)
        ) {
          return {}
        }

        let nextSnapshot = state.snapshot
        for (const item of response.createdItems) {
          nextSnapshot = applyThreadEvent(nextSnapshot, {
            eventId: `local-upsert-${item.id}`,
            channel: 'thread',
            projectId: activeProjectId,
            nodeId: activeNodeId,
            threadRole: activeThreadRole,
            occurredAt: item.updatedAt,
            snapshotVersion: response.snapshotVersion,
            type: 'conversation.item.upsert',
            payload: { item },
          })
        }

        return {
          isSending: false,
          snapshot: {
            ...nextSnapshot,
            threadId: response.threadId ?? nextSnapshot.threadId,
            activeTurnId: response.turnId,
            processingState: 'running',
            snapshotVersion: Math.max(nextSnapshot.snapshotVersion, response.snapshotVersion),
          },
          lastSnapshotVersion: Math.max(state.lastSnapshotVersion ?? 0, response.snapshotVersion),
        }
      })

      if (activeThreadRole === 'audit') {
        void useDetailStateStore.getState().refreshExecutionState(activeProjectId, activeNodeId)
      }
    } catch (error) {
      const state = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)) {
        return
      }
      set({
        isSending: false,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  },

  async resolveUserInput(requestId, answers) {
    const { activeProjectId, activeNodeId, activeThreadRole, snapshot } = get()
    if (!activeProjectId || !activeNodeId || !snapshot) {
      return
    }

    const generation = threadGeneration
    set({ error: null })
    try {
      const response = await api.resolveThreadUserInputV2(
        activeProjectId,
        activeNodeId,
        activeThreadRole,
        requestId,
        answers,
      )
      set((state) => {
        if (
          !isCurrentGeneration(generation) ||
          !state.snapshot ||
          !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)
        ) {
          return {}
        }

        return {
          snapshot: {
            ...state.snapshot,
            pendingRequests: state.snapshot.pendingRequests.map((request) =>
              request.requestId === requestId
                ? {
                    ...request,
                    status: response.status,
                    answers: response.answers,
                    submittedAt: response.submittedAt,
                  }
                : request,
            ),
          },
        }
      })
    } catch (error) {
      const state = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)) {
        return
      }
      set({ error: error instanceof Error ? error.message : String(error) })
    }
  },

  async resetThread() {
    const { activeProjectId, activeNodeId, activeThreadRole } = get()
    if (!activeProjectId || !activeNodeId) {
      return
    }

    const generation = threadGeneration
    set({ isResetting: true, error: null })

    try {
      const response = await api.resetThreadV2(activeProjectId, activeNodeId, activeThreadRole)
      const state = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)) {
        return
      }

      const streamHealthy = threadEventSource !== null && (state.streamStatus === 'open' || state.streamStatus === 'connecting')
      if (!streamHealthy) {
        await reloadThreadSnapshot(get, set, activeProjectId, activeNodeId, activeThreadRole, generation, {
          setLoading: false,
          keepResetting: false,
          reason: null,
        })
        return
      }

      scheduleResetFallbackReload(
        get,
        set,
        activeProjectId,
        activeNodeId,
        activeThreadRole,
        generation,
        response.snapshotVersion,
      )
    } catch (error) {
      const state = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)) {
        return
      }
      set({
        isResetting: false,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  },

  disconnectThread() {
    threadGeneration += 1
    clearReconnectTimer()
    clearResetFallbackTimer()
    closeThreadEventSource()
    set({
      snapshot: null,
      activeProjectId: null,
      activeNodeId: null,
      activeThreadRole: DEFAULT_THREAD_ROLE,
      isLoading: false,
      isSending: false,
      isResetting: false,
      streamStatus: 'idle',
      lastEventId: null,
      lastSnapshotVersion: null,
      error: null,
    })
  },
}))
