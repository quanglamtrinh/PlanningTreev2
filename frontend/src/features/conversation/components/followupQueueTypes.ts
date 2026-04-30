export type FollowupQueueStatus = 'queued' | 'sending' | 'requires_confirmation' | 'failed'

export type FollowupQueueEntry = {
  entryId: string
  text: string
  status: FollowupQueueStatus
  attemptCount: number
  lastError?: string | null
  confirmationReason?: string | null
}

export type ExecutionQueuePauseReason =
  | 'none'
  | 'runtime_waiting_input'
  | 'plan_ready_gate'
  | 'operator_pause'
  | 'blocked'

export type AskQueuePauseReason =
  | 'none'
  | 'snapshot_unavailable'
  | 'stream_or_state_mismatch'
  | 'active_turn_running'
  | 'waiting_user_input'
  | 'operator_pause'
  | 'confirmation_required'

export type ExecutionFollowupQueueState = {
  executionFollowupQueue: FollowupQueueEntry[]
  isSending: boolean
  executionQueuePauseReason: ExecutionQueuePauseReason
  executionQueueOperatorPaused: boolean
}

export type AskFollowupQueueState = {
  askFollowupQueue: FollowupQueueEntry[]
  isSending: boolean
  askQueuePauseReason: AskQueuePauseReason
}

export type ExecutionFollowupQueueActions = {
  removeQueued: (entryId: string) => void
  reorderQueued: (fromIndex: number, toIndex: number) => void
  sendQueuedNow: (entryId: string) => Promise<void>
  confirmQueued: (entryId: string) => Promise<void>
  retryQueued: (entryId: string) => Promise<void>
  setOperatorPause: (paused: boolean) => void
}

export type AskFollowupQueueActions = {
  removeQueued: (entryId: string) => void
  reorderAskQueued: (fromIndex: number, toIndex: number) => void
  sendAskQueuedNow: (entryId: string) => Promise<void>
  confirmQueued: (entryId: string) => Promise<void>
  retryAskQueued: (entryId: string) => Promise<void>
}
