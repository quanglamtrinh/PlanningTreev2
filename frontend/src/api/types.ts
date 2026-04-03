export type NodeStatus = 'locked' | 'draft' | 'ready' | 'in_progress' | 'done'
export type NodeKind = 'root' | 'original' | 'superseded' | 'review'
export type WorkflowStep = 'frame' | 'clarify' | 'spec'
export type ThreadRole = 'audit' | 'ask_planning' | 'execution'
export type WorkflowPhase =
  | 'idle'
  | 'execution_running'
  | 'execution_decision_pending'
  | 'audit_running'
  | 'audit_decision_pending'
  | 'done'
  | 'failed'
export type ExecutionStatus = 'idle' | 'executing' | 'completed' | 'failed' | 'review_pending' | 'review_accepted'
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
  execution_audit_v2_enabled?: boolean
  execution_audit_uiux_v3_backend_enabled?: boolean
  execution_audit_uiux_v3_frontend_enabled?: boolean
  execution_uiux_v3_frontend_enabled?: boolean
  audit_uiux_v3_frontend_enabled?: boolean
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

export interface ReviewSiblingEntry {
  index: number
  title: string
  materialized_node_id: string | null
}

export interface ReviewSiblingManifestEntry {
  index: number
  title: string
  objective: string | null
  materialized_node_id: string | null
  status: 'completed' | 'active' | 'pending'
  checkpoint_label: string | null
}

export interface ReviewSummary {
  checkpoint_count: number
  rollup_status: RollupStatus | null
  pending_sibling_count: number
  pending_siblings?: ReviewSiblingEntry[]
  sibling_manifest: ReviewSiblingManifestEntry[]
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
  review_summary?: ReviewSummary | null
}

export interface NodeWorkflowSummary {
  frame_confirmed: boolean
  active_step: WorkflowStep
  spec_confirmed: boolean
  execution_started?: boolean
  execution_completed?: boolean
  shaping_frozen?: boolean
  can_finish_task?: boolean
  can_accept_local_review?: boolean
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
  workflow: NodeWorkflowSummary | null
  frame_confirmed: boolean
  frame_confirmed_revision: number
  frame_revision: number
  active_step: WorkflowStep
  workflow_notice: string | null
  generation_error?: string | null
  frame_branch_ready?: boolean
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
  can_accept_local_review?: boolean
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
  /** Automated local review status after execution completes. */
  auto_review_status?: 'running' | 'completed' | 'failed' | null
  auto_review_summary?: string | null
  auto_review_overall_severity?: 'critical' | 'high' | 'medium' | 'low' | 'info' | null
  auto_review_overall_score?: number | null
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
export type MessageRole = 'user' | 'assistant' | 'system'

export type MessagePart =
  | { type: 'assistant_text'; content: string; is_streaming: boolean }
  | {
      type: 'plan_item'
      item_id: string
      content: string
      is_streaming: boolean
      timestamp: string
    }
  | {
      type: 'tool_call'
      tool_name: string
      arguments: Record<string, unknown>
      call_id: string | null
      status: 'running' | 'completed' | 'error'
      output?: string | null
      exit_code?: number | null
    }
  | { type: 'status_block'; status_type: string; label: string; timestamp: string }

export type ItemLifecyclePhase = 'started' | 'delta' | 'completed' | 'error'

export interface ItemLifecycleEntry {
  phase: ItemLifecyclePhase
  timestamp: string
  payload?: Record<string, unknown> | null
  text?: string | null
}

export interface MessageItem {
  item_id: string
  item_type: string
  status: 'started' | 'streaming' | 'completed' | 'error'
  started_at: string
  completed_at: string | null
  last_payload?: Record<string, unknown> | null
  lifecycle: ItemLifecycleEntry[]
}

export interface ChatMessage {
  message_id: string
  role: MessageRole
  content: string
  parts?: MessagePart[]
  items?: MessageItem[]
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
  forked_from_thread_id?: string | null
  forked_from_node_id?: string | null
  forked_from_role?: string | null
  fork_reason?: string | null
  lineage_root_thread_id?: string | null
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
  draft: RollupDraft
}

export interface RollupDraft {
  summary: string | null
  sha: string | null
  generated_at: string | null
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
  sibling_manifest: ReviewSiblingManifestEntry[]
}

export interface AcceptLocalReviewResponse {
  node_id: string
  status: 'review_accepted'
  activated_sibling_id: string | null
}

export interface AcceptRollupReviewResponse {
  review_node_id: string
  rollup_status: 'accepted'
  summary: string
  sha: string
}

// Conversation V2 types

export type ProcessingState = 'idle' | 'running' | 'waiting_user_input' | 'failed'
export type ItemStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'requested'
  | 'answer_submitted'
  | 'answered'
  | 'stale'
export type ItemSource = 'upstream' | 'backend' | 'local'
export type ItemTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'muted'
export type ConversationItemKind =
  | 'message'
  | 'reasoning'
  | 'plan'
  | 'tool'
  | 'userInput'
  | 'status'
  | 'error'

export interface ItemBase {
  id: string
  kind: ConversationItemKind
  threadId: string
  turnId: string | null
  sequence: number
  createdAt: string
  updatedAt: string
  status: ItemStatus
  source: ItemSource
  tone: ItemTone
  metadata: Record<string, unknown>
}

export interface ConversationMessageItem extends ItemBase {
  kind: 'message'
  role: 'user' | 'assistant' | 'system'
  text: string
  format: 'markdown'
}

export interface ReasoningItem extends ItemBase {
  kind: 'reasoning'
  summaryText: string
  detailText: string | null
}

export interface PlanStep {
  id: string
  text: string
  status: 'pending' | 'in_progress' | 'completed'
}

export interface PlanItem extends ItemBase {
  kind: 'plan'
  title: string | null
  text: string
  steps: PlanStep[]
}

export interface ToolOutputFile {
  path: string
  changeType: 'created' | 'updated' | 'deleted'
  summary: string | null
}

export interface ToolItem extends ItemBase {
  kind: 'tool'
  toolType: 'commandExecution' | 'fileChange' | 'generic'
  title: string
  toolName: string | null
  callId: string | null
  argumentsText: string | null
  outputText: string
  outputFiles: ToolOutputFile[]
  exitCode: number | null
}

export interface UserInputAnswer {
  questionId: string
  value: string
  label: string | null
}

export interface UserInputQuestionOption {
  label: string
  description: string | null
}

export interface UserInputQuestion {
  id: string
  header: string | null
  prompt: string
  inputType: 'single_select' | 'multi_select' | 'text'
  options: UserInputQuestionOption[]
}

export interface UserInputItem extends ItemBase {
  kind: 'userInput'
  requestId: string
  title: string | null
  questions: UserInputQuestion[]
  answers: UserInputAnswer[]
  requestedAt: string
  resolvedAt: string | null
}

export interface StatusItem extends ItemBase {
  kind: 'status'
  code: string
  label: string
  detail: string | null
}

export interface ErrorItem extends ItemBase {
  kind: 'error'
  code: string
  title: string
  message: string
  recoverable: boolean
  relatedItemId: string | null
}

export type ConversationItem =
  | ConversationMessageItem
  | ReasoningItem
  | PlanItem
  | ToolItem
  | UserInputItem
  | StatusItem
  | ErrorItem

export interface PendingUserInputRequest {
  requestId: string
  itemId: string
  threadId: string
  turnId: string | null
  status: 'requested' | 'answer_submitted' | 'answered' | 'stale'
  createdAt: string
  submittedAt: string | null
  resolvedAt: string | null
  answers: UserInputAnswer[]
}

export interface ThreadLineageV2 {
  forkedFromThreadId: string | null
  forkedFromNodeId: string | null
  forkedFromRole: ThreadRole | null
  forkReason: string | null
  lineageRootThreadId: string | null
}

export interface ThreadSnapshotV2 {
  projectId: string
  nodeId: string
  threadRole: ThreadRole
  threadId: string | null
  activeTurnId: string | null
  processingState: ProcessingState
  snapshotVersion: number
  createdAt: string
  updatedAt: string
  lineage: ThreadLineageV2
  items: ConversationItem[]
  pendingRequests: PendingUserInputRequest[]
}

export interface MessagePatch {
  kind: 'message'
  textAppend?: string
  status?: ItemStatus
  updatedAt: string
}

export interface ReasoningPatch {
  kind: 'reasoning'
  summaryTextAppend?: string
  detailTextAppend?: string
  status?: ItemStatus
  updatedAt: string
}

export interface PlanPatch {
  kind: 'plan'
  textAppend?: string
  stepsReplace?: PlanStep[]
  status?: ItemStatus
  updatedAt: string
}

export interface ToolPatch {
  kind: 'tool'
  title?: string
  argumentsText?: string | null
  outputTextAppend?: string
  outputFilesAppend?: ToolOutputFile[]
  outputFilesReplace?: ToolOutputFile[]
  exitCode?: number | null
  status?: ItemStatus
  updatedAt: string
}

export interface UserInputPatch {
  kind: 'userInput'
  answersReplace?: UserInputAnswer[]
  resolvedAt?: string | null
  status?: Extract<ItemStatus, 'requested' | 'answer_submitted' | 'answered' | 'stale'>
  updatedAt: string
}

export interface StatusPatch {
  kind: 'status'
  label?: string
  detail?: string | null
  status?: ItemStatus
  updatedAt: string
}

export interface ErrorPatch {
  kind: 'error'
  message?: string
  relatedItemId?: string | null
  status?: ItemStatus
  updatedAt: string
}

export type ItemPatch =
  | MessagePatch
  | ReasoningPatch
  | PlanPatch
  | ToolPatch
  | UserInputPatch
  | StatusPatch
  | ErrorPatch

export type ThreadLifecycleState = 'turn_started' | 'waiting_user_input' | 'turn_completed' | 'turn_failed'

export interface ThreadEventEnvelopeBaseV2 {
  eventId: string
  channel: 'thread'
  projectId: string
  nodeId: string
  threadRole: ThreadRole
  occurredAt: string
  snapshotVersion: number | null
}

export interface ThreadSnapshotEventV2 extends ThreadEventEnvelopeBaseV2 {
  type: 'thread.snapshot'
  payload: {
    snapshot: ThreadSnapshotV2
  }
}

export interface ConversationItemUpsertEventV2 extends ThreadEventEnvelopeBaseV2 {
  type: 'conversation.item.upsert'
  payload: {
    item: ConversationItem
  }
}

export interface ConversationItemPatchEventV2 extends ThreadEventEnvelopeBaseV2 {
  type: 'conversation.item.patch'
  payload: {
    itemId: string
    patch: ItemPatch
  }
}

export interface ThreadLifecycleEventV2 extends ThreadEventEnvelopeBaseV2 {
  type: 'thread.lifecycle'
  payload: {
    activeTurnId: string | null
    processingState: ProcessingState
    state: ThreadLifecycleState
    detail: string | null
  }
}

export interface ConversationUserInputRequestedEventV2 extends ThreadEventEnvelopeBaseV2 {
  type: 'conversation.request.user_input.requested'
  payload: {
    requestId: string
    itemId: string
    item: UserInputItem
    pendingRequest: PendingUserInputRequest
  }
}

export interface ConversationUserInputResolvedEventV2 extends ThreadEventEnvelopeBaseV2 {
  type: 'conversation.request.user_input.resolved'
  payload: {
    requestId: string
    itemId: string
    status: Extract<ItemStatus, 'answer_submitted' | 'answered' | 'stale'>
    answers: UserInputAnswer[]
    resolvedAt: string | null
  }
}

export interface ThreadResetEventV2 extends ThreadEventEnvelopeBaseV2 {
  type: 'thread.reset'
  payload: {
    threadId: string | null
  }
}

export interface ThreadErrorEventV2 extends ThreadEventEnvelopeBaseV2 {
  type: 'thread.error'
  payload: {
    errorItem: ErrorItem
  }
}

export type ThreadEventV2 =
  | ThreadSnapshotEventV2
  | ConversationItemUpsertEventV2
  | ConversationItemPatchEventV2
  | ThreadLifecycleEventV2
  | ConversationUserInputRequestedEventV2
  | ConversationUserInputResolvedEventV2
  | ThreadResetEventV2
  | ThreadErrorEventV2

// Conversation V3 types (execution/audit only)

export type ThreadLaneV3 = 'execution' | 'audit'
export type ConversationItemKindV3 =
  | 'message'
  | 'reasoning'
  | 'tool'
  | 'explore'
  | 'userInput'
  | 'review'
  | 'diff'
  | 'status'
  | 'error'

export interface ItemBaseV3 {
  id: string
  kind: ConversationItemKindV3
  threadId: string
  turnId: string | null
  sequence: number
  createdAt: string
  updatedAt: string
  status: ItemStatus
  source: ItemSource
  tone: ItemTone
  metadata: Record<string, unknown>
}

export interface ConversationMessageItemV3 extends ItemBaseV3 {
  kind: 'message'
  role: 'user' | 'assistant' | 'system'
  text: string
  format: 'markdown'
}

export interface ReasoningItemV3 extends ItemBaseV3 {
  kind: 'reasoning'
  summaryText: string
  detailText: string | null
}

export interface ToolOutputFileV3 {
  path: string
  changeType: 'created' | 'updated' | 'deleted'
  summary: string | null
}

export interface ToolItemV3 extends ItemBaseV3 {
  kind: 'tool'
  toolType: 'commandExecution' | 'fileChange' | 'generic'
  title: string
  toolName: string | null
  callId: string | null
  argumentsText: string | null
  outputText: string
  outputFiles: ToolOutputFileV3[]
  exitCode: number | null
}

export interface ExploreItemV3 extends ItemBaseV3 {
  kind: 'explore'
  title: string | null
  text: string
}

export interface UserInputAnswerV3 {
  questionId: string
  value: string
  label: string | null
}

export interface UserInputQuestionOptionV3 {
  label: string
  description: string | null
}

export interface UserInputQuestionV3 {
  id: string
  header: string | null
  prompt: string
  inputType: 'single_select' | 'multi_select' | 'text'
  options: UserInputQuestionOptionV3[]
}

export interface UserInputItemV3 extends ItemBaseV3 {
  kind: 'userInput'
  requestId: string
  title: string | null
  questions: UserInputQuestionV3[]
  answers: UserInputAnswerV3[]
  requestedAt: string
  resolvedAt: string | null
}

export interface ReviewItemV3 extends ItemBaseV3 {
  kind: 'review'
  title: string | null
  text: string
  disposition: 'approved' | 'changes_requested' | 'commented' | null
}

export interface DiffFileV3 {
  path: string
  changeType: 'created' | 'updated' | 'deleted'
  summary: string | null
  patchText: string | null
}

export interface DiffItemV3 extends ItemBaseV3 {
  kind: 'diff'
  title: string | null
  summaryText: string | null
  files: DiffFileV3[]
}

export interface StatusItemV3 extends ItemBaseV3 {
  kind: 'status'
  code: string
  label: string
  detail: string | null
}

export interface ErrorItemV3 extends ItemBaseV3 {
  kind: 'error'
  code: string
  title: string
  message: string
  recoverable: boolean
  relatedItemId: string | null
}

export type ConversationItemV3 =
  | ConversationMessageItemV3
  | ReasoningItemV3
  | ToolItemV3
  | ExploreItemV3
  | UserInputItemV3
  | ReviewItemV3
  | DiffItemV3
  | StatusItemV3
  | ErrorItemV3

export interface PendingUserInputRequestV3 {
  requestId: string
  itemId: string
  threadId: string
  turnId: string | null
  status: 'requested' | 'answer_submitted' | 'answered' | 'stale'
  createdAt: string
  submittedAt: string | null
  resolvedAt: string | null
  answers: UserInputAnswerV3[]
}

export interface PlanReadySignalV3 {
  planItemId: string | null
  revision: number | null
  ready: boolean
  failed: boolean
}

export interface UiSignalsV3 {
  planReady: PlanReadySignalV3
  activeUserInputRequests: PendingUserInputRequestV3[]
}

export interface ThreadSnapshotV3 {
  projectId: string
  nodeId: string
  threadId: string | null
  lane: ThreadLaneV3
  activeTurnId: string | null
  processingState: ProcessingState
  snapshotVersion: number
  createdAt: string
  updatedAt: string
  items: ConversationItemV3[]
  uiSignals: UiSignalsV3
}

export interface MessagePatchV3 {
  kind: 'message'
  textAppend?: string
  status?: ItemStatus
  updatedAt: string
}

export interface ReasoningPatchV3 {
  kind: 'reasoning'
  summaryTextAppend?: string
  detailTextAppend?: string
  status?: ItemStatus
  updatedAt: string
}

export interface ToolPatchV3 {
  kind: 'tool'
  title?: string
  argumentsText?: string | null
  outputTextAppend?: string
  outputFilesAppend?: ToolOutputFileV3[]
  outputFilesReplace?: ToolOutputFileV3[]
  exitCode?: number | null
  status?: ItemStatus
  updatedAt: string
}

export interface ExplorePatchV3 {
  kind: 'explore'
  title?: string | null
  textAppend?: string
  status?: ItemStatus
  updatedAt: string
}

export interface UserInputPatchV3 {
  kind: 'userInput'
  answersReplace?: UserInputAnswerV3[]
  resolvedAt?: string | null
  status?: Extract<ItemStatus, 'requested' | 'answer_submitted' | 'answered' | 'stale'>
  updatedAt: string
}

export interface ReviewPatchV3 {
  kind: 'review'
  title?: string | null
  textAppend?: string
  disposition?: 'approved' | 'changes_requested' | 'commented' | null
  status?: ItemStatus
  updatedAt: string
}

export interface DiffPatchV3 {
  kind: 'diff'
  title?: string | null
  summaryText?: string | null
  filesAppend?: DiffFileV3[]
  filesReplace?: DiffFileV3[]
  status?: ItemStatus
  updatedAt: string
}

export interface StatusPatchV3 {
  kind: 'status'
  label?: string
  detail?: string | null
  status?: ItemStatus
  updatedAt: string
}

export interface ErrorPatchV3 {
  kind: 'error'
  message?: string
  relatedItemId?: string | null
  status?: ItemStatus
  updatedAt: string
}

export type ItemPatchV3 =
  | MessagePatchV3
  | ReasoningPatchV3
  | ToolPatchV3
  | ExplorePatchV3
  | UserInputPatchV3
  | ReviewPatchV3
  | DiffPatchV3
  | StatusPatchV3
  | ErrorPatchV3

export interface ThreadEventEnvelopeBaseV3 {
  eventId: string
  channel: 'thread'
  projectId: string
  nodeId: string
  threadRole: ThreadRole
  occurredAt: string
  snapshotVersion: number | null
}

export interface ThreadSnapshotEventV3 extends ThreadEventEnvelopeBaseV3 {
  type: 'thread.snapshot.v3'
  payload: {
    snapshot: ThreadSnapshotV3
  }
}

export interface ConversationItemUpsertEventV3 extends ThreadEventEnvelopeBaseV3 {
  type: 'conversation.item.upsert.v3'
  payload: {
    item: ConversationItemV3
  }
}

export interface ConversationItemPatchEventV3 extends ThreadEventEnvelopeBaseV3 {
  type: 'conversation.item.patch.v3'
  payload: {
    itemId: string
    patch: ItemPatchV3
  }
}

export interface ThreadLifecycleEventV3 extends ThreadEventEnvelopeBaseV3 {
  type: 'thread.lifecycle.v3'
  payload: {
    activeTurnId: string | null
    processingState: ProcessingState
    state: string | null
    detail: string | null
  }
}

export interface ConversationPlanReadyEventV3 extends ThreadEventEnvelopeBaseV3 {
  type: 'conversation.ui.plan_ready.v3'
  payload: {
    planReady: PlanReadySignalV3
  }
}

export interface ConversationUserInputSignalEventV3 extends ThreadEventEnvelopeBaseV3 {
  type: 'conversation.ui.user_input.v3'
  payload: {
    activeUserInputRequests: PendingUserInputRequestV3[]
  }
}

export interface ThreadErrorEventV3 extends ThreadEventEnvelopeBaseV3 {
  type: 'thread.error.v3'
  payload: {
    errorItem: ErrorItemV3
  }
}

export type ThreadEventV3 =
  | ThreadSnapshotEventV3
  | ConversationItemUpsertEventV3
  | ConversationItemPatchEventV3
  | ThreadLifecycleEventV3
  | ConversationPlanReadyEventV3
  | ConversationUserInputSignalEventV3
  | ThreadErrorEventV3

export type PlanActionV3 = 'implement_plan' | 'send_changes'

export interface ResolveUserInputV3Response {
  requestId: string
  itemId: string
  threadId: string
  turnId: string | null
  status: Extract<ItemStatus, 'answer_submitted'>
  answers: UserInputAnswerV3[]
  submittedAt: string
}

export interface PlanActionV3Response {
  accepted: boolean
  threadId: string | null
  turnId: string
  snapshotVersion?: number
  createdItems?: ConversationItem[]
  executionRunId?: string | null
  workflowPhase?: WorkflowPhase | null
  action: PlanActionV3
  planItemId: string
  revision: number
}

export interface WorkflowEventEnvelopeBaseV2 {
  eventId: string
  channel: 'workflow'
  projectId: string
  nodeId: string
  occurredAt: string
}

export interface WorkflowUpdatedEventV2 extends WorkflowEventEnvelopeBaseV2 {
  type: 'node.workflow.updated'
  payload: {
    projectId: string
    nodeId: string
    executionState?: string | null
    reviewState?: string | null
    workflowPhase?: WorkflowPhase | null
    activeExecutionRunId?: string | null
    activeReviewCycleId?: string | null
    occurredAt?: string
  }
}

export interface NodeDetailInvalidateEventV2 extends WorkflowEventEnvelopeBaseV2 {
  type: 'node.detail.invalidate'
  payload: {
    projectId: string
    nodeId: string
    reason: string
  }
}

export type WorkflowEventV2 = WorkflowUpdatedEventV2 | NodeDetailInvalidateEventV2

export interface StartTurnV2Response {
  accepted: boolean
  threadId: string | null
  turnId: string
  snapshotVersion?: number
  createdItems?: ConversationItem[]
  executionRunId?: string | null
  workflowPhase?: WorkflowPhase | null
}

export interface ResolveUserInputV2Response {
  requestId: string
  itemId: string
  threadId: string
  turnId: string | null
  status: Extract<ItemStatus, 'answer_submitted'>
  answers: UserInputAnswer[]
  submittedAt: string
}

export interface ResetThreadV2Response {
  threadId: string | null
  snapshotVersion: number
}

export interface ExecutionDecisionView {
  status: string
  sourceExecutionRunId: string
  executionTurnId: string
  candidateWorkspaceHash: string
  summaryText: string | null
  createdAt: string
}

export interface AuditDecisionView {
  status: string
  sourceReviewCycleId: string
  reviewCommitSha: string
  finalReviewText: string | null
  reviewDisposition: string | null
  createdAt: string
}

export interface NodeWorkflowView {
  nodeId: string
  workflowPhase: WorkflowPhase
  executionThreadId: string | null
  auditLineageThreadId: string | null
  reviewThreadId: string | null
  activeExecutionRunId: string | null
  latestExecutionRunId: string | null
  activeReviewCycleId: string | null
  latestReviewCycleId: string | null
  currentExecutionDecision: ExecutionDecisionView | null
  currentAuditDecision: AuditDecisionView | null
  acceptedSha: string | null
  runtimeBlock: Record<string, unknown> | null
  canSendExecutionMessage: boolean
  canReviewInAudit: boolean
  canImproveInExecution: boolean
  canMarkDoneFromExecution: boolean
  canMarkDoneFromAudit: boolean
}

export interface WorkflowActionAcceptedResponse {
  accepted: boolean
  threadId?: string | null
  turnId?: string | null
  executionRunId?: string | null
  reviewCycleId?: string | null
  reviewThreadId?: string | null
  workflowPhase?: WorkflowPhase | null
}
