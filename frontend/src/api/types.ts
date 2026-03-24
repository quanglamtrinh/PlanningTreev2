export type NodeStatus = 'locked' | 'draft' | 'ready' | 'in_progress' | 'done'
export type NodeKind = 'root' | 'original' | 'superseded' | 'review'
export type WorkflowStep = 'frame' | 'clarify' | 'spec'
export type ThreadRole = 'audit' | 'ask_planning' | 'execution' | 'integration'
export type ExecutionStatus = 'idle' | 'executing' | 'completed' | 'review_pending' | 'review_accepted'
export type RollupStatus = 'pending' | 'ready' | 'accepted'
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
  /** When false, project folder has no Git repo (sidebar may show Initialize Git). */
  git_initialized?: boolean
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
  workflow: NodeWorkflowSummary | null
  review_node_id?: string | null
}

export interface NodeWorkflowSummary {
  frame_confirmed: boolean
  active_step: WorkflowStep
  spec_confirmed: boolean
  execution_started?: boolean
  execution_completed?: boolean
  shaping_frozen?: boolean
  can_finish_task?: boolean
  execution_status?: ExecutionStatus | null
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

export type ChangedFileStatus = 'A' | 'M' | 'D' | 'R'

export interface ChangedFileRecord {
  path: string
  status: ChangedFileStatus
  previous_path?: string | null
}

export interface DetailState {
  node_id: string
  frame_confirmed: boolean
  frame_confirmed_revision: number
  frame_revision: number
  active_step: WorkflowStep
  workflow_notice: string | null
  generation_error?: string | null
  frame_needs_reconfirm: boolean
  frame_read_only: boolean
  clarify_read_only: boolean
  clarify_confirmed: boolean
  spec_read_only: boolean
  spec_stale: boolean
  spec_confirmed: boolean
  execution_started?: boolean
  execution_completed?: boolean
  shaping_frozen?: boolean
  can_finish_task?: boolean
  execution_status?: ExecutionStatus | null
  audit_writable?: boolean
  package_audit_ready?: boolean
  review_status?: RollupStatus | null
  /** Workspace state at execution start (from execution state file, if any). */
  initial_sha?: string | null
  /** Workspace state after execution completes (from execution state file, if any). */
  head_sha?: string | null
  /** Deterministic commit message for this task execution (when committed). */
  commit_message?: string | null
  /** Current repo HEAD (may differ from head_sha after user moves workspace). */
  current_head_sha?: string | null
  /** False if task SHAs are no longer on the ancestry path of current HEAD. */
  task_present_in_current_workspace?: boolean | null
  /** When false, execution/finish should be blocked; see git_blocker_message. */
  git_ready?: boolean | null
  git_blocker_message?: string | null
  /** Paths changed for this task (from git or execution metadata). */
  changed_files?: ChangedFileRecord[] | string[]
}

export interface ClarifyOption {
  id: string
  label: string
  value: string
  rationale: string
  recommended: boolean
}

export interface ClarifyQuestion {
  field_name: string
  question: string
  why_it_matters: string
  current_value: string
  options: ClarifyOption[]
  selected_option_id: string | null
  custom_answer: string
  allow_custom: boolean
}

export interface ClarifyState {
  schema_version: number
  source_frame_revision: number
  confirmed_revision: number
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

export type SpecGenJobStatus = GenJobStatus

export interface SpecGenAcceptedResponse {
  status: 'accepted'
  job_id: string
  node_id: string
}

export interface SpecGenStatusResponse {
  status: SpecGenJobStatus
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
  thread_role: ThreadRole
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

// ── Execution state types ────────────────────────────────────────

export interface ExecutionState {
  status: ExecutionStatus
  initial_sha: string | null
  head_sha: string | null
  started_at: string | null
  completed_at: string | null
}

// ── Review and checkpoint types ──────────────────────────────────

export interface CheckpointRecord {
  label: string
  sha: string
  summary: string | null
  source_node_id: string | null
  accepted_at: string
}

export interface RollupState {
  status: RollupStatus
  summary: string | null
  sha: string | null
  accepted_at: string | null
}

export interface PendingSibling {
  index: number
  title: string
  objective: string
  materialized_node_id: string | null
}

export interface ReviewState {
  checkpoints: CheckpointRecord[]
  rollup: RollupState
  pending_siblings: PendingSibling[]
}
