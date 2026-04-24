export type ConnectionPhase = 'disconnected' | 'connecting' | 'initialized' | 'error'

export type TurnRuntimeStatus =
  | 'idle'
  | 'inProgress'
  | 'waitingUserInput'
  | 'completed'
  | 'failed'
  | 'interrupted'

export type TurnCodexStatus = 'inProgress' | 'completed' | 'failed' | 'interrupted'

export type ItemKind =
  | 'userMessage'
  | 'agentMessage'
  | 'reasoning'
  | 'plan'
  | 'commandExecution'
  | 'fileChange'
  | 'userInput'
  | 'error'

export type ItemStatus = 'inProgress' | 'completed' | 'failed'

export type PendingRequestStatus = 'pending' | 'submitted' | 'resolved' | 'rejected' | 'expired'

export type EventTier = 'tier0' | 'tier1' | 'tier2'
export type EventSource = 'journal' | 'replay'

export type SessionErrorCode =
  | 'ERR_SESSION_NOT_INITIALIZED'
  | 'ERR_CURSOR_INVALID'
  | 'ERR_CURSOR_EXPIRED'
  | 'ERR_TURN_TERMINAL'
  | 'ERR_TURN_NOT_STEERABLE'
  | 'ERR_ACTIVE_TURN_MISMATCH'
  | 'ERR_REQUEST_STALE'
  | 'ERR_IDEMPOTENCY_PAYLOAD_MISMATCH'
  | 'ERR_PROVIDER_UNAVAILABLE'
  | 'ERR_SANDBOX_FAILURE'
  | 'ERR_INTERNAL'

export interface SessionError {
  code: SessionErrorCode
  message: string
  details?: Record<string, unknown>
}

export interface ConnectionState {
  phase: ConnectionPhase
  clientName?: string | null
  serverVersion?: string | null
  error?: SessionError | null
}

export type ThreadStatus =
  | { type: 'notLoaded' }
  | { type: 'idle' }
  | { type: 'systemError' }
  | { type: 'active'; activeFlags: string[] }

export interface SessionItem {
  id: string
  threadId: string
  turnId: string | null
  kind: ItemKind
  status: ItemStatus
  createdAtMs: number
  updatedAtMs: number
  payload: Record<string, unknown>
}

export interface SessionTurn {
  id: string
  threadId: string
  status: TurnRuntimeStatus
  lastCodexStatus?: TurnCodexStatus | null
  startedAtMs: number
  completedAtMs: number | null
  items: SessionItem[]
  error: SessionError | null
}

export interface SessionThread {
  id: string
  name: string | null
  preview?: string | null
  model?: string | null
  modelProvider: string
  cwd: string
  path?: string | null
  ephemeral: boolean
  archived: boolean
  status: ThreadStatus
  createdAt: number
  updatedAt: number
  metadata?: Record<string, unknown>
  turns: SessionTurn[]
}

export type ServerRequestMethod =
  | 'item/tool/requestUserInput'
  | 'item/commandExecution/requestApproval'
  | 'item/fileChange/requestApproval'
  | 'item/permissions/requestApproval'
  | 'mcpServer/elicitation/request'

export interface PendingServerRequest {
  requestId: string
  method: ServerRequestMethod
  threadId: string
  turnId: string | null
  itemId: string | null
  status: PendingRequestStatus
  createdAtMs: number
  submittedAtMs: number | null
  resolvedAtMs: number | null
  payload: Record<string, unknown>
}

export type SessionNotificationMethod =
  | 'error'
  | 'thread/started'
  | 'thread/status/changed'
  | 'thread/closed'
  | 'thread/archived'
  | 'thread/unarchived'
  | 'thread/name/updated'
  | 'thread/tokenUsage/updated'
  | 'turn/started'
  | 'turn/completed'
  | 'item/started'
  | 'item/completed'
  | 'item/agentMessage/delta'
  | 'item/plan/delta'
  | 'item/reasoning/summaryTextDelta'
  | 'item/reasoning/summaryPartAdded'
  | 'item/reasoning/textDelta'
  | 'item/commandExecution/outputDelta'
  | 'item/fileChange/outputDelta'
  | 'serverRequest/resolved'

export interface SessionEventEnvelope {
  schemaVersion: number
  eventId: string
  eventSeq: number
  tier: EventTier
  method: SessionNotificationMethod
  threadId: string
  turnId: string | null
  occurredAtMs: number
  replayable: boolean
  snapshotVersion: number | null
  source: EventSource
  params: Record<string, unknown>
}

export interface ServerRequestEnvelope {
  schemaVersion: number
  requestId: string
  method: ServerRequestMethod
  threadId: string
  turnId: string | null
  itemId: string | null
  status: 'pending' | 'resolved' | 'rejected' | 'expired'
  occurredAtMs: number
  params: Record<string, unknown>
}

export interface TurnStartRequestV4 {
  clientActionId: string
  input: Array<Record<string, unknown>>
  model?: string | null
  cwd?: string | null
  approvalPolicy?: string | Record<string, unknown>
  approvalsReviewer?: string | null
  sandboxPolicy?: string | Record<string, unknown>
  personality?: string | null
  effort?: string | null
  summary?: string | Record<string, unknown>
  serviceTier?: string | null
  outputSchema?: Record<string, unknown> | null
}

export type ThreadCreationPolicy = Partial<{
  model: string | null
  modelProvider: string | null
  cwd: string | null
  approvalPolicy: string | Record<string, unknown>
  approvalsReviewer: string | null
  personality: string | null
  sandbox: string | Record<string, unknown>
  serviceTier: string | null
  baseInstructions: string | null
  developerInstructions: string | null
  config: Record<string, unknown> | null
  ephemeral: boolean | null
}>

export type TurnExecutionPolicy = Omit<TurnStartRequestV4, 'clientActionId' | 'input'>

export interface TurnSteerRequestV4 {
  clientActionId: string
  expectedTurnId: string
  input: Array<Record<string, unknown>>
}

export interface TurnInterruptRequestV4 {
  clientActionId: string
}

export interface ResolveRequestV4 {
  resolutionKey: string
  result: Record<string, unknown>
}

export interface RejectRequestV4 {
  resolutionKey: string
  reason?: string | null
}
