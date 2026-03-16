import type {
  ConversationEventEnvelope,
  ConversationSnapshot,
} from '../features/conversation/types'

export type NodeStatus = 'locked' | 'draft' | 'ready' | 'in_progress' | 'done'
export type NodePhase =
  | 'planning'
  | 'awaiting_brief'
  | 'spec_review'
  | 'ready_for_execution'
  | 'executing'
  | 'blocked_on_spec_question'
  | 'closed'
export type NodeKind = 'root' | 'original' | 'superseded'
export type ChatMessageStatus = 'pending' | 'streaming' | 'completed' | 'error'
export type SpecGenerationStatus = 'idle' | 'generating' | 'failed'

export interface BootstrapStatus {
  ready: boolean
  workspace_configured: boolean
}

export interface WorkspaceSettings {
  base_workspace_root: string | null
}

export interface ProjectSummary {
  id: string
  name: string
  root_goal: string
  base_workspace_root: string
  project_workspace_root: string
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
  phase: NodePhase
  node_kind: NodeKind
  planning_mode: 'walking_skeleton' | 'slice' | null
  depth: number
  display_order: number
  hierarchical_number: string
  split_metadata: Record<string, unknown> | null
  chat_session_id: string | null
  has_planning_thread: boolean
  has_execution_thread: boolean
  planning_thread_status: 'idle' | 'active' | null
  execution_thread_status: 'idle' | 'active' | null
  has_ask_thread: boolean
  ask_thread_status: 'idle' | 'active' | null
  is_superseded: boolean
  created_at: string
}

export interface ProjectRecord {
  id: string
  name: string
  root_goal: string
  base_workspace_root: string
  project_workspace_root: string
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

export interface NodeTask {
  title: string
  purpose: string
  responsibility: string
}

export interface BriefNodeSnapshot {
  node_summary: string
  why_this_node_exists_now: string
  current_focus: string
}

export interface BriefActiveInheritedContext {
  active_goals_from_parent: string[]
  active_constraints_from_parent: string[]
  active_decisions_in_force: string[]
}

export interface BriefAcceptedUpstreamFacts {
  accepted_outputs: string[]
  available_artifacts: string[]
  confirmed_dependencies: string[]
}

export interface BriefRuntimeState {
  status: string
  completed_so_far: string[]
  current_blockers: string[]
  next_best_action: string
}

export interface BriefPendingEscalations {
  open_risks: string[]
  pending_user_decisions: string[]
  fallback_direction_if_unanswered: string
}

export interface NodeBrief {
  node_snapshot: BriefNodeSnapshot
  active_inherited_context: BriefActiveInheritedContext
  accepted_upstream_facts: BriefAcceptedUpstreamFacts
  runtime_state: BriefRuntimeState
  pending_escalations: BriefPendingEscalations
}

export type NodeBriefing = NodeBrief

export interface SpecMission {
  goal: string
  success_outcome: string
  implementation_level: string
}

export interface SpecScope {
  must_do: string[]
  must_not_do: string[]
  deferred_work: string[]
}

export interface SpecConstraints {
  hard_constraints: string[]
  change_budget: string
  touch_boundaries: string[]
  external_dependencies: string[]
}

export interface SpecAutonomy {
  allowed_decisions: string[]
  requires_confirmation: string[]
  default_policy_when_unclear: string
}

export interface SpecVerification {
  acceptance_checks: string[]
  definition_of_done: string
  evidence_expected: string[]
}

export interface SpecExecutionControls {
  quality_profile: string
  tooling_limits: string[]
  output_expectation: string
  conflict_policy: string
  missing_decision_policy: string
}

export interface SpecAssumptions {
  assumptions_in_force: string[]
}

export interface NodeSpec {
  mission: SpecMission
  scope: SpecScope
  constraints: SpecConstraints
  autonomy: SpecAutonomy
  verification: SpecVerification
  execution_controls: SpecExecutionControls
  assumptions: SpecAssumptions
}

export interface PendingPlanQuestion {
  question_id: string
  title: string
  details: string
  created_at: string
  spec_version: number
  source?: 'plan' | 'execute'
}

export interface RuntimeInputOption {
  label: string
  description: string
}

export interface RuntimeInputQuestion {
  id: string
  header: string
  question: string
  is_other: boolean
  is_secret: boolean
  options: RuntimeInputOption[] | null
}

export interface RuntimeInputAnswer {
  answers: string[]
}

export interface RuntimeInputRequest {
  request_id: string
  thread_id: string
  turn_id: string
  node_id: string
  item_id: string
  questions: RuntimeInputQuestion[]
  created_at: string
  resolved_at: string | null
  status: 'pending' | 'resolved' | 'stale'
  answer_payload: { answers: Record<string, RuntimeInputAnswer> } | null
}

export interface RuntimeThreadStatus {
  type: 'notLoaded' | 'idle' | 'systemError' | 'active'
  activeFlags?: string[]
}

export interface LastAgentFailure {
  operation: 'brief_pipeline' | 'generate_spec' | 'plan' | 'split'
  message: string
  occurred_at: string
}

export interface NodeState {
  phase: NodePhase
  task_confirmed: boolean
  briefing_confirmed: boolean
  brief_generation_status: 'missing' | 'generating' | 'failed' | 'ready'
  brief_version: number
  brief_created_at: string
  brief_created_from_predecessor_node_id: string
  brief_generated_by: string
  brief_source_hash: string
  brief_source_refs: string[]
  brief_late_upstream_policy: string
  spec_initialized: boolean
  spec_generated: boolean
  spec_generation_status: SpecGenerationStatus
  spec_confirmed: boolean
  active_spec_version: number
  spec_status: 'draft' | 'confirmed' | 'needs_reconfirm'
  spec_confirmed_at: string
  initialized_from_brief_version: number
  spec_content_hash: string
  active_plan_version: number
  plan_status:
    | 'none'
    | 'generating'
    | 'questioning'
    | 'waiting_on_input'
    | 'ready'
    | 'abandoned'
    | 'completed'
  bound_plan_spec_version: number
  bound_plan_brief_version: number
  active_plan_input_version: number
  bound_plan_input_version: number
  bound_turn_id: string
  final_plan_item_id: string
  structured_result_hash: string
  resolved_request_ids: string[]
  spec_update_change_summary: string
  spec_update_changed_contract_axes: string[]
  spec_update_recommended_next_step: string
  run_status: 'idle' | 'planning' | 'executing' | 'completed' | 'failed'
  pending_plan_questions: PendingPlanQuestion[]
  planning_thread_id: string
  execution_thread_id: string
  ask_thread_id: string
  planning_thread_forked_from_node: string
  planning_thread_bootstrapped_at: string
  chat_session_id: string
  last_agent_failure: LastAgentFailure | null
}

export interface NodeDocuments {
  task: NodeTask
  brief: NodeBrief
  briefing: NodeBrief
  spec: NodeSpec
  plan?: { content: string }
  state: NodeState
}

export interface ChatMessage {
  message_id: string
  role: 'user' | 'assistant'
  content: string
  status: ChatMessageStatus
  created_at: string
  updated_at: string
  error: string | null
}

export interface ChatConfig {
  access_mode: 'project_write' | 'read_only'
  cwd: string
  writable_roots: string[]
  timeout_sec: number
}

export interface ChatSession {
  project_id: string
  node_id: string
  active_turn_id: string | null
  active_assistant_message_id?: string | null
  event_seq: number
  status?: 'idle' | 'active' | null
  mode?: 'idle' | 'plan' | 'execute'
  config: ChatConfig
  messages: ChatMessage[]
  runtime_thread_status?: RuntimeThreadStatus | null
  runtime_request_registry?: RuntimeInputRequest[]
  pending_input_request?: RuntimeInputRequest | null
}

export type PacketStatus = 'pending' | 'approved' | 'merged' | 'rejected' | 'blocked'

export interface DeltaContextPacket {
  packet_id: string
  node_id: string
  created_at: string
  source_message_ids: string[]
  summary: string
  context_text: string
  status: PacketStatus
  status_reason: string | null
  merged_at: string | null
  merged_planning_turn_id: string | null
  suggested_by: 'agent' | 'user'
}

export interface AskSession {
  project_id: string
  node_id: string
  active_turn_id: string | null
  event_seq: number
  status: 'idle' | 'active' | null
  messages: ChatMessage[]
  delta_context_packets: DeltaContextPacket[]
}

type ChatEventBase = {
  event_seq: number
}

export type ChatEvent =
  | (ChatEventBase & {
      type: 'message_created'
      active_turn_id: string
      user_message: ChatMessage
      assistant_message: ChatMessage
    })
  | (ChatEventBase & {
      type: 'assistant_delta'
      message_id: string
      delta: string
      content: string
      updated_at: string
    })
  | (ChatEventBase & {
      type: 'assistant_completed'
      message_id: string
      content: string
      updated_at: string
    })
  | (ChatEventBase & {
      type: 'assistant_error'
      message_id: string
      content: string
      updated_at: string
      error: string
    })
  | (ChatEventBase & {
      type: 'session_reset'
      session: ChatSession
    })
  | (ChatEventBase & {
      type: 'plan_input_requested'
      request: RuntimeInputRequest
      assistant_message: ChatMessage
      waiting_message_id: string
    })
  | (ChatEventBase & {
      type: 'plan_input_resolved'
      request_id: string
      status: 'resolved' | 'stale'
      resolved_at: string
      user_message: ChatMessage | null
    })
  | (ChatEventBase & {
      type: 'plan_runtime_status_changed'
      thread_status: RuntimeThreadStatus | null
    })

type AskEventBase = {
  event_seq: number
}

export type AskEvent =
  | (AskEventBase & {
      type: 'ask_message_created'
      active_turn_id: string
      user_message: ChatMessage
      assistant_message: ChatMessage
    })
  | (AskEventBase & {
      type: 'ask_assistant_delta'
      message_id: string
      delta: string
      content: string
      updated_at: string
    })
  | (AskEventBase & {
      type: 'ask_assistant_completed'
      message_id: string
      content: string
      updated_at: string
    })
  | (AskEventBase & {
      type: 'ask_assistant_error'
      message_id: string
      content: string
      updated_at: string
      error: string
    })
  | (AskEventBase & {
      type: 'ask_session_reset'
      session: AskSession
    })
  | (AskEventBase & {
      type: 'ask_delta_context_suggested'
      packet: DeltaContextPacket
    })
  | (AskEventBase & {
      type: 'ask_packet_status_changed'
      packet: DeltaContextPacket
    })

export interface PlanningTurn {
  turn_id: string
  role: 'user' | 'assistant' | 'tool_call' | 'context_merge'
  is_inherited: boolean
  origin_node_id: string
  content?: string
  summary?: string
  packet_id?: string
  tool_name?: string
  arguments?: {
    kind?: 'split_result'
    payload?: Record<string, unknown>
  }
  timestamp: string
}

export interface PlanningHistory {
  node_id: string
  turns: PlanningTurn[]
}

type PlanningEventBase = {
  node_id: string
  turn_id: string
}

export type PlanningEvent =
  | (PlanningEventBase & {
      type: 'planning_turn_started'
      mode: 'walking_skeleton' | 'slice'
      timestamp: string
    })
  | (PlanningEventBase & {
      type: 'planning_tool_call'
      tool_name: string
      kind: 'split_result' | null
      payload: Record<string, unknown> | null
    })
  | (PlanningEventBase & {
      type: 'planning_turn_completed'
      created_child_ids: string[]
      fallback_used: boolean
      timestamp: string
    })
  | (PlanningEventBase & {
      type: 'planning_turn_failed'
      message: string
      timestamp: string
    })

type AgentEventBase = {
  event_seq: number
  node_id: string
  operation: 'brief_pipeline' | 'generate_spec' | 'plan' | 'split'
  stage: string
  message: string
  timestamp: string
}

export type AgentEvent =
  | (AgentEventBase & {
      type: 'operation_started'
    })
  | (AgentEventBase & {
      type: 'operation_progress'
    })
  | (AgentEventBase & {
      type: 'operation_completed'
      completed_at?: string
    })
  | (AgentEventBase & {
      type: 'operation_failed'
      failed_at?: string
    })

export interface AgentActivity {
  operation: AgentEvent['operation']
  stage: string
  message: string
  status: AgentEvent['type']
  timestamp: string
}

export interface AcceptedAgentOperation {
  status: 'accepted'
  operation?: AgentEvent['operation'] | 'generate_spec'
  state?: NodeState
  user_message_id?: string
  assistant_message_id?: string
}

export interface SplitAcceptedResponse {
  status: 'accepted'
  node_id: string
  mode: 'walking_skeleton' | 'slice'
  planning_status: 'active'
}

export interface ExecutionConversationResponse {
  conversation: ConversationSnapshot
}

export interface ExecutionConversationSendAcceptedResponse {
  status: 'accepted'
  conversation_id: string
  turn_id: string
  stream_id: string
  user_message_id: string
  assistant_message_id: string
  assistant_text_part_id: string
}

export type ExecutionConversationEvent = ConversationEventEnvelope

export interface AskConversationResponse {
  conversation: ConversationSnapshot
}

export interface AskConversationSendAcceptedResponse {
  status: 'accepted'
  conversation_id: string
  turn_id: string
  stream_id: string
  user_message_id: string
  assistant_message_id: string
  assistant_text_part_id: string
}

export type AskConversationEvent = ConversationEventEnvelope
