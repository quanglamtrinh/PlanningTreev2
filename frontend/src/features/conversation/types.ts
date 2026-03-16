export type ConversationThreadType = 'ask' | 'planning' | 'execution'
export type ConversationRuntimeMode = 'ask' | 'planning' | 'plan' | 'execute'
export type ConversationStatus =
  | 'idle'
  | 'active'
  | 'completed'
  | 'interrupted'
  | 'cancelled'
  | 'error'
export type ConversationMessageRole = 'system' | 'user' | 'assistant' | 'tool'
export type ConversationMessageStatus =
  | 'pending'
  | 'streaming'
  | 'completed'
  | 'error'
  | 'cancelled'
  | 'interrupted'
  | 'superseded'
export type ConversationMessagePartType =
  | 'user_text'
  | 'assistant_text'
  | 'reasoning'
  | 'tool_call'
  | 'tool_result'
  | 'plan_block'
  | 'plan_step_update'
  | 'approval_request'
  | 'user_input_request'
  | 'user_input_response'
  | 'diff_summary'
  | 'file_change_summary'
  | 'status_block'
export type ConversationEventType =
  | 'message_created'
  | 'assistant_text_delta'
  | 'assistant_text_final'
  | 'reasoning_state'
  | 'tool_call_start'
  | 'tool_call_update'
  | 'tool_call_finish'
  | 'tool_result'
  | 'plan_block'
  | 'plan_step_status_change'
  | 'approval_request'
  | 'request_user_input'
  | 'request_resolved'
  | 'user_input_resolved'
  | 'diff_summary'
  | 'file_change_summary'
  | 'completion_status'
  | 'stream_interrupted'
  | 'stream_cancelled'

export interface ConversationReasoningPayload extends Record<string, unknown> {
  reasoning_id?: string
  summary?: string
  text?: string
  content?: string
  title?: string
}

export interface ConversationToolCallPayload extends Record<string, unknown> {
  part_id?: string
  tool_call_id?: string
  call_id?: string
  tool_name?: string
  name?: string
  arguments?: Record<string, unknown>
}

export interface ConversationToolResultPayload extends Record<string, unknown> {
  part_id?: string
  tool_call_id?: string
  result_for_item_id?: string
  result_for_tool_call_id?: string
  text?: string
  content?: string
  summary?: string
  output?: unknown
  result?: unknown
}

export interface ConversationPlanBlockPayload extends Record<string, unknown> {
  part_id?: string
  plan_id?: string
  title?: string
  summary?: string
  text?: string
  content?: string
  steps?: unknown[]
}

export interface ConversationPlanStepUpdatePayload extends Record<string, unknown> {
  part_id?: string
  step_id?: string
  title?: string
  step_title?: string
  label?: string
  status?: string
  state?: string
  text?: string
  content?: string
  summary?: string
}

export interface ConversationDiffSummaryPayload extends Record<string, unknown> {
  part_id?: string
  summary_id?: string
  diff_id?: string
  title?: string
  summary?: string
  text?: string
  content?: string
  files?: unknown[]
  added?: number
  removed?: number
  changed?: number
}

export type ConversationInteractiveResolutionState =
  | 'pending'
  | 'resolved'
  | 'approved'
  | 'declined'
  | 'stale'
  | 'cancelled'
  | 'error'

export interface ConversationInteractiveOption extends Record<string, unknown> {
  label?: string
  description?: string
}

export interface ConversationInteractiveQuestion extends Record<string, unknown> {
  id?: string
  header?: string
  question?: string
  is_other?: boolean
  is_secret?: boolean
  options?: ConversationInteractiveOption[] | null
}

export interface ConversationInteractiveAnswer extends Record<string, unknown> {
  answers?: string[]
}

export interface ConversationApprovalRequestPayload extends Record<string, unknown> {
  part_id?: string
  request_id?: string
  request_kind?: 'approval'
  title?: string
  summary?: string
  prompt?: string
  details?: string
  decision?: string
  resolution_state?: ConversationInteractiveResolutionState
  thread_id?: string
  turn_id?: string
  item_id?: string
}

export interface ConversationUserInputRequestPayload extends Record<string, unknown> {
  part_id?: string
  request_id?: string
  request_kind?: 'user_input'
  title?: string
  summary?: string
  prompt?: string
  details?: string
  resolution_state?: ConversationInteractiveResolutionState
  thread_id?: string
  turn_id?: string
  item_id?: string
  questions?: ConversationInteractiveQuestion[]
  answer_payload?: { answers?: Record<string, ConversationInteractiveAnswer> } | null
  resolved_at?: string | null
}

export interface ConversationUserInputResponsePayload extends Record<string, unknown> {
  part_id?: string
  request_id?: string
  request_kind?: 'user_input'
  title?: string
  summary?: string
  text?: string
  content?: string
  resolved_at?: string | null
  answers?: Record<string, ConversationInteractiveAnswer>
}

export interface ConversationRequestResolvedPayload extends Record<string, unknown> {
  part_id?: string
  request_id?: string
  request_kind?: 'approval' | 'user_input'
  decision?: string
  resolution_state?: ConversationInteractiveResolutionState
  resolved_at?: string | null
  answer_payload?: { answers?: Record<string, ConversationInteractiveAnswer> } | null
}

export interface ConversationFileChangeSummaryPayload extends Record<string, unknown> {
  part_id?: string
  summary_id?: string
  file_id?: string
  file_path?: string
  path?: string
  filename?: string
  change_type?: string
  status?: string
  summary?: string
  text?: string
  content?: string
}

export interface ConversationScope {
  project_id: string
  node_id: string
  thread_type: ConversationThreadType
}

export interface ConversationLineage {
  parent_message_id?: string | null
  retry_of_message_id?: string | null
  continue_of_message_id?: string | null
  regenerate_of_message_id?: string | null
  superseded_by_message_id?: string | null
}

export interface ConversationMessagePart {
  part_id: string
  part_type: ConversationMessagePartType
  status: ConversationMessageStatus
  order: number
  item_key: string | null
  created_at: string
  updated_at: string
  payload: Record<string, unknown>
}

export interface ConversationMessage {
  message_id: string
  conversation_id: string
  turn_id: string
  role: ConversationMessageRole
  runtime_mode: ConversationRuntimeMode
  status: ConversationMessageStatus
  created_at: string
  updated_at: string
  lineage: ConversationLineage
  usage: Record<string, unknown> | null
  error: string | null
  parts: ConversationMessagePart[]
}

export interface ConversationRecord extends ConversationScope {
  conversation_id: string
  app_server_thread_id: string | null
  current_runtime_mode: ConversationRuntimeMode
  status: ConversationStatus
  active_stream_id: string | null
  event_seq: number
  created_at: string
  updated_at: string
}

export interface ConversationSnapshot {
  record: ConversationRecord
  messages: ConversationMessage[]
}

export interface ConversationEventEnvelope {
  event_type: ConversationEventType
  conversation_id: string
  stream_id: string
  event_seq: number
  created_at: string
  payload: Record<string, unknown>
  turn_id?: string
  message_id?: string
  item_id?: string
}

export function createConversationScopeKey(scope: ConversationScope): string {
  return `${scope.project_id}:${scope.node_id}:${scope.thread_type}`
}
