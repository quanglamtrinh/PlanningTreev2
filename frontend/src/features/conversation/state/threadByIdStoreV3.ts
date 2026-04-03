import { create } from 'zustand'
import { api, appendAuthToken, buildThreadByIdEventsUrlV3 } from '../../../api/client'
import type { ThreadEventV3, ThreadRole, ThreadSnapshotV3, UserInputAnswer } from '../../../api/types'
import { applyThreadEventV3, ThreadEventApplyErrorV3 } from './applyThreadEventV3'
import { parseThreadEventEnvelopeV3 } from './threadEventRouter'

const SSE_RECONNECT_RETRY_MS = 1000

export type ThreadByIdStreamStatusV3 = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'error'

export type ThreadByIdStoreV3State = {
  snapshot: ThreadSnapshotV3 | null
  activeProjectId: string | null
  activeNodeId: string | null
  activeThreadId: string | null
  activeThreadRole: ThreadRole | null
  isLoading: boolean
  isSending: boolean
  streamStatus: ThreadByIdStreamStatusV3
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
  ThreadByIdStoreV3State,
  'processingStartedAt' | 'lastCompletedAt' | 'lastDurationMs'
>

function selectProcessingTelemetry(state: ProcessingTelemetryState): ProcessingTelemetryState {
  return {
    processingStartedAt: state.processingStartedAt,
    lastCompletedAt: state.lastCompletedAt,
    lastDurationMs: state.lastDurationMs,
  }
}

function resetProcessingTelemetry(): ProcessingTelemetryState {
  return {
    processingStartedAt: null,
    lastCompletedAt: null,
    lastDurationMs: null,
  }
}

function seedRunningTelemetry(
  state: ProcessingTelemetryState,
  snapshot: ThreadSnapshotV3 | null,
): ProcessingTelemetryState {
  const telemetry = selectProcessingTelemetry(state)
  if (!snapshot) {
    return resetProcessingTelemetry()
  }
  if (snapshot.processingState === 'running' || snapshot.processingState === 'waiting_user_input') {
    return {
      processingStartedAt: telemetry.processingStartedAt ?? Date.now(),
      lastCompletedAt: telemetry.lastCompletedAt,
      lastDurationMs: telemetry.lastDurationMs,
    }
  }
  return telemetry
}

function completeProcessingTelemetry(state: ProcessingTelemetryState): ProcessingTelemetryState {
  const telemetry = selectProcessingTelemetry(state)
  const completedAt = Date.now()
  return {
    processingStartedAt: null,
    lastCompletedAt: completedAt,
    lastDurationMs:
      telemetry.processingStartedAt != null
        ? Math.max(0, completedAt - telemetry.processingStartedAt)
        : telemetry.lastDurationMs,
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
    ThreadByIdStoreV3State,
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
  get: () => ThreadByIdStoreV3State,
  set: (
    partial:
      | Partial<ThreadByIdStoreV3State>
      | ((state: ThreadByIdStoreV3State) => Partial<ThreadByIdStoreV3State>),
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
    const snapshot = await api.getThreadSnapshotByIdV3(projectId, nodeId, threadId)
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
  get: () => ThreadByIdStoreV3State,
  set: (
    partial:
      | Partial<ThreadByIdStoreV3State>
      | ((state: ThreadByIdStoreV3State) => Partial<ThreadByIdStoreV3State>),
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
  get: () => ThreadByIdStoreV3State,
  set: (
    partial:
      | Partial<ThreadByIdStoreV3State>
      | ((state: ThreadByIdStoreV3State) => Partial<ThreadByIdStoreV3State>),
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
    buildThreadByIdEventsUrlV3(projectId, nodeId, threadId, afterSnapshotVersion),
  )
  const eventSource = new EventSource(url)
  threadEventSource = eventSource
  set({ streamStatus: 'connecting' })

  const applyEnvelope = (event: ThreadEventV3) => {
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

    let nextSnapshot: ThreadSnapshotV3
    try {
      nextSnapshot = applyThreadEventV3(currentState.snapshot, event)
    } catch (error) {
      if (error instanceof ThreadEventApplyErrorV3) {
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

      const nextState: Partial<ThreadByIdStoreV3State> = {
        snapshot: nextSnapshot,
        lastEventId: event.eventId,
        lastSnapshotVersion: event.snapshotVersion ?? nextSnapshot.snapshotVersion,
        streamStatus: 'open',
      }

      if (event.type === 'thread.snapshot.v3') {
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
      } else if (event.type === 'thread.error.v3') {
        nextState.error = event.payload.errorItem.message
      } else if (event.type === 'thread.lifecycle.v3') {
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
      const event = parseThreadEventEnvelopeV3(message.data)
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

export const useThreadByIdStoreV3 = create<ThreadByIdStoreV3State>((set, get) => ({
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
      const snapshot = await api.getThreadSnapshotByIdV3(projectId, nodeId, threadId)
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
        return {
          isSending: false,
          snapshot: {
            ...state.snapshot,
            threadId: response.threadId ?? state.snapshot.threadId,
            activeTurnId: response.turnId,
            processingState: 'running',
            snapshotVersion: Math.max(
              state.snapshot.snapshotVersion,
              response.snapshotVersion ?? state.snapshot.snapshotVersion,
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
    throw new Error('User input requests are unsupported in the V3 execution/audit foundation phase.')
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
