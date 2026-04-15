import type { ThreadSnapshotV3 } from '../../../api/types'
import type { QueueCoreEntry, QueueLane } from './threadQueueCoreV3'

export const EXECUTION_QUEUE_AUTO_SEND_MAX_AGE_MS = 90_000
export const ASK_QUEUE_AUTO_SEND_MAX_AGE_MS = 90_000

export type ExecutionQueuePauseReason =
  | 'none'
  | 'runtime_waiting_input'
  | 'plan_ready_gate'
  | 'operator_pause'
  | 'workflow_blocked'

export type AskQueuePauseReason =
  | 'none'
  | 'snapshot_unavailable'
  | 'stream_or_state_mismatch'
  | 'active_turn_running'
  | 'waiting_user_input'
  | 'operator_pause'

export type ExecutionQueueContext = {
  latestExecutionRunId: string | null
  planReadyRevision: number | null
}

export type AskQueueContext = {
  threadId: string | null
  snapshotVersion: number | null
  staleMarker: boolean
}

export type ExecutionQueueEntry = QueueCoreEntry<ExecutionQueueContext>
export type AskQueueEntry = QueueCoreEntry<AskQueueContext>

export type ExecutionQueuePolicyState = {
  snapshot: ThreadSnapshotV3 | null
  operatorPaused: boolean
  workflowPhase: string | null
  canSendExecutionMessage: boolean
}

export type AskQueuePolicyState = {
  snapshot: ThreadSnapshotV3 | null
  operatorPaused: boolean
  streamOrStateMismatch: boolean
}

export type ExecutionSendWindowOptions = {
  manual: boolean
  allowPlanReadyGate: boolean
}

export type AskSendWindowOptions = {
  streamOrStateMismatch: boolean
}

export type LaneQueuePolicyAdapter<
  TLane extends QueueLane,
  TState,
  TEntry,
  TContext,
  TPauseReason extends string,
  TSendWindowOptions,
> = {
  evaluatePauseReason: (lane: TLane, state: TState, options: TSendWindowOptions) => TPauseReason
  sendWindowIsOpen: (lane: TLane, state: TState, options: TSendWindowOptions) => boolean
  requiresConfirmation: (lane: TLane, entry: TEntry, currentContext: TContext, nowMs: number) => boolean
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

export const executionQueuePolicyAdapter: LaneQueuePolicyAdapter<
  'execution',
  ExecutionQueuePolicyState,
  ExecutionQueueEntry,
  ExecutionQueueContext,
  ExecutionQueuePauseReason,
  ExecutionSendWindowOptions
> = {
  evaluatePauseReason(lane, state) {
    if (lane !== 'execution') {
      return 'workflow_blocked'
    }
    if (state.operatorPaused) {
      return 'operator_pause'
    }
    if (state.snapshot?.processingState === 'waiting_user_input' || hasPendingInputBlocking(state.snapshot)) {
      return 'runtime_waiting_input'
    }
    if (hasPlanReadyGate(state.snapshot)) {
      return 'plan_ready_gate'
    }
    if (state.workflowPhase !== 'execution_decision_pending' || !state.canSendExecutionMessage) {
      return 'workflow_blocked'
    }
    if (!state.snapshot || state.snapshot.activeTurnId || state.snapshot.processingState !== 'idle') {
      return 'workflow_blocked'
    }
    return 'none'
  },
  sendWindowIsOpen(lane, state, options) {
    if (lane !== 'execution') {
      return false
    }
    if (!state.snapshot) {
      return false
    }
    if (!options.manual && state.operatorPaused) {
      return false
    }
    if (state.workflowPhase !== 'execution_decision_pending' || !state.canSendExecutionMessage) {
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
  },
  requiresConfirmation(lane, entry, currentContext, nowMs) {
    if (lane !== 'execution') {
      return false
    }
    if (nowMs - entry.createdAtMs > EXECUTION_QUEUE_AUTO_SEND_MAX_AGE_MS) {
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
  },
}

export const askQueuePolicyAdapter: LaneQueuePolicyAdapter<
  'ask_planning',
  AskQueuePolicyState,
  AskQueueEntry,
  AskQueueContext,
  AskQueuePauseReason,
  AskSendWindowOptions
> = {
  evaluatePauseReason(lane, state, options) {
    if (lane !== 'ask_planning') {
      return 'stream_or_state_mismatch'
    }
    if (!state.snapshot) {
      return 'snapshot_unavailable'
    }
    if (options.streamOrStateMismatch || state.streamOrStateMismatch) {
      return 'stream_or_state_mismatch'
    }
    if (state.operatorPaused) {
      return 'operator_pause'
    }
    if (state.snapshot.activeTurnId != null || state.snapshot.processingState !== 'idle') {
      return 'active_turn_running'
    }
    if (hasPendingInputBlocking(state.snapshot)) {
      return 'waiting_user_input'
    }
    return 'none'
  },
  sendWindowIsOpen(lane, state, options) {
    return this.evaluatePauseReason(lane, state, options) === 'none'
  },
  requiresConfirmation(lane, entry, currentContext, nowMs) {
    if (lane !== 'ask_planning') {
      return false
    }
    if (nowMs - entry.createdAtMs > ASK_QUEUE_AUTO_SEND_MAX_AGE_MS) {
      return true
    }
    if (
      entry.enqueueContext.threadId &&
      currentContext.threadId &&
      entry.enqueueContext.threadId !== currentContext.threadId
    ) {
      return true
    }
    if (
      entry.enqueueContext.snapshotVersion !== currentContext.snapshotVersion &&
      (entry.enqueueContext.snapshotVersion != null || currentContext.snapshotVersion != null)
    ) {
      return true
    }
    if (currentContext.staleMarker) {
      return true
    }
    return false
  },
}

export const laneQueuePolicyAdapters = {
  execution: executionQueuePolicyAdapter,
  ask_planning: askQueuePolicyAdapter,
} as const

