import { create } from 'zustand'
import { api, appendAuthToken, buildThreadByIdEventsUrlV2 } from '../../../api/client'
import type { ThreadEventV2, ThreadRole, ThreadSnapshotV2, UserInputAnswer } from '../../../api/types'
import { applyThreadEvent, ThreadEventApplyError } from './applyThreadEvent'
import { parseThreadEventEnvelope } from './threadEventRouter'

const SSE_RECONNECT_RETRY_MS = 1000

export type ThreadByIdStreamStatusV2 = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'error'

export type ThreadByIdStoreV2State = {
  snapshot: ThreadSnapshotV2 | null
  activeProjectId: string | null
  activeNodeId: string | null
  activeThreadId: string | null
  activeThreadRole: ThreadRole | null
  isLoading: boolean
  isSending: boolean
  streamStatus: ThreadByIdStreamStatusV2
  lastEventId: string | null
  lastSnapshotVersion: number | null
  processingStartedAt: number | null
  lastCompletedAt: number | null
  lastDurationMs: number | null
  error: string | null

  loadThread: (
    projectId: string,
    nodeId: string,
    threadId: string,
    threadRole: ThreadRole,
  ) => Promise<void>
  sendTurn: (text: string, metadata?: Record<string, unknown>) => Promise<void>
  resolveUserInput: (requestId: string, answers: UserInputAnswer[]) => Promise<void>
  disconnectThread: () => void
}

let threadEventSource: EventSource | null = null
let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null
let threadGeneration = 0

type ProcessingTelemetryState = Pick<
  ThreadByIdStoreV2State,
  'processingStartedAt' | 'lastCompletedAt' | 'lastDurationMs'
>

function resetProcessingTelemetry(): ProcessingTelemetryState {
  return {
    processingStartedAt: null,
    lastCompletedAt: null,
    lastDurationMs: null,
  }
}

function seedRunningTelemetry(
  state: ProcessingTelemetryState,
  snapshot: ThreadSnapshotV2 | null,
): ProcessingTelemetryState {
  if (!snapshot) {
    return resetProcessingTelemetry()
  }
  if (snapshot.processingState === 'running' || snapshot.processingState === 'waiting_user_input') {
    return {
      processingStartedAt: state.processingStartedAt ?? Date.now(),
      lastCompletedAt: state.lastCompletedAt,
      lastDurationMs: state.lastDurationMs,
    }
  }
  return state
}

function completeProcessingTelemetry(state: ProcessingTelemetryState): ProcessingTelemetryState {
  const completedAt = Date.now()
  return {
    processingStartedAt: null,
    lastCompletedAt: completedAt,
    lastDurationMs:
      state.processingStartedAt != null ? Math.max(0, completedAt - state.processingStartedAt) : state.lastDurationMs,
  }
}

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    globalThis.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function closeThreadEventSource() {
  if (threadEventSource) {
    threadEventSource.close()
    threadEventSource = null
  }
}

function isActiveTarget(
  state: Pick<
    ThreadByIdStoreV2State,
    'activeProjectId' | 'activeNodeId' | 'activeThreadId' | 'activeThreadRole'
  >,
  projectId: string,
  nodeId: string,
  threadId: string,
  threadRole: ThreadRole,
) {
  return (
    state.activeProjectId === projectId &&
    state.activeNodeId === nodeId &&
    state.activeThreadId === threadId &&
    state.activeThreadRole === threadRole
  )
}

function isCurrentGeneration(generation: number) {
  return generation === threadGeneration
}

async function reloadThreadSnapshot(
  get: () => ThreadByIdStoreV2State,
  set: (
    partial:
      | Partial<ThreadByIdStoreV2State>
      | ((state: ThreadByIdStoreV2State) => Partial<ThreadByIdStoreV2State>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadId: string,
  threadRole: ThreadRole,
  generation: number,
  options: {
    setLoading?: boolean
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
    const snapshot = await api.getThreadSnapshotByIdV2(projectId, nodeId, threadId)
    const latestState = get()
    if (
      !isCurrentGeneration(generation) ||
      !isActiveTarget(latestState, projectId, nodeId, threadId, threadRole)
    ) {
      return
    }
    set({
      snapshot,
      isLoading: false,
      error: null,
      lastSnapshotVersion: snapshot.snapshotVersion,
      streamStatus: 'connecting',
      ...seedRunningTelemetry(get(), snapshot),
    })
    openThreadEventStream(
      get,
      set,
      projectId,
      nodeId,
      threadId,
      threadRole,
      generation,
      snapshot.snapshotVersion,
    )
  } catch (error) {
    const latestState = get()
    if (
      !isCurrentGeneration(generation) ||
      !isActiveTarget(latestState, projectId, nodeId, threadId, threadRole)
    ) {
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
  get: () => ThreadByIdStoreV2State,
  set: (
    partial:
      | Partial<ThreadByIdStoreV2State>
      | ((state: ThreadByIdStoreV2State) => Partial<ThreadByIdStoreV2State>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadId: string,
  threadRole: ThreadRole,
  generation: number,
) {
  clearReconnectTimer()
  set({ streamStatus: 'reconnecting' })
  reconnectTimer = globalThis.setTimeout(() => {
    reconnectTimer = null
    const state = get()
    if (
      !isCurrentGeneration(generation) ||
      !isActiveTarget(state, projectId, nodeId, threadId, threadRole)
    ) {
      return
    }
    void reloadThreadSnapshot(get, set, projectId, nodeId, threadId, threadRole, generation, {
      setLoading: false,
      reason: state.error,
    })
  }, SSE_RECONNECT_RETRY_MS)
}

function openThreadEventStream(
  get: () => ThreadByIdStoreV2State,
  set: (
    partial:
      | Partial<ThreadByIdStoreV2State>
      | ((state: ThreadByIdStoreV2State) => Partial<ThreadByIdStoreV2State>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadId: string,
  threadRole: ThreadRole,
  generation: number,
  afterSnapshotVersion: number | null,
) {
  clearReconnectTimer()
  closeThreadEventSource()

  const url = appendAuthToken(
    buildThreadByIdEventsUrlV2(projectId, nodeId, threadId, afterSnapshotVersion),
  )
  const eventSource = new EventSource(url)
  threadEventSource = eventSource
  set({ streamStatus: 'connecting' })

  const applyEnvelope = (event: ThreadEventV2) => {
    const currentState = get()
    if (
      !isCurrentGeneration(generation) ||
      !isActiveTarget(currentState, projectId, nodeId, threadId, threadRole)
    ) {
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
        void reloadThreadSnapshot(get, set, projectId, nodeId, threadId, threadRole, generation, {
          setLoading: false,
          reason: error.message,
        })
        return
      }
      throw error
    }

    set((state) => {
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(state, projectId, nodeId, threadId, threadRole)
      ) {
        return {}
      }

      const nextState: Partial<ThreadByIdStoreV2State> = {
        snapshot: nextSnapshot,
        lastEventId: event.eventId,
        lastSnapshotVersion: event.snapshotVersion ?? nextSnapshot.snapshotVersion,
        streamStatus: 'open',
      }

      if (event.type === 'thread.snapshot') {
        nextState.isLoading = false
        nextState.error = null
        if (
          (state.snapshot?.processingState === 'running' ||
            state.snapshot?.processingState === 'waiting_user_input') &&
          (nextSnapshot.processingState === 'idle' || nextSnapshot.processingState === 'failed')
        ) {
          Object.assign(nextState, completeProcessingTelemetry(state))
        } else {
          Object.assign(nextState, seedRunningTelemetry(state, nextSnapshot))
        }
      } else if (event.type === 'thread.error') {
        nextState.error = event.payload.errorItem.message
      } else if (event.type === 'thread.lifecycle') {
        if (
          event.payload.state === 'turn_started' ||
          event.payload.state === 'waiting_user_input'
        ) {
          Object.assign(nextState, {
            processingStartedAt: state.processingStartedAt ?? Date.now(),
          })
        } else if (
          event.payload.state === 'turn_completed' ||
          event.payload.state === 'turn_failed'
        ) {
          Object.assign(nextState, completeProcessingTelemetry(state))
        }
      }

      return nextState
    })
  }

  eventSource.onopen = () => {
    if (threadEventSource !== eventSource || !isCurrentGeneration(generation)) {
      return
    }
    const state = get()
    if (!isActiveTarget(state, projectId, nodeId, threadId, threadRole)) {
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
      const reason = error instanceof Error ? error.message : String(error)
      set({
        error: reason,
        streamStatus: 'error',
      })
      void reloadThreadSnapshot(get, set, projectId, nodeId, threadId, threadRole, generation, {
        setLoading: false,
        reason,
      })
    }
  }

  eventSource.onerror = () => {
    if (threadEventSource !== eventSource || !isCurrentGeneration(generation)) {
      return
    }
    const state = get()
    if (!isActiveTarget(state, projectId, nodeId, threadId, threadRole)) {
      return
    }
    closeThreadEventSource()
    scheduleStreamReopen(get, set, projectId, nodeId, threadId, threadRole, generation)
  }
}

export const useThreadByIdStoreV2 = create<ThreadByIdStoreV2State>((set, get) => ({
  snapshot: null,
  activeProjectId: null,
  activeNodeId: null,
  activeThreadId: null,
  activeThreadRole: null,
  isLoading: false,
  isSending: false,
  streamStatus: 'idle',
  lastEventId: null,
  lastSnapshotVersion: null,
  processingStartedAt: null,
  lastCompletedAt: null,
  lastDurationMs: null,
  error: null,

  async loadThread(projectId: string, nodeId: string, threadId: string, threadRole: ThreadRole) {
    const current = get()
    if (
      current.activeProjectId === projectId &&
      current.activeNodeId === nodeId &&
      current.activeThreadId === threadId &&
      current.activeThreadRole === threadRole &&
      current.snapshot &&
      (threadEventSource !== null || reconnectTimer !== null)
    ) {
      return
    }

    clearReconnectTimer()
    closeThreadEventSource()

    const generation = ++threadGeneration
    set({
      snapshot: null,
      activeProjectId: projectId,
      activeNodeId: nodeId,
      activeThreadId: threadId,
      activeThreadRole: threadRole,
      isLoading: true,
      isSending: false,
      streamStatus: 'connecting',
      lastEventId: null,
      lastSnapshotVersion: null,
      ...resetProcessingTelemetry(),
      error: null,
    })

    try {
      const snapshot = await api.getThreadSnapshotByIdV2(projectId, nodeId, threadId)
      const latestState = get()
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(latestState, projectId, nodeId, threadId, threadRole)
      ) {
        return
      }
      set({
        snapshot,
        isLoading: false,
        error: null,
        lastSnapshotVersion: snapshot.snapshotVersion,
        streamStatus: 'connecting',
        ...seedRunningTelemetry(get(), snapshot),
      })
      openThreadEventStream(
        get,
        set,
        projectId,
        nodeId,
        threadId,
        threadRole,
        generation,
        snapshot.snapshotVersion,
      )
    } catch (error) {
      const latestState = get()
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(latestState, projectId, nodeId, threadId, threadRole)
      ) {
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
    if (activeThreadRole !== 'execution') {
      throw new Error('Audit review is read-only in the V1 execution/audit flow.')
    }

    const generation = threadGeneration
    set({ isSending: true, error: null })

    try {
      const response = await api.startThreadTurnV2(
        activeProjectId,
        activeNodeId,
        'execution',
        text,
        metadata,
      )
      set((state) => {
        if (
          !isCurrentGeneration(generation) ||
          !state.snapshot ||
          !state.activeThreadId ||
          !isActiveTarget(state, activeProjectId, activeNodeId, state.activeThreadId, 'execution')
        ) {
          return {}
        }

        let nextSnapshot = state.snapshot
        for (const item of response.createdItems ?? []) {
          nextSnapshot = applyThreadEvent(nextSnapshot, {
            eventId: `local-upsert-${item.id}`,
            channel: 'thread',
            projectId: activeProjectId,
            nodeId: activeNodeId,
            threadRole: 'execution',
            occurredAt: item.updatedAt,
            snapshotVersion: response.snapshotVersion ?? nextSnapshot.snapshotVersion,
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
            snapshotVersion: Math.max(
              nextSnapshot.snapshotVersion,
              response.snapshotVersion ?? nextSnapshot.snapshotVersion,
            ),
          },
          lastSnapshotVersion: Math.max(
            state.lastSnapshotVersion ?? 0,
            response.snapshotVersion ?? 0,
          ),
          processingStartedAt: state.processingStartedAt ?? Date.now(),
        }
      })
    } catch (error) {
      const state = get()
      if (
        !isCurrentGeneration(generation) ||
        !state.activeThreadId ||
        !isActiveTarget(state, activeProjectId, activeNodeId, state.activeThreadId, 'execution')
      ) {
        return
      }
      set({
        isSending: false,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  },

  async resolveUserInput() {
    throw new Error('User input requests are unsupported in the V1 execution/audit flow.')
  },

  disconnectThread() {
    threadGeneration += 1
    clearReconnectTimer()
    closeThreadEventSource()
    set({
      snapshot: null,
      activeProjectId: null,
      activeNodeId: null,
      activeThreadId: null,
      activeThreadRole: null,
      isLoading: false,
      isSending: false,
      streamStatus: 'idle',
      lastEventId: null,
      lastSnapshotVersion: null,
      ...resetProcessingTelemetry(),
      error: null,
    })
  },
}))
