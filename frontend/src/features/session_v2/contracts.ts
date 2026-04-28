export type ConnectionPhase = 'disconnected' | 'connecting' | 'initialized' | 'error'

export type TurnRuntimeStatus =
  | 'idle'
  | 'inProgress'
  | 'waitingUserInput'
  | 'completed'
  | 'failed'
  | 'interrupted'

export type TurnCodexStatus = 'inProgress' | 'completed' | 'failed' | 'interrupted'

export const ITEM_KINDS = [
  'userMessage',
  'agentMessage',
  'reasoning',
  'plan',
  'commandExecution',
  'fileChange',
  'userInput',
  'error',
] as const

export type ItemKind = typeof ITEM_KINDS[number]

export function isItemKind(value: unknown): value is ItemKind {
  return typeof value === 'string' && (ITEM_KINDS as readonly string[]).includes(value)
}

export type ItemStatus = 'inProgress' | 'completed' | 'failed'

export type SessionItemVisibility = 'user' | 'internal' | 'debug'

export type SessionItemRenderAs = 'chatBubble' | 'workflowContext' | 'frameArtifact' | 'specArtifact' | 'hidden'

export type SessionItemWorkflowKind = 'generate_frame' | 'regenerate_frame' | 'generate_spec' | 'regenerate_spec'

export type PendingRequestStatus = 'pending' | 'submitted' | 'resolved' | 'rejected' | 'expired'

export type EventTier = 'tier0' | 'tier1' | 'tier2'
export type EventSource = 'journal' | 'replay'

export type SessionErrorCode =
  | 'ERR_SESSION_NOT_INITIALIZED'
  | 'ERR_THREAD_NOT_FOUND'
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

export type CodexContentItem =
  | { type: 'text' | 'input_text' | 'output_text'; text: string }
  | { type: 'image'; imageUrl?: string; image_url?: string }
  | { type: 'localImage'; path: string }
  | Record<string, unknown>

export type CodexResponseItem =
  | {
      type: 'message'
      role: string
      content: CodexContentItem[]
      end_turn?: boolean
      phase?: string
      metadata?: Record<string, unknown>
    }
  | {
      type: 'reasoning'
      summary: unknown[]
      content?: unknown[]
      encrypted_content: string | null
    }
  | { type: 'function_call'; name: string; namespace?: string; arguments: string; call_id: string }
  | { type: 'function_call_output'; call_id: string; output: unknown }
  | { type: 'local_shell_call'; call_id: string | null; status: string; action: Record<string, unknown> }
  | { type: 'other' }
  | Record<string, unknown>

export type ThreadItem = CodexResponseItem

export interface SessionItem {
  id: string
  threadId: string
  turnId: string | null
  kind: string
  normalizedKind?: ItemKind | null
  status: ItemStatus
  createdAtMs: number
  updatedAtMs: number
  payload: Record<string, unknown>
  visibility?: SessionItemVisibility
  renderAs?: SessionItemRenderAs
  workflowKind?: SessionItemWorkflowKind
  rawItem?: ThreadItem
  rawParams?: Record<string, unknown>
}

export type VisibleTranscriptItem = SessionItem & {
  visibility: SessionItemVisibility
  renderAs: SessionItemRenderAs
  workflowKind?: SessionItemWorkflowKind
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
  metadata?: Record<string, unknown>
}

export type VisibleTranscriptRow = {
  turn: SessionTurn
  item: VisibleTranscriptItem
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
  inactiveByReconcile?: boolean
  reconciledAtMs?: number
}

export type SessionNotificationMethod =
  | 'error'
  | 'warning'
  | 'user/message'
  | 'user_message'
  | 'assistant/message'
  | 'assistant_message'
  | 'agent/message'
  | 'thread/started'
  | 'thread/status/changed'
  | 'thread/closed'
  | 'thread/archived'
  | 'thread/unarchived'
  | 'thread/name/updated'
  | 'thread/tokenUsage/updated'
  | 'thread/compacted'
  | 'turn/started'
  | 'turn/completed'
  | 'turn/failed'
  | 'turn/diff/updated'
  | 'turn/plan/updated'
  | 'task/started'
  | 'task/completed'
  | 'task/failed'
  | 'item/started'
  | 'item/completed'
  | 'item/autoApprovalReview/started'
  | 'item/autoApprovalReview/completed'
  | 'item/agentMessage/delta'
  | 'item/plan/delta'
  | 'item/mcpToolCall/progress'
  | 'item/reasoning/summaryTextDelta'
  | 'item/reasoning/summaryPartAdded'
  | 'item/reasoning/textDelta'
  | 'item/commandExecution/outputDelta'
  | 'item/commandExecution/terminalInteraction'
  | 'item/fileChange/outputDelta'
  | 'rawResponseItem/completed'
  | 'hook/started'
  | 'hook/completed'
  | 'thread/realtime/started'
  | 'thread/realtime/itemAdded'
  | 'thread/realtime/transcript/delta'
  | 'thread/realtime/transcript/done'
  | 'thread/realtime/outputAudio/delta'
  | 'thread/realtime/sdp'
  | 'thread/realtime/error'
  | 'thread/realtime/closed'
  | 'serverRequest/created'
  | 'serverRequest/updated'
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
  status: PendingRequestStatus
  occurredAtMs: number
  params: Record<string, unknown>
}

export interface McpTurnContextV4 {
  projectId: string
  nodeId: string
  role: string
}

export interface TurnStartRequestV4 {
  input: Array<Record<string, unknown>>
  model?: string | null
  cwd?: string | null
  approvalPolicy?: string | Record<string, unknown> | null
  approvalsReviewer?: string | null
  sandboxPolicy?: string | Record<string, unknown> | null
  personality?: string | null
  effort?: string | null
  summary?: string | Record<string, unknown> | null
  serviceTier?: string | null
  outputSchema?: Record<string, unknown> | null
  mcpContext?: McpTurnContextV4 | null
}

export type ThreadCreationPolicy = Partial<{
  model: string | null
  modelProvider: string | null
  cwd: string | null
  approvalPolicy: string | Record<string, unknown> | null
  approvalsReviewer: string | null
  personality: string | null
  sandbox: string | Record<string, unknown> | null
  serviceTier: string | null
  baseInstructions: string | null
  developerInstructions: string | null
  config: Record<string, unknown> | null
  ephemeral: boolean | null
}>

export type TurnExecutionPolicy = Omit<TurnStartRequestV4, 'input'>

export type SessionInputAction =
  | {
      type: 'turn.start'
      threadId: string
      input: Array<Record<string, unknown>>
      policy?: TurnExecutionPolicy
      context?: { mcpContext?: McpTurnContextV4 | null }
    }
  | {
      type: 'turn.steer'
      threadId: string
      turnId: string
      input: Array<Record<string, unknown>>
    }
  | {
      type: 'turn.interrupt'
      threadId: string
      turnId: string
    }
  | {
      type: 'request.resolve'
      requestId: string
      result: Record<string, unknown>
      resolutionKey: string
    }
  | {
      type: 'request.reject'
      requestId: string
      reason?: string | null
      resolutionKey: string
    }

export type SessionConfig = {
  model?: string | null
  modelProvider?: string | null
  cwd?: string | null
  approvalPolicy?: string | Record<string, unknown> | null
  approvalsReviewer?: string | null
  sandbox?: string | Record<string, unknown> | null
  sandboxPolicy?: string | Record<string, unknown> | null
  reasoning?: {
    effort?: string | null
    summary?: string | Record<string, unknown> | null
  } | null
  personality?: string | null
  serviceTier?: string | null
  outputSchema?: Record<string, unknown> | null
  baseInstructions?: string | null
  developerInstructions?: string | null
  config?: Record<string, unknown> | null
  ephemeral?: boolean | null
}

export function toThreadCreationPolicy(config: SessionConfig): ThreadCreationPolicy {
  return {
    model: config.model,
    modelProvider: config.modelProvider,
    cwd: config.cwd,
    approvalPolicy: config.approvalPolicy,
    approvalsReviewer: config.approvalsReviewer,
    sandbox: config.sandbox,
    personality: config.personality,
    serviceTier: config.serviceTier,
    baseInstructions: config.baseInstructions,
    developerInstructions: config.developerInstructions,
    config: config.config,
    ephemeral: config.ephemeral,
  }
}

export function toTurnExecutionPolicy(config: SessionConfig): TurnExecutionPolicy {
  return {
    model: config.model,
    cwd: config.cwd,
    approvalPolicy: config.approvalPolicy,
    approvalsReviewer: config.approvalsReviewer,
    sandboxPolicy: config.sandboxPolicy,
    personality: config.personality,
    effort: config.reasoning?.effort ?? null,
    summary: config.reasoning?.summary ?? null,
    serviceTier: config.serviceTier,
    outputSchema: config.outputSchema,
  }
}

export interface TurnSteerRequestV4 {
  expectedTurnId: string
  input: Array<Record<string, unknown>>
}

export type TurnInterruptRequestV4 = Record<string, never>

export interface ResolveRequestV4 {
  resolutionKey: string
  result: Record<string, unknown>
}

export interface RejectRequestV4 {
  resolutionKey: string
  reason?: string | null
}
