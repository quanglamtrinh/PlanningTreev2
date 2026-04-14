import { create } from 'zustand'
import { api, appendAuthToken, buildThreadByIdEventsUrlV3 } from '../../../api/client'
import type {
  ConversationItemV3,
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
const SCROLLBACK_SOFT_CAP = 1000
const PHASE12_CAP_PROFILE_ENV_FLAG = 'VITE_PTM_PHASE12_CAP_PROFILE'
const DEFAULT_PHASE12_CAP_PROFILE: Phase12CapProfile = 'standard'
const PHASE12_CAP_HEADROOM_BY_PROFILE: Record<Phase12CapProfile, number> = {
  low: 100,
  standard: 200,
  high: 400,
}
const HISTORY_PAGE_LIMIT = 200
const EXECUTION_FOLLOWUP_QUEUE_STORAGE_PREFIX = 'ptm:v3:execution-followup-queue:'
const EXECUTION_FOLLOWUP_AUTO_SEND_MAX_AGE_MS = 90_000
const EXECUTION_FOLLOWUP_QUEUE_MAX_ITEMS = 20

export type Phase12CapProfile = 'low' | 'standard' | 'high'
export type Phase12CapPolicy = {
  profile: Phase12CapProfile
  softCap: number
  headroom: number
  effectiveHardCap: number
  effectiveTrimTarget: number
}

function normalizePhase12CapProfile(value: string | null | undefined): Phase12CapProfile | null {
  const normalized = String(value ?? '')
    .trim()
    .toLowerCase()
  if (normalized === 'low' || normalized === 'standard' || normalized === 'high') {
    return normalized
  }
  return null
}

function resolveDeviceMemoryHint(): number | null {
  const nav = (globalThis as { navigator?: { deviceMemory?: unknown } }).navigator
  const memory = nav?.deviceMemory
  if (typeof memory === 'number' && Number.isFinite(memory) && memory > 0) {
    return memory
  }
  return null
}

export function resolvePhase12CapProfile(options: {
  envValue?: string | null
  deviceMemory?: number | null
} = {}): Phase12CapProfile {
  const envProfile = normalizePhase12CapProfile(options.envValue)
  if (envProfile) {
    return envProfile
  }
  const deviceMemory =
    options.deviceMemory != null && Number.isFinite(options.deviceMemory)
      ? Number(options.deviceMemory)
      : resolveDeviceMemoryHint()
  if (deviceMemory != null) {
    if (deviceMemory < 4) {
      return 'low'
    }
    if (deviceMemory >= 8) {
      return 'high'
    }
  }
  return DEFAULT_PHASE12_CAP_PROFILE
}

export function resolvePhase12CapPolicy(options: {
  envValue?: string | null
  deviceMemory?: number | null
} = {}): Phase12CapPolicy {
  const envValue =
    options.envValue ??
    String((import.meta.env as Record<string, unknown>)[PHASE12_CAP_PROFILE_ENV_FLAG] ?? '')
  const profile = resolvePhase12CapProfile({
    envValue,
    deviceMemory: options.deviceMemory,
  })
  const softCap = SCROLLBACK_SOFT_CAP
  const headroom = PHASE12_CAP_HEADROOM_BY_PROFILE[profile]
  return {
    profile,
    softCap,
    headroom,
    effectiveHardCap: softCap + headroom,
    effectiveTrimTarget: softCap,
  }
}

const SCROLLBACK_CAP_POLICY = resolvePhase12CapPolicy()
const SNAPSHOT_LIVE_LIMIT = SCROLLBACK_CAP_POLICY.softCap

export type ThreadByIdStreamStatusV3 = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'error'
export type ExecutionFollowupQueueStatus = 'queued' | 'requires_confirmation' | 'sending' | 'failed'
export type ExecutionFollowupQueuePauseReason =
  | 'none'
  | 'runtime_waiting_input'
  | 'plan_ready_gate'
  | 'operator_pause'
  | 'workflow_blocked'
export type ExecutionFollowupEnqueueContext = {
  latestExecutionRunId: string | null
  planReadyRevision: number | null
}
export type ExecutionFollowupQueueEntry = {
  entryId: string
  text: string
  idempotencyKey: string
  createdAtMs: number
  enqueueContext: ExecutionFollowupEnqueueContext
  status: ExecutionFollowupQueueStatus
  attemptCount: number
  lastError: string | null
}
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
  hasOlderHistory: boolean
  oldestVisibleSequence: number | null
  totalItemCount: number
  isLoadingHistory: boolean
  historyError: string | null
  executionFollowupQueue: ExecutionFollowupQueueEntry[]
  executionQueuePauseReason: ExecutionFollowupQueuePauseReason
  executionQueueOperatorPaused: boolean
  executionQueueWorkflowPhase: string | null
  executionQueueCanSendExecutionMessage: boolean
  executionQueueLatestExecutionRunId: string | null

  loadThread: (
    projectId: string,
    nodeId: string,
    threadId: string,
    threadRole: ThreadRole,
  ) => Promise<void>
  loadMoreHistory: () => Promise<void>
  sendTurn: (text: string, metadata?: Record<string, unknown>) => Promise<void>
  resolveUserInput: (requestId: string, answers: UserInputAnswer[]) => Promise<void>
  runPlanAction: (
    action: PlanActionV3,
    planItemId: string,
    revision: number,
    text?: string,
  ) => Promise<void>
  enqueueFollowup: (text: string) => Promise<void>
  removeQueued: (entryId: string) => void
  reorderQueued: (fromIndex: number, toIndex: number) => void
  sendQueuedNow: (entryId: string) => Promise<void>
  confirmQueued: (entryId: string) => Promise<void>
  retryQueued: (entryId: string) => Promise<void>
  setOperatorPause: (paused: boolean) => void
  syncExecutionQueueContext: (context: {
    workflowPhase: string | null
    canSendExecutionMessage: boolean
    latestExecutionRunId: string | null
  }) => Promise<void>
  recordRenderError: (reason: string) => void
  disconnectThread: () => void
}

export type ThreadCoreState = Pick<
  ThreadByIdStoreV3State,
  | 'snapshot'
  | 'lastEventId'
  | 'lastSnapshotVersion'
  | 'processingStartedAt'
  | 'lastCompletedAt'
  | 'lastDurationMs'
  | 'hasOlderHistory'
  | 'oldestVisibleSequence'
  | 'totalItemCount'
>
export type ThreadTransportState = Pick<
  ThreadByIdStoreV3State,
  'activeProjectId' | 'activeNodeId' | 'activeThreadId' | 'activeThreadRole' | 'streamStatus'
>
export type ThreadUiControlState = Pick<
  ThreadByIdStoreV3State,
  'isLoading' | 'isSending' | 'error' | 'telemetry' | 'isLoadingHistory' | 'historyError'
>
export type ThreadActionHandlers = Pick<
  ThreadByIdStoreV3State,
  | 'loadThread'
  | 'loadMoreHistory'
  | 'sendTurn'
  | 'resolveUserInput'
  | 'runPlanAction'
  | 'recordRenderError'
  | 'disconnectThread'
>
export type ThreadExecutionFollowupQueueState = Pick<
  ThreadByIdStoreV3State,
  | 'activeThreadRole'
  | 'executionFollowupQueue'
  | 'executionQueuePauseReason'
  | 'executionQueueOperatorPaused'
  | 'isSending'
>
export type ThreadExecutionFollowupQueueActions = Pick<
  ThreadByIdStoreV3State,
  | 'enqueueFollowup'
  | 'removeQueued'
  | 'reorderQueued'
  | 'sendQueuedNow'
  | 'confirmQueued'
  | 'retryQueued'
  | 'setOperatorPause'
  | 'syncExecutionQueueContext'
>
export type ThreadFeedRenderState = {
  snapshot: ThreadSnapshotV3 | null
  isLoading: boolean
  isSending: boolean
  error: string | null
  lastCompletedAt: number | null
  lastDurationMs: number | null
}
export type ThreadHistoryUiState = {
  hasOlderHistory: boolean
  isLoadingHistory: boolean
  historyError: string | null
}
export type ThreadComposerState = {
  snapshot: ThreadSnapshotV3 | null
  isLoading: boolean
  isSending: boolean
  isActiveTurn: boolean
}
export type ThreadTransportBannerState = {
  streamStatus: ThreadByIdStreamStatusV3
  error: string | null
  forcedReloadCount: number
  lastForcedReloadReason: ReloadReasonCode | null
}
export type ThreadWorkflowActionState = {
  snapshot: ThreadSnapshotV3 | null
  isLoading: boolean
  isSending: boolean
  lastCompletedAt: number | null
  lastDurationMs: number | null
}

export function selectCore(state: ThreadByIdStoreV3State): ThreadCoreState {
  return {
    snapshot: state.snapshot,
    lastEventId: state.lastEventId,
    lastSnapshotVersion: state.lastSnapshotVersion,
    processingStartedAt: state.processingStartedAt,
    lastCompletedAt: state.lastCompletedAt,
    lastDurationMs: state.lastDurationMs,
    hasOlderHistory: state.hasOlderHistory,
    oldestVisibleSequence: state.oldestVisibleSequence,
    totalItemCount: state.totalItemCount,
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
    isLoadingHistory: state.isLoadingHistory,
    historyError: state.historyError,
  }
}

export function selectThreadActions(state: ThreadByIdStoreV3State): ThreadActionHandlers {
  return {
    loadThread: state.loadThread,
    loadMoreHistory: state.loadMoreHistory,
    sendTurn: state.sendTurn,
    resolveUserInput: state.resolveUserInput,
    runPlanAction: state.runPlanAction,
    recordRenderError: state.recordRenderError,
    disconnectThread: state.disconnectThread,
  }
}

export function selectExecutionFollowupQueueState(
  state: ThreadByIdStoreV3State,
): ThreadExecutionFollowupQueueState {
  return {
    activeThreadRole: state.activeThreadRole,
    executionFollowupQueue: state.executionFollowupQueue,
    executionQueuePauseReason: state.executionQueuePauseReason,
    executionQueueOperatorPaused: state.executionQueueOperatorPaused,
    isSending: state.isSending,
  }
}

export function selectExecutionFollowupQueueActions(
  state: ThreadByIdStoreV3State,
): ThreadExecutionFollowupQueueActions {
  return {
    enqueueFollowup: state.enqueueFollowup,
    removeQueued: state.removeQueued,
    reorderQueued: state.reorderQueued,
    sendQueuedNow: state.sendQueuedNow,
    confirmQueued: state.confirmQueued,
    retryQueued: state.retryQueued,
    setOperatorPause: state.setOperatorPause,
    syncExecutionQueueContext: state.syncExecutionQueueContext,
  }
}

export function selectFeedRenderState(state: ThreadByIdStoreV3State): ThreadFeedRenderState {
  const core = selectCore(state)
  const uiControl = selectUiControl(state)
  return {
    snapshot: core.snapshot,
    isLoading: uiControl.isLoading,
    isSending: uiControl.isSending,
    error: uiControl.error,
    lastCompletedAt: core.lastCompletedAt,
    lastDurationMs: core.lastDurationMs,
  }
}

export function selectHistoryUiState(state: ThreadByIdStoreV3State): ThreadHistoryUiState {
  return {
    hasOlderHistory: state.hasOlderHistory,
    isLoadingHistory: state.isLoadingHistory,
    historyError: state.historyError,
  }
}

export function selectComposerState(state: ThreadByIdStoreV3State): ThreadComposerState {
  return {
    snapshot: state.snapshot,
    isLoading: state.isLoading,
    isSending: state.isSending,
    isActiveTurn: Boolean(state.snapshot?.activeTurnId),
  }
}

export function selectTransportBannerState(
  state: ThreadByIdStoreV3State,
): ThreadTransportBannerState {
  return {
    streamStatus: state.streamStatus,
    error: state.error,
    forcedReloadCount: state.telemetry.forcedSnapshotReloadCount,
    lastForcedReloadReason: state.telemetry.lastForcedReloadReason,
  }
}

export function selectWorkflowActionState(state: ThreadByIdStoreV3State): ThreadWorkflowActionState {
  return {
    snapshot: state.snapshot,
    isLoading: state.isLoading,
    isSending: state.isSending,
    lastCompletedAt: state.lastCompletedAt,
    lastDurationMs: state.lastDurationMs,
  }
}

type ThreadCorePatch = Partial<ThreadCoreState>
type ThreadTransportPatch = Partial<ThreadTransportState>
type ThreadUiControlPatch = Partial<ThreadUiControlState>
type ThreadRuntimeStateV3 = Omit<
  ThreadByIdStoreV3State,
  keyof ThreadActionHandlers | keyof ThreadExecutionFollowupQueueActions
>
type ThreadDomainPatch = {
  core?: ThreadCorePatch
  transport?: ThreadTransportPatch
  uiControl?: ThreadUiControlPatch
}

function composeDomainPatch(...patches: ThreadDomainPatch[]): Partial<ThreadByIdStoreV3State> {
  const merged: Partial<ThreadByIdStoreV3State> = {}
  for (const patch of patches) {
    if (patch.core) {
      Object.assign(merged, patch.core)
    }
    if (patch.transport) {
      Object.assign(merged, patch.transport)
    }
    if (patch.uiControl) {
      Object.assign(merged, patch.uiControl)
    }
  }
  return merged
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

type ThreadHistoryState = Pick<
  ThreadByIdStoreV3State,
  'hasOlderHistory' | 'oldestVisibleSequence' | 'totalItemCount'
>

function newExecutionQueueId(prefix: string): string {
  const random =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}:${random}`
}

function executionQueueStorageKey(projectId: string, nodeId: string, threadId: string): string {
  return `${EXECUTION_FOLLOWUP_QUEUE_STORAGE_PREFIX}${projectId}::${nodeId}::${threadId}`
}

function normalizeExecutionQueueStatus(value: unknown): ExecutionFollowupQueueStatus {
  const normalized = String(value ?? '').trim()
  if (
    normalized === 'queued' ||
    normalized === 'requires_confirmation' ||
    normalized === 'sending' ||
    normalized === 'failed'
  ) {
    return normalized
  }
  return 'queued'
}

function normalizeExecutionQueueEntry(raw: unknown): ExecutionFollowupQueueEntry | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }
  const source = raw as Record<string, unknown>
  const entryId = String(source.entryId ?? '').trim()
  const text = String(source.text ?? '').trim()
  const idempotencyKey = String(source.idempotencyKey ?? '').trim()
  const createdAtRaw = Number(source.createdAtMs)
  const enqueueContextRaw =
    source.enqueueContext && typeof source.enqueueContext === 'object'
      ? (source.enqueueContext as Record<string, unknown>)
      : {}
  const latestExecutionRunId = String(enqueueContextRaw.latestExecutionRunId ?? '').trim() || null
  const planReadyRevisionRaw = enqueueContextRaw.planReadyRevision
  const planReadyRevision =
    typeof planReadyRevisionRaw === 'number' && Number.isFinite(planReadyRevisionRaw)
      ? Math.floor(planReadyRevisionRaw)
      : null
  const attemptCountRaw = Number(source.attemptCount)
  const attemptCount =
    Number.isFinite(attemptCountRaw) && attemptCountRaw >= 0 ? Math.floor(attemptCountRaw) : 0
  const lastError = String(source.lastError ?? '').trim() || null
  if (!entryId || !text || !idempotencyKey || !Number.isFinite(createdAtRaw) || createdAtRaw <= 0) {
    return null
  }
  return {
    entryId,
    text,
    idempotencyKey,
    createdAtMs: Math.floor(createdAtRaw),
    enqueueContext: {
      latestExecutionRunId,
      planReadyRevision,
    },
    status: normalizeExecutionQueueStatus(source.status),
    attemptCount,
    lastError,
  }
}

function loadExecutionQueueFromStorage(
  projectId: string,
  nodeId: string,
  threadId: string,
): ExecutionFollowupQueueEntry[] {
  if (typeof globalThis.localStorage === 'undefined') {
    return []
  }
  try {
    const raw = globalThis.localStorage.getItem(executionQueueStorageKey(projectId, nodeId, threadId))
    if (!raw) {
      return []
    }
    const payload = JSON.parse(raw)
    if (!Array.isArray(payload)) {
      return []
    }
    const normalized = payload
      .map((entry) => normalizeExecutionQueueEntry(entry))
      .filter((entry): entry is ExecutionFollowupQueueEntry => entry !== null)
      .slice(0, EXECUTION_FOLLOWUP_QUEUE_MAX_ITEMS)
    // Recovery safety: a previously persisted `sending` entry should return to `queued`.
    return normalized.map((entry) =>
      entry.status === 'sending'
        ? {
            ...entry,
            status: 'queued',
          }
        : entry,
    )
  } catch {
    return []
  }
}

function persistExecutionQueueToStorage(
  projectId: string,
  nodeId: string,
  threadId: string,
  queue: ExecutionFollowupQueueEntry[],
): void {
  if (typeof globalThis.localStorage === 'undefined') {
    return
  }
  const key = executionQueueStorageKey(projectId, nodeId, threadId)
  try {
    if (queue.length === 0) {
      globalThis.localStorage.removeItem(key)
      return
    }
    globalThis.localStorage.setItem(key, JSON.stringify(queue))
  } catch {
    // Best-effort persistence only.
  }
}

function currentExecutionQueueContext(
  state: Pick<ThreadByIdStoreV3State, 'snapshot' | 'executionQueueLatestExecutionRunId'>,
): ExecutionFollowupEnqueueContext {
  const revision = state.snapshot?.uiSignals.planReady?.revision
  return {
    latestExecutionRunId: state.executionQueueLatestExecutionRunId,
    planReadyRevision:
      typeof revision === 'number' && Number.isFinite(revision) ? Math.floor(revision) : null,
  }
}

function hasPendingInputBlocking(snapshot: ThreadSnapshotV3 | null): boolean {
  if (!snapshot) {
    return false
  }
  return snapshot.uiSignals.activeUserInputRequests.some(
    (request) => request.status === 'requested' || request.status === 'answer_submitted',
  )
}

function hasPlanReadyGate(snapshot: ThreadSnapshotV3 | null): boolean {
  const planReady = snapshot?.uiSignals.planReady
  return Boolean(
    planReady &&
      planReady.ready &&
      !planReady.failed &&
      planReady.planItemId &&
      planReady.revision != null,
  )
}

function queueHasSending(entries: ExecutionFollowupQueueEntry[]): boolean {
  return entries.some((entry) => entry.status === 'sending')
}

function compareConversationItemsByOrder(left: ConversationItemV3, right: ConversationItemV3): number {
  if (left.sequence !== right.sequence) {
    return left.sequence - right.sequence
  }
  const createdAtCompare = left.createdAt.localeCompare(right.createdAt)
  if (createdAtCompare !== 0) {
    return createdAtCompare
  }
  return left.id.localeCompare(right.id)
}

function normalizeThreadHistoryMeta(snapshot: ThreadSnapshotV3 | null): ThreadHistoryState {
  if (!snapshot) {
    return {
      hasOlderHistory: false,
      oldestVisibleSequence: null,
      totalItemCount: 0,
    }
  }
  const itemCount = snapshot.items.length
  const oldestVisibleSequence = itemCount > 0 ? snapshot.items[0].sequence : null
  const snapshotMeta = snapshot.historyMeta
  const metaTotal =
    snapshotMeta && Number.isFinite(snapshotMeta.totalItemCount)
      ? Math.max(0, Math.floor(snapshotMeta.totalItemCount))
      : itemCount
  const totalItemCount = Math.max(itemCount, metaTotal)
  const hasOlderHistory = Boolean(snapshotMeta?.hasOlder) || totalItemCount > itemCount
  return {
    hasOlderHistory,
    oldestVisibleSequence:
      snapshotMeta?.oldestVisibleSequence != null
        ? snapshotMeta.oldestVisibleSequence
        : oldestVisibleSequence,
    totalItemCount,
  }
}

function applyHistoryMeta(snapshot: ThreadSnapshotV3, history: ThreadHistoryState): ThreadSnapshotV3 {
  return {
    ...snapshot,
    historyMeta: {
      hasOlder: history.hasOlderHistory,
      oldestVisibleSequence: history.oldestVisibleSequence,
      totalItemCount: history.totalItemCount,
    },
  }
}

function enforceScrollbackCap(
  snapshot: ThreadSnapshotV3 | null,
  previousHistory: ThreadHistoryState | null = null,
): { snapshot: ThreadSnapshotV3 | null; history: ThreadHistoryState } {
  if (!snapshot) {
    return {
      snapshot: null,
      history: {
        hasOlderHistory: false,
        oldestVisibleSequence: null,
        totalItemCount: 0,
      },
    }
  }
  const sortedItems = [...snapshot.items].sort(compareConversationItemsByOrder)
  const baselineHistory = normalizeThreadHistoryMeta({
    ...snapshot,
    items: sortedItems,
  })
  let totalItemCount = Math.max(
    baselineHistory.totalItemCount,
    previousHistory?.totalItemCount ?? 0,
    sortedItems.length,
  )
  let hasOlderHistory =
    baselineHistory.hasOlderHistory || Boolean(previousHistory?.hasOlderHistory) || totalItemCount > sortedItems.length
  let nextItems = sortedItems
  if (sortedItems.length > SCROLLBACK_CAP_POLICY.effectiveHardCap) {
    nextItems = sortedItems.slice(
      Math.max(0, sortedItems.length - SCROLLBACK_CAP_POLICY.effectiveTrimTarget),
    )
    hasOlderHistory = true
  }
  totalItemCount = Math.max(totalItemCount, nextItems.length)
  const oldestVisibleSequence = nextItems.length > 0 ? nextItems[0].sequence : null
  const history: ThreadHistoryState = {
    hasOlderHistory,
    oldestVisibleSequence,
    totalItemCount,
  }
  return {
    snapshot: applyHistoryMeta(
      {
        ...snapshot,
        items: nextItems,
      },
      history,
    ),
    history,
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

function buildDisconnectedStatePatch(): ThreadRuntimeStateV3 {
  return {
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
    hasOlderHistory: false,
    oldestVisibleSequence: null,
    totalItemCount: 0,
    isLoadingHistory: false,
    historyError: null,
    executionFollowupQueue: [],
    executionQueuePauseReason: 'none',
    executionQueueOperatorPaused: false,
    executionQueueWorkflowPhase: null,
    executionQueueCanSendExecutionMessage: false,
    executionQueueLatestExecutionRunId: null,
  }
}

function buildThreadLoadStartPatch(
  projectId: string,
  nodeId: string,
  threadId: string,
  threadRole: ThreadRole,
): Partial<ThreadByIdStoreV3State> {
  return {
    ...composeDomainPatch(
      {
        core: {
          snapshot: null,
          lastEventId: null,
          lastSnapshotVersion: null,
          ...resetProcessingTelemetry(),
          hasOlderHistory: false,
          oldestVisibleSequence: null,
          totalItemCount: 0,
        },
      },
      {
        transport: {
          activeProjectId: projectId,
          activeNodeId: nodeId,
          activeThreadId: threadId,
          activeThreadRole: threadRole,
          streamStatus: 'connecting',
        },
      },
      {
        uiControl: {
          isLoading: true,
          isSending: false,
          isLoadingHistory: false,
          telemetry: resetTelemetryV3(),
          error: null,
          historyError: null,
        },
      },
    ),
    executionFollowupQueue: [],
    executionQueuePauseReason: 'none',
    executionQueueOperatorPaused: false,
    executionQueueWorkflowPhase: null,
    executionQueueCanSendExecutionMessage: false,
    executionQueueLatestExecutionRunId: null,
  }
}

function buildSnapshotHydratedPatch(
  state: ThreadByIdStoreV3State,
  snapshot: ThreadSnapshotV3,
  options: { telemetry?: ThreadByIdTelemetryV3 } = {},
): Partial<ThreadByIdStoreV3State> {
  const previousHistory: ThreadHistoryState = {
    hasOlderHistory: state.hasOlderHistory,
    oldestVisibleSequence: state.oldestVisibleSequence,
    totalItemCount: state.totalItemCount,
  }
  const capped = enforceScrollbackCap(snapshot, previousHistory)
  return composeDomainPatch(
    {
      core: {
        snapshot: capped.snapshot,
        lastEventId: null,
        lastSnapshotVersion: snapshot.snapshotVersion,
        ...seedRunningTelemetry(state, capped.snapshot),
        hasOlderHistory: capped.history.hasOlderHistory,
        oldestVisibleSequence: capped.history.oldestVisibleSequence,
        totalItemCount: capped.history.totalItemCount,
      },
    },
    {
      transport: {
        streamStatus: 'connecting',
      },
    },
    {
      uiControl: {
        isLoading: false,
        isLoadingHistory: false,
        error: null,
        historyError: null,
        ...(options.telemetry ? { telemetry: options.telemetry } : {}),
      },
    },
  )
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
    set((state) =>
      composeDomainPatch({
        uiControl: {
          telemetry: {
            ...state.telemetry,
            forcedSnapshotReloadCount: state.telemetry.forcedSnapshotReloadCount + 1,
            lastForcedReloadReason: policy.reason,
          },
        },
      }),
    )
  }

  if (policy.setLoading) {
    const errorMessage = policy.message ?? (policy.kind === 'soft' ? policy.reason ?? null : null)
    set(
      composeDomainPatch(
        {
          transport: {
            streamStatus: 'connecting',
          },
        },
        {
          uiControl: {
            isLoading: true,
            error: errorMessage,
          },
        },
      ),
    )
  }

  try {
    const snapshot = await api.getThreadSnapshotByIdV3(projectId, nodeId, threadId, SNAPSHOT_LIVE_LIMIT)
    const latestState = get()
    if (
      !isCurrentGeneration(generation) ||
      !isActiveTarget(latestState, projectId, nodeId, threadId, threadRole)
    ) {
      return
    }
    set(buildSnapshotHydratedPatch(latestState, snapshot))
    reconcileResolveFallbackTimers(get().snapshot)
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
    set(
      composeDomainPatch(
        {
          transport: {
            streamStatus: 'error',
          },
        },
        {
          uiControl: {
            isLoading: false,
            error: error instanceof Error ? error.message : String(error),
          },
        },
      ),
    )
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
  set((state) =>
    composeDomainPatch(
      {
        transport: {
          streamStatus: 'reconnecting',
        },
      },
      {
        uiControl: {
          telemetry: {
            ...state.telemetry,
            streamReconnectCount: state.telemetry.streamReconnectCount + 1,
          },
        },
      },
    ),
  )
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
        set(
          composeDomainPatch(
            {
              transport: {
                streamStatus: 'error',
              },
            },
            {
              uiControl: {
                error: reason,
              },
            },
          ),
        )
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
      set(
        composeDomainPatch(
          {
            transport: {
              streamStatus: 'error',
            },
          },
          {
            uiControl: {
              error: error instanceof Error ? error.message : String(error),
            },
          },
        ),
      )
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
  set(
    composeDomainPatch({
      transport: {
        streamStatus: 'connecting',
      },
    }),
  )
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
    set((state) =>
      composeDomainPatch(
        {
          transport: {
            streamStatus: 'error',
          },
        },
        {
          uiControl: {
            error: reason,
            telemetry: {
              ...state.telemetry,
              envelope_validation_failure_count:
                state.telemetry.envelope_validation_failure_count + 1,
            },
          },
        },
      ),
    )
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
      return composeDomainPatch(
        {
          core: {
            lastSnapshotVersion: envelope.snapshotVersion ?? state.lastSnapshotVersion,
          },
        },
        {
          transport: {
            streamStatus: 'open',
          },
        },
        {
          uiControl: {
            telemetry: {
              ...state.telemetry,
              legacy_fallback_used_count:
                state.telemetry.legacy_fallback_used_count + (legacyFallbackUsed ? 1 : 0),
              firstMeaningfulFrameLatencyMs:
                state.telemetry.firstMeaningfulFrameLatencyMs ??
                Math.max(0, Date.now() - streamSubscribedAt),
            },
          },
        },
      )
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
    let workingHistory: ThreadHistoryState = {
      hasOlderHistory: currentState.hasOlderHistory,
      oldestVisibleSequence: currentState.oldestVisibleSequence,
      totalItemCount: currentState.totalItemCount,
    }
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
          set((state) =>
            composeDomainPatch(
              {
                transport: {
                  streamStatus: 'error',
                },
              },
              {
                uiControl: {
                  error: error.message,
                  telemetry: {
                    ...state.telemetry,
                    applyErrorCount: state.telemetry.applyErrorCount + 1,
                  },
                },
              },
            ),
          )
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

    const cappedResult = enforceScrollbackCap(workingSnapshot, workingHistory)
    workingSnapshot = cappedResult.snapshot
    workingHistory = cappedResult.history

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
      return composeDomainPatch(
        {
          core: {
            snapshot: workingSnapshot,
            lastEventId: workingLastEventId,
            lastSnapshotVersion: workingLastSnapshotVersion,
            ...processingTelemetry,
            hasOlderHistory: workingHistory.hasOlderHistory,
            oldestVisibleSequence: workingHistory.oldestVisibleSequence,
            totalItemCount: workingHistory.totalItemCount,
          },
        },
        {
          transport: {
            streamStatus: 'open',
          },
        },
        {
          uiControl: {
            isLoading: workingIsLoading,
            error: workingError,
            historyError: null,
            telemetry: {
              ...state.telemetry,
              legacy_fallback_used_count:
                state.telemetry.legacy_fallback_used_count + legacyFallbackUsedCount,
              batchedFlushCount: state.telemetry.batchedFlushCount + 1,
              batchedEventsApplied: state.telemetry.batchedEventsApplied + appliedEventCount,
              forcedFlushCount: state.telemetry.forcedFlushCount + forcedFlushDelta,
              fastAppendHitCount: state.telemetry.fastAppendHitCount + fastAppendHitCount,
              fastAppendFallbackCount: state.telemetry.fastAppendFallbackCount + fastAppendFallbackCount,
            },
          },
        },
      )
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
    set(
      composeDomainPatch({
        transport: {
          streamStatus: 'open',
        },
      }),
    )
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

export const useThreadByIdStoreV3 = create<ThreadByIdStoreV3State>((set, get) => {
  const persistQueueForCurrentThread = (
    state: Pick<ThreadByIdStoreV3State, 'activeProjectId' | 'activeNodeId' | 'activeThreadId'>,
    queue: ExecutionFollowupQueueEntry[],
  ) => {
    if (!state.activeProjectId || !state.activeNodeId || !state.activeThreadId) {
      return
    }
    persistExecutionQueueToStorage(
      state.activeProjectId,
      state.activeNodeId,
      state.activeThreadId,
      queue,
    )
  }

  const normalizeQueueIndexes = (
    entries: ExecutionFollowupQueueEntry[],
    fromIndex: number,
    toIndex: number,
  ): ExecutionFollowupQueueEntry[] => {
    if (entries.length <= 1) {
      return entries
    }
    const from = Math.max(0, Math.min(entries.length - 1, Math.floor(fromIndex)))
    const to = Math.max(0, Math.min(entries.length - 1, Math.floor(toIndex)))
    if (from === to) {
      return entries
    }
    const next = [...entries]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    return next
  }

  const evaluateQueuePauseReason = (
    state: Pick<
      ThreadByIdStoreV3State,
      | 'snapshot'
      | 'activeThreadRole'
      | 'executionQueueOperatorPaused'
      | 'executionQueueWorkflowPhase'
      | 'executionQueueCanSendExecutionMessage'
    >,
  ): ExecutionFollowupQueuePauseReason => {
    if (state.activeThreadRole !== 'execution') {
      return 'workflow_blocked'
    }
    if (state.executionQueueOperatorPaused) {
      return 'operator_pause'
    }
    if (state.snapshot?.processingState === 'waiting_user_input' || hasPendingInputBlocking(state.snapshot)) {
      return 'runtime_waiting_input'
    }
    if (hasPlanReadyGate(state.snapshot)) {
      return 'plan_ready_gate'
    }
    if (
      state.executionQueueWorkflowPhase !== 'execution_decision_pending' ||
      !state.executionQueueCanSendExecutionMessage
    ) {
      return 'workflow_blocked'
    }
    if (!state.snapshot || state.snapshot.activeTurnId || state.snapshot.processingState !== 'idle') {
      return 'workflow_blocked'
    }
    return 'none'
  }

  const sendWindowIsOpen = (
    state: Pick<
      ThreadByIdStoreV3State,
      | 'activeThreadRole'
      | 'executionQueueOperatorPaused'
      | 'executionQueueWorkflowPhase'
      | 'executionQueueCanSendExecutionMessage'
      | 'snapshot'
    >,
    options: { manual: boolean; allowPlanReadyGate: boolean },
  ): boolean => {
    if (state.activeThreadRole !== 'execution') {
      return false
    }
    if (!state.snapshot) {
      return false
    }
    if (!options.manual && state.executionQueueOperatorPaused) {
      return false
    }
    if (
      state.executionQueueWorkflowPhase !== 'execution_decision_pending' ||
      !state.executionQueueCanSendExecutionMessage
    ) {
      return false
    }
    if (state.snapshot.activeTurnId || state.snapshot.processingState !== 'idle') {
      return false
    }
    if (hasPendingInputBlocking(state.snapshot)) {
      return false
    }
    if (!options.allowPlanReadyGate && hasPlanReadyGate(state.snapshot)) {
      return false
    }
    return true
  }

  const queueEntryRequiresConfirmation = (
    entry: ExecutionFollowupQueueEntry,
    nowMs: number,
    currentContext: ExecutionFollowupEnqueueContext,
  ): boolean => {
    if (nowMs - entry.createdAtMs > EXECUTION_FOLLOWUP_AUTO_SEND_MAX_AGE_MS) {
      return true
    }
    if (
      entry.enqueueContext.latestExecutionRunId &&
      currentContext.latestExecutionRunId &&
      entry.enqueueContext.latestExecutionRunId !== currentContext.latestExecutionRunId
    ) {
      return true
    }
    const previousRevision = entry.enqueueContext.planReadyRevision
    const currentRevision = currentContext.planReadyRevision
    if (previousRevision !== currentRevision && (previousRevision != null || currentRevision != null)) {
      return true
    }
    return false
  }

  const startThreadTurnRequest = async (
    text: string,
    metadata: Record<string, unknown> = {},
  ): Promise<{ ok: true } | { ok: false; error: string }> => {
    const { activeProjectId, activeNodeId, activeThreadId, activeThreadRole, snapshot } = get()
    if (!activeProjectId || !activeNodeId || !activeThreadId || !activeThreadRole || !snapshot) {
      return { ok: false, error: 'Thread is not ready.' }
    }
    if (activeThreadRole !== 'execution' && activeThreadRole !== 'ask_planning') {
      return { ok: false, error: 'Audit review is read-only in the V3 execution/audit flow.' }
    }
    const generation = threadGeneration
    const sendingRole = activeThreadRole
    set(
      composeDomainPatch({
        uiControl: {
          isSending: true,
          error: null,
        },
      }),
    )

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
        return composeDomainPatch(
          {
            core: {
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
            },
          },
          {
            uiControl: {
              isSending: false,
            },
          },
        )
      })
      return { ok: true }
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
        return { ok: false, error: error instanceof Error ? error.message : String(error) }
      }
      const reason = error instanceof Error ? error.message : String(error)
      set(
        composeDomainPatch({
          uiControl: {
            isSending: false,
            error: reason,
          },
        }),
      )
      return { ok: false, error: reason }
    }
  }

  const attemptExecutionQueueFlush = async (options: {
    manualEntryId?: string
    confirmedEntryId?: string
    allowPlanReadyGate?: boolean
  } = {}): Promise<void> => {
    const state = get()
    if (state.activeThreadRole !== 'execution') {
      return
    }
    if (!state.executionFollowupQueue.length) {
      return
    }
    if (queueHasSending(state.executionFollowupQueue)) {
      return
    }
    const manualMode = Boolean(options.manualEntryId)
    const windowOpen = sendWindowIsOpen(state, {
      manual: manualMode,
      allowPlanReadyGate: Boolean(options.allowPlanReadyGate),
    })
    if (!windowOpen) {
      set({ executionQueuePauseReason: evaluateQueuePauseReason(get()) })
      return
    }

    const entry =
      options.manualEntryId != null
        ? state.executionFollowupQueue.find((candidate) => candidate.entryId === options.manualEntryId) ?? null
        : state.executionFollowupQueue.find((candidate) => candidate.status === 'queued') ?? null
    if (!entry || entry.status === 'sending') {
      return
    }

    const nowMs = Date.now()
    const context = currentExecutionQueueContext(state)
    const requiresConfirmation = queueEntryRequiresConfirmation(entry, nowMs, context)
    const confirmedByAction = options.confirmedEntryId != null && options.confirmedEntryId === entry.entryId
    if (requiresConfirmation && !confirmedByAction) {
      set((current) => {
        const nextQueue = current.executionFollowupQueue.map((candidate) =>
          candidate.entryId === entry.entryId
            ? {
                ...candidate,
                status: 'requires_confirmation' as const,
                lastError: null,
              }
            : candidate,
        )
        persistQueueForCurrentThread(current, nextQueue)
        return {
          executionFollowupQueue: nextQueue,
          executionQueuePauseReason: evaluateQueuePauseReason(current),
        }
      })
      return
    }

    set((current) => {
      const nextQueue = current.executionFollowupQueue.map((candidate) =>
        candidate.entryId === entry.entryId
          ? {
              ...candidate,
              status: 'sending' as const,
              lastError: null,
            }
          : candidate,
      )
      persistQueueForCurrentThread(current, nextQueue)
      return {
        executionFollowupQueue: nextQueue,
        executionQueuePauseReason: evaluateQueuePauseReason(current),
      }
    })

    const result = await startThreadTurnRequest(entry.text, {
      idempotencyKey: entry.idempotencyKey,
    })

    set((current) => {
      const existing = current.executionFollowupQueue.find((candidate) => candidate.entryId === entry.entryId)
      if (!existing) {
        return {}
      }
      let nextQueue: ExecutionFollowupQueueEntry[]
      if (result.ok) {
        nextQueue = current.executionFollowupQueue.filter((candidate) => candidate.entryId !== entry.entryId)
      } else {
        nextQueue = current.executionFollowupQueue.map((candidate) =>
          candidate.entryId === entry.entryId
            ? {
                ...candidate,
                status: 'failed' as const,
                attemptCount: candidate.attemptCount + 1,
                lastError: result.error,
              }
            : candidate,
        )
      }
      persistQueueForCurrentThread(current, nextQueue)
      return {
        executionFollowupQueue: nextQueue,
        executionQueuePauseReason: evaluateQueuePauseReason({
          ...current,
        }),
      }
    })

    if (result.ok) {
      await attemptExecutionQueueFlush()
    }
  }

  return {
  ...buildDisconnectedStatePatch(),

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
    set(buildThreadLoadStartPatch(projectId, nodeId, threadId, threadRole))

    try {
      const snapshot = await api.getThreadSnapshotByIdV3(projectId, nodeId, threadId, SNAPSHOT_LIVE_LIMIT)
      const latestState = get()
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(latestState, projectId, nodeId, threadId, threadRole)
      ) {
        return
      }
      set((state) =>
        buildSnapshotHydratedPatch(state, snapshot, {
          telemetry: {
            ...state.telemetry,
            firstFrameLatencyMs: Math.max(0, Date.now() - loadStartedAt),
          },
        }),
      )
      if (threadRole === 'execution') {
        const hydratedQueue = loadExecutionQueueFromStorage(projectId, nodeId, threadId)
        set((state) => {
          persistQueueForCurrentThread(state, hydratedQueue)
          return {
            executionFollowupQueue: hydratedQueue,
            executionQueuePauseReason: evaluateQueuePauseReason(state),
          }
        })
      } else {
        set({
          executionFollowupQueue: [],
          executionQueuePauseReason: 'none',
          executionQueueOperatorPaused: false,
        })
      }
      reconcileResolveFallbackTimers(get().snapshot)
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
      set(
        composeDomainPatch(
          {
            transport: {
              streamStatus: 'error',
            },
          },
          {
            uiControl: {
              isLoading: false,
              error: error instanceof Error ? error.message : String(error),
            },
          },
        ),
      )
    }
  },

  async loadMoreHistory() {
    const state = get()
    const { activeProjectId, activeNodeId, activeThreadId, activeThreadRole, snapshot } = state
    if (!activeProjectId || !activeNodeId || !activeThreadId || !activeThreadRole || !snapshot) {
      return
    }
    if (state.isLoadingHistory || !state.hasOlderHistory) {
      return
    }
    const beforeSequence = state.oldestVisibleSequence ?? (snapshot.items.length > 0 ? snapshot.items[0].sequence : null)
    if (beforeSequence == null) {
      return
    }

    const generation = threadGeneration
    set(
      composeDomainPatch({
        uiControl: {
          isLoadingHistory: true,
          historyError: null,
        },
      }),
    )

    try {
      const page = await api.getThreadHistoryPageByIdV3(activeProjectId, activeNodeId, activeThreadId, {
        beforeSequence,
        limit: HISTORY_PAGE_LIMIT,
      })
      const latestState = get()
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(latestState, activeProjectId, activeNodeId, activeThreadId, activeThreadRole)
      ) {
        return
      }

      set((current) => {
        if (
          !isCurrentGeneration(generation) ||
          !isActiveTarget(current, activeProjectId, activeNodeId, activeThreadId, activeThreadRole) ||
          !current.snapshot
        ) {
          return {}
        }
        const existingIds = new Set(current.snapshot.items.map((item) => item.id))
        const prependItems = page.items.filter((item) => !existingIds.has(item.id))
        const mergedItems = [...prependItems, ...current.snapshot.items].sort(compareConversationItemsByOrder)
        const totalItemCount = Math.max(
          current.totalItemCount,
          Number.isFinite(page.total_item_count) ? Math.max(0, Math.floor(page.total_item_count)) : 0,
          mergedItems.length,
        )
        const mergedHistory: ThreadHistoryState = {
          hasOlderHistory: Boolean(page.has_more),
          oldestVisibleSequence: mergedItems.length > 0 ? mergedItems[0].sequence : null,
          totalItemCount,
        }
        const mergedSnapshot = applyHistoryMeta(
          {
            ...current.snapshot,
            items: mergedItems,
          },
          mergedHistory,
        )
        const capped = enforceScrollbackCap(
          mergedSnapshot,
          mergedHistory,
        )
        const nextSnapshot = capped.snapshot ?? current.snapshot
        return composeDomainPatch(
          {
            core: {
              snapshot: nextSnapshot,
              hasOlderHistory: capped.history.hasOlderHistory,
              oldestVisibleSequence: capped.history.oldestVisibleSequence,
              totalItemCount: capped.history.totalItemCount,
            },
          },
          {
            uiControl: {
              isLoadingHistory: false,
              historyError: null,
            },
          },
        )
      })
    } catch (error) {
      const latestState = get()
      if (
        !isCurrentGeneration(generation) ||
        !isActiveTarget(latestState, activeProjectId, activeNodeId, activeThreadId, activeThreadRole)
      ) {
        return
      }
      set(
        composeDomainPatch({
          uiControl: {
            isLoadingHistory: false,
            historyError: error instanceof Error ? error.message : String(error),
          },
        }),
      )
    }
  },

  async sendTurn(text: string, metadata: Record<string, unknown> = {}) {
    await startThreadTurnRequest(text, metadata)
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
      return composeDomainPatch(
        {
          core: {
            snapshot: applyOptimisticUserInputSubmissionV3(
              state.snapshot,
              requestId,
              answers,
              submittedAt,
            ),
          },
        },
        {
          uiControl: {
            error: null,
          },
        },
      )
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
      set(
        composeDomainPatch({
          uiControl: {
            error: reason,
          },
        }),
      )
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
    set(
      composeDomainPatch({
        uiControl: {
          isSending: true,
          error: null,
        },
      }),
    )
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
        return composeDomainPatch(
          {
            core: {
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
              lastSnapshotVersion: Math.max(
                state.lastSnapshotVersion ?? 0,
                response.snapshotVersion ?? 0,
              ),
              processingStartedAt: state.processingStartedAt ?? Date.now(),
            },
          },
          {
            uiControl: {
              isSending: false,
            },
          },
        )
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
      set(
        composeDomainPatch({
          uiControl: {
            isSending: false,
            error: error instanceof Error ? error.message : String(error),
          },
        }),
      )
    }
  },

  async enqueueFollowup(text: string) {
    const state = get()
    const cleaned = String(text ?? '').trim()
    if (!cleaned) {
      return
    }
    if (
      state.activeThreadRole !== 'execution' ||
      !state.activeProjectId ||
      !state.activeNodeId ||
      !state.activeThreadId
    ) {
      // Execution-only queue. Other lanes keep existing direct-send behavior.
      await startThreadTurnRequest(cleaned)
      return
    }
    if (queueHasSending(state.executionFollowupQueue)) {
      return
    }

    const cappedQueue = state.executionFollowupQueue.slice(0, EXECUTION_FOLLOWUP_QUEUE_MAX_ITEMS)
    const nextQueue = [
      ...cappedQueue,
      {
        entryId: newExecutionQueueId('q'),
        text: cleaned,
        idempotencyKey: newExecutionQueueId('exec_followup'),
        createdAtMs: Date.now(),
        enqueueContext: currentExecutionQueueContext(state),
        status: 'queued' as const,
        attemptCount: 0,
        lastError: null,
      },
    ].slice(-EXECUTION_FOLLOWUP_QUEUE_MAX_ITEMS)

    set((current) => {
      persistQueueForCurrentThread(current, nextQueue)
      return {
        executionFollowupQueue: nextQueue,
        executionQueuePauseReason: evaluateQueuePauseReason(current),
      }
    })
    await attemptExecutionQueueFlush()
  },

  removeQueued(entryId: string) {
    const id = String(entryId ?? '').trim()
    if (!id) {
      return
    }
    const state = get()
    if (queueHasSending(state.executionFollowupQueue)) {
      return
    }
    const nextQueue = state.executionFollowupQueue.filter((entry) => entry.entryId !== id)
    set((current) => {
      persistQueueForCurrentThread(current, nextQueue)
      return {
        executionFollowupQueue: nextQueue,
        executionQueuePauseReason: evaluateQueuePauseReason(current),
      }
    })
  },

  reorderQueued(fromIndex: number, toIndex: number) {
    const state = get()
    if (queueHasSending(state.executionFollowupQueue)) {
      return
    }
    const nextQueue = normalizeQueueIndexes(state.executionFollowupQueue, fromIndex, toIndex)
    set((current) => {
      persistQueueForCurrentThread(current, nextQueue)
      return {
        executionFollowupQueue: nextQueue,
        executionQueuePauseReason: evaluateQueuePauseReason(current),
      }
    })
  },

  async sendQueuedNow(entryId: string) {
    const id = String(entryId ?? '').trim()
    if (!id) {
      return
    }
    await attemptExecutionQueueFlush({
      manualEntryId: id,
      allowPlanReadyGate: true,
    })
  },

  async confirmQueued(entryId: string) {
    const id = String(entryId ?? '').trim()
    if (!id) {
      return
    }
    const state = get()
    if (queueHasSending(state.executionFollowupQueue)) {
      return
    }
    const context = currentExecutionQueueContext(state)
    const nextQueue = state.executionFollowupQueue.map((entry) =>
      entry.entryId === id
        ? {
            ...entry,
            status: 'queued' as const,
            createdAtMs: Date.now(),
            enqueueContext: context,
            lastError: null,
          }
        : entry,
    )
    set((current) => {
      persistQueueForCurrentThread(current, nextQueue)
      return {
        executionFollowupQueue: nextQueue,
        executionQueuePauseReason: evaluateQueuePauseReason(current),
      }
    })
    await attemptExecutionQueueFlush({
      manualEntryId: id,
      confirmedEntryId: id,
      allowPlanReadyGate: true,
    })
  },

  async retryQueued(entryId: string) {
    const id = String(entryId ?? '').trim()
    if (!id) {
      return
    }
    const state = get()
    if (queueHasSending(state.executionFollowupQueue)) {
      return
    }
    const nextQueue = state.executionFollowupQueue.map((entry) =>
      entry.entryId === id && entry.status === 'failed'
        ? {
            ...entry,
            status: 'queued' as const,
            lastError: null,
          }
        : entry,
    )
    set((current) => {
      persistQueueForCurrentThread(current, nextQueue)
      return {
        executionFollowupQueue: nextQueue,
        executionQueuePauseReason: evaluateQueuePauseReason(current),
      }
    })
    await attemptExecutionQueueFlush({
      manualEntryId: id,
      allowPlanReadyGate: true,
    })
  },

  setOperatorPause(paused: boolean) {
    set((state) => ({
      executionQueueOperatorPaused: Boolean(paused),
      executionQueuePauseReason: evaluateQueuePauseReason({
        ...state,
        executionQueueOperatorPaused: Boolean(paused),
      }),
    }))
  },

  async syncExecutionQueueContext(context: {
    workflowPhase: string | null
    canSendExecutionMessage: boolean
    latestExecutionRunId: string | null
  }) {
    const workflowPhase = context.workflowPhase ? String(context.workflowPhase) : null
    const latestExecutionRunId = context.latestExecutionRunId
      ? String(context.latestExecutionRunId)
      : null
    set((state) => ({
      executionQueueWorkflowPhase: workflowPhase,
      executionQueueCanSendExecutionMessage: Boolean(context.canSendExecutionMessage),
      executionQueueLatestExecutionRunId: latestExecutionRunId,
      executionQueuePauseReason: evaluateQueuePauseReason({
        ...state,
        executionQueueWorkflowPhase: workflowPhase,
        executionQueueCanSendExecutionMessage: Boolean(context.canSendExecutionMessage),
      }),
    }))
    await attemptExecutionQueueFlush()
  },

  recordRenderError(reason: string) {
    set((state) =>
      composeDomainPatch({
        uiControl: {
          error: reason,
          telemetry: {
            ...state.telemetry,
            renderErrorCount: state.telemetry.renderErrorCount + 1,
          },
        },
      }),
    )
  },

  disconnectThread() {
    threadGeneration += 1
    clearReconnectTimer()
    clearResolveFallbackTimers()
    closeThreadEventSource()
    set(buildDisconnectedStatePatch())
  },
  }
})
