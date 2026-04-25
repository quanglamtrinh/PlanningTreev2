import type { ThreadTab } from '../surfaceRouting'
import type {
  AskFollowupQueueStatus,
  ExecutionFollowupQueueStatus,
  ThreadAskFollowupQueueState,
  ThreadExecutionFollowupQueueState,
} from '../state/threadByIdStoreV3'

export type BreadcrumbThreadTabDesignItem = {
  value: ThreadTab
  label: string
  testId: string
}

export const BREADCRUMB_THREAD_TAB_DESIGN: ReadonlyArray<BreadcrumbThreadTabDesignItem> = [
  { value: 'ask', label: 'Ask', testId: 'breadcrumb-thread-tab-ask' },
  { value: 'execution', label: 'Execution', testId: 'breadcrumb-thread-tab-execution' },
  { value: 'audit', label: 'Review', testId: 'breadcrumb-thread-tab-audit' },
  { value: 'package', label: 'Package', testId: 'breadcrumb-thread-tab-package' },
]

export function renderQueueStatusLabel(
  status: ExecutionFollowupQueueStatus | AskFollowupQueueStatus,
): string {
  if (status === 'queued') {
    return 'Queued'
  }
  if (status === 'requires_confirmation') {
    return 'Needs confirmation'
  }
  if (status === 'sending') {
    return 'Sending'
  }
  return 'Failed'
}

export function renderExecutionQueuePauseReasonLabel(
  reason: ThreadExecutionFollowupQueueState['executionQueuePauseReason'],
): string {
  if (reason === 'none') {
    return 'Auto-send ready'
  }
  if (reason === 'runtime_waiting_input') {
    return 'Paused: waiting for required input'
  }
  if (reason === 'plan_ready_gate') {
    return 'Paused: plan-ready gate'
  }
  if (reason === 'operator_pause') {
    return 'Paused by operator'
  }
  return 'Paused: workflow blocked'
}

export function renderAskQueuePauseReasonLabel(
  reason: ThreadAskFollowupQueueState['askQueuePauseReason'],
): string {
  if (reason === 'none') {
    return 'Auto-send ready'
  }
  if (reason === 'snapshot_unavailable') {
    return 'Paused: snapshot unavailable'
  }
  if (reason === 'stream_or_state_mismatch') {
    return 'Paused: stream/state mismatch'
  }
  if (reason === 'active_turn_running') {
    return 'Paused: active turn running'
  }
  if (reason === 'waiting_user_input') {
    return 'Paused: waiting for required input'
  }
  if (reason === 'operator_pause') {
    return 'Paused by operator'
  }
  return 'Paused: confirmation required'
}

export function renderAskConfirmationReasonLabel(reason: string | null | undefined): string {
  if (reason === 'stale_age') {
    return 'Queued ask is stale. Confirm before sending.'
  }
  if (reason === 'thread_drift') {
    return 'Thread context changed. Confirm before sending.'
  }
  if (reason === 'snapshot_drift') {
    return 'Snapshot context changed. Confirm before sending.'
  }
  if (reason === 'stale_marker') {
    return 'Stream context changed. Confirm before sending.'
  }
  return 'Queued ask requires confirmation before sending.'
}
