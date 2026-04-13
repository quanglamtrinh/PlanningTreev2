import { create } from 'zustand'
import { api, appendAuthToken, buildThreadByIdEventsUrlV3 } from '../../../api/client'
import type {
  PlanActionV3,
  ThreadRole,
  ThreadSnapshotV3,
  UserInputAnswer,
} from '../../../api/types'
import {
  applyOptimisticUserInputSubmissionV3,
  applyThreadEventV3,
  ThreadEventApplyDiagnosticsV3,
  ThreadEventApplyErrorV3,
} from './applyThreadEventV3'
import type { ThreadBusinessEventV3, ThreadStreamOpenEnvelopeV3 } from './threadEventRouter'
import { parseThreadEventEnvelopeV3 } from './threadEventRouter'

const SSE_RECONNECT_RETRY_MS = 1000
const USER_INPUT_RESOLVE_FALLBACK_RELOAD_MS = 1500
const FRAME_BATCH_FALLBACK_FLUSH_MS = 16
const FRAME_BATCH_MAX_QUEUE_AGE_MS = 50

export type ThreadByIdStreamStatusV3 = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'error'
export type ReloadReasonCode =
  | 'REPLAY_MISS'
  | 'CONTRACT_ENVELOPE_INVALID'
  | 'CONTRACT_THREAD_ID_MISMATCH'
  | 'CONTRACT_EVENT_CURSOR_INVALID'
  | 'APPLY_EVENT_FAILED'
  | 'USER_INPUT_RESOLVE_TIMEOUT'
  | 'USER_INPUT_RESOLVE_REQUEST_FAILED'
  | 'STREAM_HEALTHCHECK_FAILED'
  | 'MANUAL_RETRY'
export type ThreadByIdTelemetryV3 = {
  streamReconnectCount: number
  applyErrorCount: number
  forcedSnapshotReloadCount: number
  lastForcedReloadReason: ReloadReasonCode | null
  batchedFlushCount: number
  batchedEventsApplied: number
  forcedFlushCount: number
  fastAppendHitCount: number
  fastAppendFallbackCount: number
  firstFrameLatencyMs: number | null
  firstMeaningfulFrameLatencyMs: number | null
  renderErrorCount: number
  legacy_fallback_used_count: number
  envelope_validation_failure_count: number
  heartbeat_cursor_pollution_count: number
}

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
  telemetry: ThreadByIdTelemetryV3
  error: string | null

  loadThread: (
    projectId: string,
    nodeId: string,
    threadId: string,
    threadRole: ThreadRole,
  ) => Promise<void>
  sendTurn: (text: string, metadata?: Record<string, unknown>) => Promise<void>
  resolveUserInput: (requestId: string, answers: UserInputAnswer[]) => Promise<void>
  runPlanAction: (
    action: PlanActionV3,
    planItemId: string,
    revision: number,
    text?: string,
  ) => Promise<void>
  recordRenderError: (reason: string) => void
  disconnectThread: () => void
}

export type ThreadCoreState = Pick<
  ThreadByIdStoreV3State,
  'snapshot' | 'lastEventId' | 'lastSnapshotVersion' | 'processingStartedAt' | 'lastCompletedAt' | 'lastDurationMs'
>
export type ThreadTransportState = Pick<
  ThreadByIdStoreV3State,
  'activeProjectId' | 'activeNodeId' | 'activeThreadId' | 'activeThreadRole' | 'streamStatus'
>
export type ThreadUiControlState = Pick<
  ThreadByIdStoreV3State,
  'isLoading' | 'isSending' | 'error' | 'telemetry'
>

export function selectCore(state: ThreadByIdStoreV3State): ThreadCoreState {
  return {
    snapshot: state.snapshot,
    lastEventId: state.lastEventId,
    lastSnapshotVersion: state.lastSnapshotVersion,
    processingStartedAt: state.processingStartedAt,
    lastCompletedAt: state.lastCompletedAt,
    lastDurationMs: state.lastDurationMs,
  }
}

export function selectTransport(state: ThreadByIdStoreV3State): ThreadTransportState {
  return {
    activeProjectId: state.activeProjectId,
    activeNodeId: state.activeNodeId,
    activeThreadId: state.activeThreadId,
    activeThreadRole: state.activeThreadRole,
    streamStatus: state.streamStatus,
  }
}

export function selectUiControl(state: ThreadByIdStoreV3State): ThreadUiControlState {
  return {
    isLoading: state.isLoading,
    isSending: state.isSending,
    error: state.error,
    telemetry: state.telemetry,
  }
}

let threadEventSource: EventSource | null = null
let clearThreadEventStreamBuffers: (() => void) | null = null
let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null
const resolveFallbackTimers = new Map<string, ReturnType<typeof globalThis.setTimeout>>()
let threadGeneration = 0

type ProcessingTelemetryState = Pick<
  ThreadByIdStoreV3State,
  'processingStartedAt' | 'lastCompletedAt' | 'lastDurationMs'
>

const DEFAULT_TELEMETRY_V3: ThreadByIdTelemetryV3 = {
  streamReconnectCount: 0,
  applyErrorCount: 0,
  forcedSnapshotReloadCount: 0,
  lastForcedReloadReason: null,
  batchedFlushCount: 0,
  batchedEventsApplied: 0,
  forcedFlushCount: 0,
  fastAppendHitCount: 0,
  fastAppendFallbackCount: 0,
  firstFrameLatencyMs: null,
  firstMeaningfulFrameLatencyMs: null,
  renderErrorCount: 0,
  legacy_fallback_used_count: 0,
  envelope_validation_failure_count: 0,
  heartbeat_cursor_pollution_count: 0,
}

function resetTelemetryV3(): ThreadByIdTelemetryV3 {
  return { ...DEFAULT_TELEMETRY_V3 }
}

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

function clearResolveFallbackTimer(requestId: string) {
  const timer = resolveFallbackTimers.get(requestId)
  if (timer !== undefined) {
    globalThis.clearTimeout(timer)
    resolveFallbackTimers.delete(requestId)
  }
}

function clearResolveFallbackTimers() {
  for (const timer of resolveFallbackTimers.values()) {
    globalThis.clearTimeout(timer)
  }
  resolveFallbackTimers.clear()
}

function closeThreadEventSource() {
  if (clearThreadEventStreamBuffers) {
    clearThreadEventStreamBuffers()
    clearThreadEventStreamBuffers = null
  }
  if (threadEventSource) {
    threadEventSource.close()
    threadEventSource = null
  }
}

function reconcileResolveFallbackTimers(snapshot: ThreadSnapshotV3 | null) {
  if (!snapshot) {
    clearResolveFallbackTimers()
    return
  }
  const submittedRequestIds = new Set(
    snapshot.uiSignals.activeUserInputRequests
      .filter((request) => request.status === 'answer_submitted')
      .map((request) => request.requestId),
  )
  for (const requestId of [...resolveFallbackTimers.keys()]) {
    if (!submittedRequestIds.has(requestId)) {
      clearResolveFallbackTimer(requestId)
    }
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

function isStreamHealthy(state: Pick<ThreadByIdStoreV3State, 'streamStatus'>) {
  return (
    threadEventSource !== null &&
    (state.streamStatus === 'open' || state.streamStatus === 'connecting')
  )
}

function compareEventIdCursor(previous: string | null, current: string): number {
  if (previous == null) {
    return -1
  }
  const prev = BigInt(previous)
  const next = BigInt(current)
  if (next > prev) {
    return -1
  }
  if (next === prev) {
    return 0
  }
  return 1
}

type ReloadPolicyV3 =
  | {
      kind: 'forced'
      reason: ReloadReasonCode
      setLoading?: boolean
      message?: string | null
    }
  | {
      kind: 'soft'
      setLoading?: boolean
      reason?: string | null
      message?: string | null
    }

type ReloadTriggerV3 =
  | { type: 'stream_replay_miss'; message: string }
  | { type: 'contract_envelope_invalid'; message: string }
  | { type: 'contract_thread_id_mismatch'; message: string }
  | { type: 'contract_event_cursor_invalid'; message: string }
  | { type: 'apply_event_failed'; message: string }
  | { type: 'user_input_resolve_timeout' }
  | { type: 'user_input_resolve_request_failed'; message: string }
  | { type: 'stream_healthcheck_failed'; setLoading: boolean }
  | { type: 'manual_retry'; setLoading?: boolean; message?: string | null }

export function decideReloadPolicy(trigger: ReloadTriggerV3): ReloadPolicyV3 {
  switch (trigger.type) {
    case 'stream_replay_miss':
      return {
        kind: 'forced',
        reason: 'REPLAY_MISS',
        setLoading: false,
        message: trigger.message,
      }
    case 'contract_envelope_invalid':
      return {
        kind: 'forced',
        reason: 'CONTRACT_ENVELOPE_INVALID',
        setLoading: false,
        message: trigger.message,
      }
    case 'contract_thread_id_mismatch':
      return {
        kind: 'forced',
        reason: 'CONTRACT_THREAD_ID_MISMATCH',
        setLoading: false,
        message: trigger.message,
      }
    case 'contract_event_cursor_invalid':
      return {
        kind: 'forced',
        reason: 'CONTRACT_EVENT_CURSOR_INVALID',
        setLoading: false,
        message: trigger.message,
      }
    case 'apply_event_failed':
      return {
        kind: 'forced',
        reason: 'APPLY_EVENT_FAILED',
        setLoading: false,
        message: trigger.message,
      }
    case 'user_input_resolve_timeout':
      return {
        kind: 'forced',
        reason: 'USER_INPUT_RESOLVE_TIMEOUT',
        setLoading: false,
      }
    case 'user_input_resolve_request_failed':
      return {
        kind: 'forced',
        reason: 'USER_INPUT_RESOLVE_REQUEST_FAILED',
        setLoading: false,
        message: trigger.message,
      }
    case 'stream_healthcheck_failed':
      return {
        kind: 'forced',
        reason: 'STREAM_HEALTHCHECK_FAILED',
        setLoading: trigger.setLoading,
      }
    case 'manual_retry':
      return {
        kind: 'forced',
        reason: 'MANUAL_RETRY',
        setLoading: trigger.setLoading,
        message: trigger.message,
      }
    default:
      return { kind: 'soft', setLoading: false }
  }
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
  policy: ReloadPolicyV3 = { kind: 'soft', setLoading: false },
) {
  clearReconnectTimer()
  closeThreadEventSource()

  if (policy.kind === 'forced') {
    set((state) => ({
      telemetry: {
        ...state.telemetry,
        forcedSnapshotReloadCount: state.telemetry.forcedSnapshotReloadCount + 1,
        lastForcedReloadReason: policy.reason,
      },
    }))
  }

  if (policy.setLoading) {
    const errorMessage = policy.message ?? (policy.kind === 'soft' ? policy.reason ?? null : null)
    set({
      isLoading: true,
      streamStatus: 'connecting',
      error: errorMessage,
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
      lastEventId: null,
      lastSnapshotVersion: snapshot.snapshotVersion,
      streamStatus: 'connecting',
      ...seedRunningTelemetry(get(), snapshot),
    })
    reconcileResolveFallbackTimers(snapshot)
    void openThreadEventStream(
      get,
      set,
      projectId,
      nodeId,
      threadId,
      threadRole,
      generation,
      snapshot.snapshotVersion,
      null,
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
  if (threadRole === 'ask_planning') {
    void api.reportAskRolloutMetricEvent('stream_reconnect').catch(() => undefined)
  }
  set((state) => ({
    streamStatus: 'reconnecting',
    telemetry: {
      ...state.telemetry,
      streamReconnectCount: state.telemetry.streamReconnectCount + 1,
    },
  }))
  reconnectTimer = globalThis.setTimeout(() => {
    reconnectTimer = null
    const state = get()
    if (
      !isCurrentGeneration(generation) ||
      !isActiveTarget(state, projectId, nodeId, threadId, threadRole)
    ) {
      return
    }
    if (!state.snapshot) {
      void reloadThreadSnapshot(get, set, projectId, nodeId, threadId, threadRole, generation, {
        kind: 'soft',
        setLoading: false,
        reason: state.error,
      })
      return
    }
    void openThreadEventStream(
      get,
      set,
      projectId,
      nodeId,
      threadId,
      threadRole,
      generation,
      state.lastSnapshotVersion,
      state.lastEventId,
    )
  }, SSE_RECONNECT_RETRY_MS)
}

function scheduleResolveFallbackReload(
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
  requestId: string,
) {
  clearResolveFallbackTimer(requestId)
  const timer = globalThis.setTimeout(() => {
    resolveFallbackTimers.delete(requestId)
    const state = get()
    if (
      !isCurrentGeneration(generation) ||
      !isActiveTarget(state, projectId, nodeId, threadId, threadRole)
    ) {
      return
    }
    const pending = state.snapshot?.uiSignals.activeUserInputRequests.find(
      (request) => request.requestId === requestId,
    )
    if (!pending || pending.status !== 'answer_submitted') {
      return
    }
    void reloadThreadSnapshot(
      get,
      set,
      projectId,
      nodeId,
      threadId,
      threadRole,
      generation,
      decideReloadPolicy({ type: 'user_input_resolve_timeout' }),
    )
  }, USER_INPUT_RESOLVE_FALLBACK_RELOAD_MS)
  resolveFallbackTimers.set(requestId, timer)
}

async function openThreadEventStream(
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
  lastEventId: string | null,
) {
  clearReconnectTimer()
  clearResolveFallbackTimers()
  closeThreadEventSource()

  const normalizedLastEventId =
    typeof lastEventId === 'string' && lastEventId.trim().length > 0 ? lastEventId.trim() : null

  if (normalizedLastEventId != null) {
    try {
      const probe = await api.probeThreadByIdEventsCursorV3(
        projectId,
        nodeId,
        threadId,
        normalizedLastEventId,
      )
      const stateAfterProbe = get()
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(stateAfterProbe, projectId, nodeId, threadId, threadRole)
      ) {
        return
      }
      if (probe === 'mismatch') {
        const reason =
          'replay_miss: reconnect cursor is outside replay window; running targeted resync.'
        set({
          streamStatus: 'error',
          error: reason,
        })
        void reloadThreadSnapshot(
          get,
          set,
          projectId,
          nodeId,
          threadId,
          threadRole,
          generation,
          decideReloadPolicy({ type: 'stream_replay_miss', message: reason }),
        )
        return
      }
    } catch (error) {
      const stateAfterProbeFailure = get()
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(stateAfterProbeFailure, projectId, nodeId, threadId, threadRole)
      ) {
        return
      }
      set({
        streamStatus: 'error',
        error: error instanceof Error ? error.message : String(error),
      })
      scheduleStreamReopen(get, set, projectId, nodeId, threadId, threadRole, generation)
      return
    }
  }

  const url = appendAuthToken(
    buildThreadByIdEventsUrlV3(
      projectId,
      nodeId,
      threadId,
      afterSnapshotVersion,
      normalizedLastEventId,
    ),
  )
  const eventSource = new EventSource(url)
  threadEventSource = eventSource
  set({ streamStatus: 'connecting' })
  const streamSubscribedAt = Date.now()
  type QueuedBusinessFrame = {
    event: ThreadBusinessEventV3
    legacyFallbackUsed: boolean
  }
  type FlushReason = 'raf' | 'fallback' | 'forced' | 'max_age'
  const queuedBusinessFrames: QueuedBusinessFrame[] = []
  let queuedSinceMs: number | null = null
  let rafFlushHandle: number | null = null
  let fallbackFlushTimer: ReturnType<typeof globalThis.setTimeout> | null = null
  let maxAgeFlushTimer: ReturnType<typeof globalThis.setTimeout> | null = null

  const clearScheduledFlush = () => {
    if (rafFlushHandle !== null && typeof globalThis.cancelAnimationFrame === 'function') {
      globalThis.cancelAnimationFrame(rafFlushHandle)
    }
    rafFlushHandle = null
    if (fallbackFlushTimer !== null) {
      globalThis.clearTimeout(fallbackFlushTimer)
      fallbackFlushTimer = null
    }
    if (maxAgeFlushTimer !== null) {
      globalThis.clearTimeout(maxAgeFlushTimer)
      maxAgeFlushTimer = null
    }
  }

  const clearQueuedBusinessFrames = () => {
    queuedBusinessFrames.length = 0
    queuedSinceMs = null
    clearScheduledFlush()
  }

  clearThreadEventStreamBuffers = clearQueuedBusinessFrames

  const failContract = (
    trigger:
      | { type: 'contract_envelope_invalid'; message: string }
      | { type: 'contract_thread_id_mismatch'; message: string }
      | { type: 'contract_event_cursor_invalid'; message: string },
  ) => {
    const reason = trigger.message
    clearQueuedBusinessFrames()
    if (threadRole === 'ask_planning') {
      void api.reportAskRolloutMetricEvent('stream_error').catch(() => undefined)
    }
    set((state) => ({
      error: reason,
      streamStatus: 'error',
      telemetry: {
        ...state.telemetry,
        envelope_validation_failure_count: state.telemetry.envelope_validation_failure_count + 1,
      },
    }))
    void reloadThreadSnapshot(
      get,
      set,
      projectId,
      nodeId,
      threadId,
      threadRole,
      generation,
      decideReloadPolicy(trigger),
    )
  }

  const applyStreamOpen = (
    envelope: ThreadStreamOpenEnvelopeV3,
    legacyFallbackUsed: boolean,
  ) => {
    const currentState = get()
    if (
      !isCurrentGeneration(generation) ||
      !isActiveTarget(currentState, projectId, nodeId, threadId, threadRole)
    ) {
      return
    }
    if (
      envelope.projectId !== projectId ||
      envelope.nodeId !== nodeId ||
      envelope.threadRole !== threadRole
    ) {
      return
    }
    set((state) => {
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(state, projectId, nodeId, threadId, threadRole)
      ) {
        return {}
      }
      return {
        streamStatus: 'open',
        lastSnapshotVersion: envelope.snapshotVersion ?? state.lastSnapshotVersion,
        telemetry: {
          ...state.telemetry,
          legacy_fallback_used_count:
            state.telemetry.legacy_fallback_used_count + (legacyFallbackUsed ? 1 : 0),
          firstMeaningfulFrameLatencyMs:
            state.telemetry.firstMeaningfulFrameLatencyMs ??
            Math.max(0, Date.now() - streamSubscribedAt),
        },
      }
    })
  }

  const shouldForceFlush = (event: ThreadBusinessEventV3): boolean => {
    if (
      event.type === 'thread.snapshot.v3' ||
      event.type === 'thread.error.v3' ||
      event.type === 'conversation.ui.user_input.v3'
    ) {
      return true
    }
    if (event.type === 'thread.lifecycle.v3') {
      return (
        event.payload.state === 'waiting_user_input' ||
        event.payload.state === 'turn_completed' ||
        event.payload.state === 'turn_failed'
      )
    }
    return false
  }

  const flushQueuedBusinessFrames = (reason: FlushReason) => {
    if (queuedBusinessFrames.length === 0) {
      return
    }
    const frames = queuedBusinessFrames.splice(0, queuedBusinessFrames.length)
    queuedSinceMs = null
    clearScheduledFlush()

    const currentState = get()
    if (
      !isCurrentGeneration(generation) ||
      !isActiveTarget(currentState, projectId, nodeId, threadId, threadRole)
    ) {
      return
    }

    let workingSnapshot = currentState.snapshot
    let workingLastEventId = currentState.lastEventId
    let workingLastSnapshotVersion = currentState.lastSnapshotVersion
    let workingError = currentState.error
    let workingIsLoading = currentState.isLoading
    let processingTelemetry = selectProcessingTelemetry(currentState)
    let shouldReconcileResolveFallback = false
    let legacyFallbackUsedCount = 0
    let appliedEventCount = 0
    let fastAppendHitCount = 0
    let fastAppendFallbackCount = 0

    for (const frame of frames) {
      const event = frame.event
      if (event.threadId !== threadId) {
        failContract({
          type: 'contract_thread_id_mismatch',
          message: `Thread event thread_id mismatch: expected ${threadId} but received ${event.threadId}.`,
        })
        return
      }
      if (
        event.projectId !== projectId ||
        event.nodeId !== nodeId ||
        event.threadRole !== threadRole
      ) {
        continue
      }
      try {
        const cursorOrder = compareEventIdCursor(workingLastEventId, event.eventId)
        if (cursorOrder >= 0) {
          const orderReason =
            cursorOrder === 0
              ? `Duplicate event_id detected: ${event.eventId}.`
              : `Non-monotonic event_id detected: ${event.eventId} after ${workingLastEventId}.`
          failContract({
            type: 'contract_event_cursor_invalid',
            message: orderReason,
          })
          return
        }
      } catch {
        failContract({
          type: 'contract_event_cursor_invalid',
          message: `Invalid event_id cursor state. last_event_id=${workingLastEventId}`,
        })
        return
      }

      const beforeSnapshot = workingSnapshot
      const diagnostics: ThreadEventApplyDiagnosticsV3 = {
        fastAppendUsed: false,
        fastAppendFallback: false,
      }
      let nextSnapshot: ThreadSnapshotV3
      try {
        nextSnapshot = applyThreadEventV3(workingSnapshot, event, diagnostics)
      } catch (error) {
        if (error instanceof ThreadEventApplyErrorV3) {
          clearQueuedBusinessFrames()
          set((state) => ({
            error: error.message,
            streamStatus: 'error',
            telemetry: {
              ...state.telemetry,
              applyErrorCount: state.telemetry.applyErrorCount + 1,
            },
          }))
          void reloadThreadSnapshot(
            get,
            set,
            projectId,
            nodeId,
            threadId,
            threadRole,
            generation,
            decideReloadPolicy({ type: 'apply_event_failed', message: error.message }),
          )
          return
        }
        throw error
      }

      workingSnapshot = nextSnapshot
      workingLastEventId = event.eventId
      workingLastSnapshotVersion = event.snapshotVersion ?? nextSnapshot.snapshotVersion
      appliedEventCount += 1
      if (frame.legacyFallbackUsed) {
        legacyFallbackUsedCount += 1
      }
      if (diagnostics.fastAppendUsed) {
        fastAppendHitCount += 1
      }
      if (diagnostics.fastAppendFallback) {
        fastAppendFallbackCount += 1
      }

      if (event.type === 'thread.snapshot.v3') {
        shouldReconcileResolveFallback = true
        workingIsLoading = false
        workingError = null
        if (
          (beforeSnapshot?.processingState === 'running' ||
            beforeSnapshot?.processingState === 'waiting_user_input') &&
          (nextSnapshot.processingState === 'idle' || nextSnapshot.processingState === 'failed')
        ) {
          processingTelemetry = completeProcessingTelemetry(processingTelemetry)
        } else {
          processingTelemetry = seedRunningTelemetry(processingTelemetry, nextSnapshot)
        }
      } else if (event.type === 'conversation.ui.user_input.v3') {
        shouldReconcileResolveFallback = true
      } else if (event.type === 'thread.error.v3') {
        workingError = event.payload.errorItem.message
      } else if (event.type === 'thread.lifecycle.v3') {
        if (
          event.payload.state === 'turn_started' ||
          event.payload.state === 'waiting_user_input'
        ) {
          processingTelemetry = {
            ...processingTelemetry,
            processingStartedAt: processingTelemetry.processingStartedAt ?? Date.now(),
          }
        } else if (
          event.payload.state === 'turn_completed' ||
          event.payload.state === 'turn_failed'
        ) {
          processingTelemetry = completeProcessingTelemetry(processingTelemetry)
        }
      }
    }

    if (!appliedEventCount) {
      return
    }

    if (shouldReconcileResolveFallback && workingSnapshot) {
      reconcileResolveFallbackTimers(workingSnapshot)
    }

    const forcedFlushDelta = reason === 'forced' || reason === 'max_age' ? 1 : 0
    set((state) => {
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(state, projectId, nodeId, threadId, threadRole)
      ) {
        return {}
      }
      return {
        snapshot: workingSnapshot,
        lastEventId: workingLastEventId,
        lastSnapshotVersion: workingLastSnapshotVersion,
        streamStatus: 'open',
        isLoading: workingIsLoading,
        error: workingError,
        ...processingTelemetry,
        telemetry: {
          ...state.telemetry,
          legacy_fallback_used_count: state.telemetry.legacy_fallback_used_count + legacyFallbackUsedCount,
          batchedFlushCount: state.telemetry.batchedFlushCount + 1,
          batchedEventsApplied: state.telemetry.batchedEventsApplied + appliedEventCount,
          forcedFlushCount: state.telemetry.forcedFlushCount + forcedFlushDelta,
          fastAppendHitCount: state.telemetry.fastAppendHitCount + fastAppendHitCount,
          fastAppendFallbackCount: state.telemetry.fastAppendFallbackCount + fastAppendFallbackCount,
        },
      }
    })
  }

  const scheduleQueuedBusinessFlush = () => {
    if (rafFlushHandle === null && typeof globalThis.requestAnimationFrame === 'function') {
      rafFlushHandle = globalThis.requestAnimationFrame(() => {
        rafFlushHandle = null
        flushQueuedBusinessFrames('raf')
      })
    }
    if (fallbackFlushTimer === null) {
      fallbackFlushTimer = globalThis.setTimeout(() => {
        fallbackFlushTimer = null
        flushQueuedBusinessFrames('fallback')
      }, FRAME_BATCH_FALLBACK_FLUSH_MS)
    }
    if (maxAgeFlushTimer === null && queuedSinceMs !== null) {
      const ageMs = Math.max(0, Date.now() - queuedSinceMs)
      const waitMs = Math.max(0, FRAME_BATCH_MAX_QUEUE_AGE_MS - ageMs)
      maxAgeFlushTimer = globalThis.setTimeout(() => {
        maxAgeFlushTimer = null
        flushQueuedBusinessFrames('max_age')
      }, waitMs)
    }
  }

  const enqueueBusinessEvent = (event: ThreadBusinessEventV3, legacyFallbackUsed: boolean) => {
    if (queuedBusinessFrames.length === 0) {
      queuedSinceMs = Date.now()
    }
    queuedBusinessFrames.push({ event, legacyFallbackUsed })
    if (shouldForceFlush(event)) {
      flushQueuedBusinessFrames('forced')
      return
    }
    scheduleQueuedBusinessFlush()
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
      const frame = parseThreadEventEnvelopeV3(message.data)
      if (frame.kind === 'stream_open') {
        applyStreamOpen(frame.envelope, frame.legacyFallbackUsed)
        return
      }
      enqueueBusinessEvent(frame.event, frame.legacyFallbackUsed)
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      failContract({
        type: 'contract_envelope_invalid',
        message: reason,
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
    if (threadRole === 'ask_planning') {
      void api.reportAskRolloutMetricEvent('stream_error').catch(() => undefined)
    }
    clearQueuedBusinessFrames()
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
  telemetry: resetTelemetryV3(),
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
    clearResolveFallbackTimers()
    closeThreadEventSource()

    const generation = ++threadGeneration
    const loadStartedAt = Date.now()
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
      telemetry: resetTelemetryV3(),
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
      set((state) => ({
        snapshot,
        isLoading: false,
        error: null,
        lastSnapshotVersion: snapshot.snapshotVersion,
        streamStatus: 'connecting',
        telemetry: {
          ...state.telemetry,
          firstFrameLatencyMs: Math.max(0, Date.now() - loadStartedAt),
        },
        ...seedRunningTelemetry(get(), snapshot),
      }))
      reconcileResolveFallbackTimers(snapshot)
      void openThreadEventStream(
        get,
        set,
        projectId,
        nodeId,
        threadId,
        threadRole,
        generation,
        snapshot.snapshotVersion,
        null,
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
    const { activeProjectId, activeNodeId, activeThreadId, activeThreadRole, snapshot } = get()
    if (!activeProjectId || !activeNodeId || !activeThreadId || !activeThreadRole || !snapshot) {
      return
    }
    if (activeThreadRole !== 'execution' && activeThreadRole !== 'ask_planning') {
      throw new Error('Audit review is read-only in the V3 execution/audit flow.')
    }

    const generation = threadGeneration
    const sendingRole = activeThreadRole
    set({ isSending: true, error: null })

    try {
      const response = await api.startThreadTurnByIdV3(
        activeProjectId,
        activeNodeId,
        activeThreadId,
        text,
        metadata,
      )
      set((state) => {
        if (
          !isCurrentGeneration(generation) ||
          !state.snapshot ||
          !state.activeThreadId ||
          !isActiveTarget(
            state,
            activeProjectId,
            activeNodeId,
            state.activeThreadId,
            sendingRole,
          )
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
        !isActiveTarget(
          state,
          activeProjectId,
          activeNodeId,
          state.activeThreadId,
          sendingRole,
        )
      ) {
        return
      }
      set({
        isSending: false,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  },

  async resolveUserInput(requestId: string, answers: UserInputAnswer[]) {
    const {
      activeProjectId,
      activeNodeId,
      activeThreadId,
      activeThreadRole,
      snapshot,
      isLoading,
      streamStatus,
    } = get()
    if (!activeProjectId || !activeNodeId || !activeThreadId || !activeThreadRole || !snapshot) {
      return
    }

    const generation = threadGeneration
    const submittedAt = new Date().toISOString()
    set((state) => {
      if (
        !state.snapshot ||
        !state.activeThreadId ||
        !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadId, activeThreadRole)
      ) {
        return {}
      }
      return {
        error: null,
        snapshot: applyOptimisticUserInputSubmissionV3(
          state.snapshot,
          requestId,
          answers,
          submittedAt,
        ),
      }
    })

    try {
      await api.resolveThreadUserInputByIdV3(
        activeProjectId,
        activeNodeId,
        activeThreadId,
        requestId,
        answers,
      )
      const latestState = get()
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(latestState, activeProjectId, activeNodeId, activeThreadId, activeThreadRole)
      ) {
        return
      }
      if (!isStreamHealthy(latestState)) {
        await reloadThreadSnapshot(
          get,
          set,
          activeProjectId,
          activeNodeId,
          activeThreadId,
          activeThreadRole,
          generation,
          decideReloadPolicy({
            type: 'stream_healthcheck_failed',
            setLoading: isLoading && streamStatus === 'connecting',
          }),
        )
        return
      }
      scheduleResolveFallbackReload(
        get,
        set,
        activeProjectId,
        activeNodeId,
        activeThreadId,
        activeThreadRole,
        generation,
        requestId,
      )
    } catch (error) {
      const state = get()
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadId, activeThreadRole)
      ) {
        return
      }
      const reason = error instanceof Error ? error.message : String(error)
      set({
        error: reason,
      })
      await reloadThreadSnapshot(
        get,
        set,
        activeProjectId,
        activeNodeId,
        activeThreadId,
        activeThreadRole,
        generation,
        decideReloadPolicy({
          type: 'user_input_resolve_request_failed',
          message: reason,
        }),
      )
    }
  },

  async runPlanAction(
    action: PlanActionV3,
    planItemId: string,
    revision: number,
    text?: string,
  ) {
    const { activeProjectId, activeNodeId, activeThreadId, activeThreadRole, snapshot } = get()
    if (!activeProjectId || !activeNodeId || !activeThreadId || !snapshot) {
      return
    }
    if (activeThreadRole !== 'execution') {
      throw new Error('Plan actions are supported only on execution threads.')
    }

    const generation = threadGeneration
    set({ isSending: true, error: null })
    try {
      const response = await api.planActionByIdV3(activeProjectId, activeNodeId, activeThreadId, {
        action,
        planItemId,
        revision,
        text,
      })
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
            activeTurnId: response.turnId ?? state.snapshot.activeTurnId,
            processingState: 'running',
            snapshotVersion: Math.max(
              state.snapshot.snapshotVersion,
              response.snapshotVersion ?? state.snapshot.snapshotVersion,
            ),
          },
          lastSnapshotVersion: Math.max(state.lastSnapshotVersion ?? 0, response.snapshotVersion ?? 0),
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

  recordRenderError(reason: string) {
    set((state) => ({
      error: reason,
      telemetry: {
        ...state.telemetry,
        renderErrorCount: state.telemetry.renderErrorCount + 1,
      },
    }))
  },

  disconnectThread() {
    threadGeneration += 1
    clearReconnectTimer()
    clearResolveFallbackTimers()
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
      telemetry: resetTelemetryV3(),
      error: null,
    })
  },
}))
