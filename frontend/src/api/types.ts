export type NodeStatus = 'locked' | 'draft' | 'ready' | 'in_progress' | 'done'
export type NodeKind = 'root' | 'original' | 'superseded'
export type SplitMode =
  | 'workflow'
  | 'simplify_workflow'
  | 'phase_breakdown'
  | 'agent_breakdown'
export type SplitJobStatus = 'idle' | 'active' | 'failed'
export type NodeDocumentKind = 'frame' | 'spec'

export interface BootstrapStatus {
  ready: boolean
  workspace_configured: boolean
  codex_available: boolean
  codex_path: string | null
}

export interface CodexAccount {
  type: 'chatgpt' | 'apikey' | 'unknown'
  email: string | null
  plan_type: string | null
  requires_openai_auth: boolean | null
}

export interface CodexRateLimitWindow {
  used_percent: number
  window_duration_mins: number | null
  resets_at: number | null
}

export interface CodexCredits {
  has_credits: boolean
  unlimited: boolean
  balance: string | null
}

export interface CodexRateLimits {
  primary: CodexRateLimitWindow | null
  secondary: CodexRateLimitWindow | null
  credits: CodexCredits | null
  plan_type: string | null
}

export interface CodexSnapshot {
  account: CodexAccount | null
  rate_limits: CodexRateLimits | null
}

export interface ProjectSummary {
  id: string
  name: string
  root_goal: string
  project_path: string
  created_at: string
  updated_at: string
}

export interface NodeRecord {
  node_id: string
  parent_id: string | null
  child_ids: string[]
  title: string
  description: string
  status: NodeStatus
  node_kind: NodeKind
  depth: number
  display_order: number
  hierarchical_number: string
  created_at: string
  is_superseded: boolean
}

export interface ProjectRecord {
  id: string
  name: string
  root_goal: string
  project_path: string
  created_at: string
  updated_at: string
}

export interface TreeState {
  root_node_id: string
  active_node_id: string | null
  node_registry: NodeRecord[]
}

export interface Snapshot {
  schema_version: number
  project: ProjectRecord
  tree_state: TreeState
  updated_at: string
}

export interface NodeDraft {
  title?: string
  description?: string
}

export interface NodeDocument {
  node_id: string
  kind: NodeDocumentKind
  content: string
  updated_at: string | null
}

export interface DetailState {
  node_id: string
  frame_confirmed: boolean
  frame_confirmed_revision: number
  frame_revision: number
  clarify_unlocked: boolean
  clarify_stale: boolean
  clarify_confirmed: boolean
  spec_unlocked: boolean
  spec_stale: boolean
  spec_confirmed: boolean
}

export type ClarifyResolutionStatus = 'open' | 'answered' | 'assumed' | 'deferred'

export interface ClarifyQuestion {
  field_name: string
  question: string
  answer: string
  resolution_status: ClarifyResolutionStatus
}

export interface ClarifyState {
  schema_version: number
  source_frame_revision: number
  confirmed_at: string | null
  questions: ClarifyQuestion[]
  updated_at: string | null
}

export type GenJobStatus = 'idle' | 'active' | 'failed'
export type FrameGenJobStatus = GenJobStatus

export interface FrameGenAcceptedResponse {
  status: 'accepted'
  job_id: string
  node_id: string
}

export interface FrameGenStatusResponse {
  status: FrameGenJobStatus
  job_id: string | null
  started_at: string | null
  completed_at: string | null
  error: string | null
}

export interface ClarifyGenAcceptedResponse {
  status: 'accepted'
  job_id: string
  node_id: string
}

export interface ClarifyGenStatusResponse {
  status: GenJobStatus
  job_id: string | null
  started_at: string | null
  completed_at: string | null
  error: string | null
}

export interface SplitAcceptedResponse {
  status: 'accepted'
  job_id: string
  node_id: string
  mode: SplitMode
}

export interface SplitStatusResponse {
  status: SplitJobStatus
  job_id: string | null
  node_id: string | null
  mode: SplitMode | null
  started_at: string | null
  completed_at: string | null
  error: string | null
}

// ── Chat types ──────────────────────────────────────────────────────

export type MessageStatus = 'pending' | 'streaming' | 'completed' | 'error'
export type MessageRole = 'user' | 'assistant'

export type MessagePart =
  | { type: 'assistant_text'; content: string; is_streaming: boolean }
  | {
      type: 'tool_call'
      tool_name: string
      arguments: Record<string, unknown>
      call_id: string | null
      status: 'running' | 'completed' | 'error'
    }
  | { type: 'status_block'; status_type: string; label: string; timestamp: string }

export interface ChatMessage {
  message_id: string
  role: MessageRole
  content: string
  parts?: MessagePart[]
  status: MessageStatus
  error: string | null
  turn_id: string | null
  created_at: string
  updated_at: string
}

export interface ChatSession {
  thread_id: string | null
  active_turn_id: string | null
  messages: ChatMessage[]
  created_at: string
  updated_at: string
}

export interface SendMessageResponse {
  user_message: ChatMessage
  assistant_message: ChatMessage
  active_turn_id: string
}
