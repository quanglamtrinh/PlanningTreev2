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
  | 'user_input_resolved'
  | 'diff_summary'
  | 'file_change_summary'
  | 'completion_status'
  | 'stream_interrupted'
  | 'stream_cancelled'

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
