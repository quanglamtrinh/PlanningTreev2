import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    planningEventsUrl: vi.fn(),
    getPlanningConversation: vi.fn(),
    planningConversationEventsUrl: vi.fn(),
    agentEventsUrl: vi.fn(),
    chatEventsUrl: vi.fn(),
    askEventsUrl: vi.fn(),
    getAskConversation: vi.fn(),
    sendAskConversationMessage: vi.fn(),
    askConversationEventsUrl: vi.fn(),
    getExecutionConversation: vi.fn(),
    sendExecutionConversationMessage: vi.fn(),
    resolveExecutionConversationRequest: vi.fn(),
    resolvePlanningConversationRequest: vi.fn(),
    executionConversationEventsUrl: vi.fn(),
    getNodeDocuments: vi.fn(),
    startPlan: vi.fn(),
    executeNode: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => {
  class ApiError extends Error {
    status: number
    code: string | null

    constructor(status = 400, payload: { message?: string; code?: string } | null = null) {
      super(payload?.message ?? 'Request failed')
      this.status = status
      this.code = payload?.code ?? null
    }
  }

  return {
    api: apiMock,
    ApiError,
  }
})

import { BreadcrumbWorkspace } from '../../src/features/breadcrumb/BreadcrumbWorkspace'
import { useAskStore } from '../../src/stores/ask-store'
import { useChatStore } from '../../src/stores/chat-store'
import { useConversationStore } from '../../src/stores/conversation-store'
import { useProjectStore } from '../../src/stores/project-store'
import { useUIStore } from '../../src/stores/ui-store'

function makeNodeDocuments() {
  return {
    task: { title: 'Alpha', purpose: 'Ship phase 3', responsibility: '' },
    brief: {
      node_snapshot: {
        node_summary: 'Alpha',
        why_this_node_exists_now: 'Ship phase 3',
        current_focus: '',
      },
      active_inherited_context: {
        active_goals_from_parent: [],
        active_constraints_from_parent: [],
        active_decisions_in_force: [],
      },
      accepted_upstream_facts: {
        accepted_outputs: [],
        available_artifacts: [],
        confirmed_dependencies: [],
      },
      runtime_state: {
        status: 'ready',
        completed_so_far: [],
        current_blockers: [],
        next_best_action: 'Draft spec',
      },
      pending_escalations: {
        open_risks: [],
        pending_user_decisions: [],
        fallback_direction_if_unanswered: '',
      },
    },
    briefing: {
      node_snapshot: {
        node_summary: 'Alpha',
        why_this_node_exists_now: 'Ship phase 3',
        current_focus: '',
      },
      active_inherited_context: {
        active_goals_from_parent: [],
        active_constraints_from_parent: [],
        active_decisions_in_force: [],
      },
      accepted_upstream_facts: {
        accepted_outputs: [],
        available_artifacts: [],
        confirmed_dependencies: [],
      },
      runtime_state: {
        status: 'ready',
        completed_so_far: [],
        current_blockers: [],
        next_best_action: 'Draft spec',
      },
      pending_escalations: {
        open_risks: [],
        pending_user_decisions: [],
        fallback_direction_if_unanswered: '',
      },
    },
    spec: {
      mission: { goal: '', success_outcome: '', implementation_level: '' },
      scope: { must_do: [], must_not_do: [], deferred_work: [] },
      constraints: {
        hard_constraints: [],
        change_budget: '',
        touch_boundaries: [],
        external_dependencies: [],
      },
      autonomy: {
        allowed_decisions: [],
        requires_confirmation: [],
        default_policy_when_unclear: '',
      },
      verification: {
        acceptance_checks: [],
        definition_of_done: '',
        evidence_expected: [],
      },
      execution_controls: {
        quality_profile: '',
        tooling_limits: [],
        output_expectation: '',
        conflict_policy: '',
        missing_decision_policy: '',
      },
      assumptions: { assumptions_in_force: [] },
    },
    state: {
      phase: 'planning' as const,
      task_confirmed: false,
      briefing_confirmed: false,
      brief_generation_status: 'missing' as const,
      brief_version: 0,
      brief_created_at: '',
      brief_created_from_predecessor_node_id: '',
      brief_generated_by: '',
      brief_source_hash: '',
      brief_source_refs: [],
      brief_late_upstream_policy: 'ignore',
      spec_initialized: false,
      spec_generated: false,
      spec_generation_status: 'idle' as const,
      spec_confirmed: false,
      active_spec_version: 0,
      spec_status: 'draft' as const,
      spec_confirmed_at: '',
      initialized_from_brief_version: 0,
      spec_content_hash: '',
      active_plan_version: 0,
      plan_status: 'none' as const,
      bound_plan_spec_version: 0,
      bound_plan_brief_version: 0,
      run_status: 'idle' as const,
      pending_plan_questions: [],
      pending_spec_questions: [],
      planning_thread_id: '',
      execution_thread_id: '',
      ask_thread_id: '',
      planning_thread_forked_from_node: '',
      planning_thread_bootstrapped_at: '',
      chat_session_id: '',
    },
  }
}

const snapshot = {
  schema_version: 2,
  project: {
    id: 'project-1',
    name: 'Alpha',
    root_goal: 'Ship phase 3',
    base_workspace_root: 'C:/workspace',
    project_workspace_root: 'C:/workspace/alpha',
    created_at: '2026-03-07T10:00:00Z',
    updated_at: '2026-03-07T10:00:00Z',
  },
  tree_state: {
    root_node_id: 'root',
    active_node_id: 'root',
    node_registry: [
      {
        node_id: 'root',
        parent_id: null,
        child_ids: [],
        title: 'Alpha',
        description: 'Ship phase 3',
        status: 'draft' as const,
        phase: 'planning' as const,
        planning_mode: null,
        depth: 0,
        display_order: 0,
        hierarchical_number: '1',
        split_metadata: null,
        chat_session_id: null,
        has_planning_thread: true,
        has_execution_thread: false,
        planning_thread_status: 'idle' as const,
        execution_thread_status: null,
        has_ask_thread: false,
        ask_thread_status: null,
        is_superseded: false,
        created_at: '2026-03-07T10:00:00Z',
      },
    ],
  },
  updated_at: '2026-03-07T10:00:00Z',
}

const childSnapshot = {
  ...snapshot,
  tree_state: {
    ...snapshot.tree_state,
    node_registry: [
      ...snapshot.tree_state.node_registry,
      {
        node_id: 'child-1',
        parent_id: 'root',
        child_ids: [],
        title: 'Child Node',
        description: 'Implement the child flow',
        status: 'ready' as const,
        phase: 'ready_for_execution' as const,
        planning_mode: null,
        depth: 1,
        display_order: 0,
        hierarchical_number: '1.1',
        split_metadata: null,
        chat_session_id: null,
        has_planning_thread: true,
        has_execution_thread: false,
        planning_thread_status: 'idle' as const,
        execution_thread_status: null,
        has_ask_thread: false,
        ask_thread_status: null,
        is_superseded: false,
        created_at: '2026-03-07T10:05:00Z',
      },
    ],
  },
}

function makeExecutionConversationSnapshot() {
  return {
    record: {
      conversation_id: 'conv_exec_1',
      project_id: 'project-1',
      node_id: 'child-1',
      thread_type: 'execution' as const,
      app_server_thread_id: null,
      current_runtime_mode: 'execute' as const,
      status: 'idle' as const,
      active_stream_id: null,
      event_seq: 0,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:00Z',
    },
    messages: [],
  }
}

function makeExecutionConversationSnapshotWithMessage(
  text: string,
  overrides: Partial<ReturnType<typeof makeExecutionConversationSnapshot>> = {},
) {
  const snapshot = makeExecutionConversationSnapshot()
  return {
    ...snapshot,
    ...overrides,
    record: {
      ...snapshot.record,
      ...(overrides.record ?? {}),
    },
    messages: [
      {
        message_id: 'conv_msg_1',
        conversation_id: snapshot.record.conversation_id,
        turn_id: 'turn_1',
        role: 'assistant' as const,
        runtime_mode: 'execute' as const,
        status: 'completed' as const,
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:01Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'part_assistant',
            part_type: 'assistant_text' as const,
            status: 'completed' as const,
            order: 0,
            item_key: null,
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
            payload: { text },
          },
        ],
      },
    ],
  }
}

function makeExecutionConversationSnapshotWithUserInputRequest() {
  const snapshot = makeExecutionConversationSnapshot()
  return {
    ...snapshot,
    record: {
      ...snapshot.record,
      node_id: 'child-1',
      status: 'active' as const,
      active_stream_id: 'stream_1',
      event_seq: 5,
    },
    messages: [
      {
        message_id: 'msg_exec_request:req_old',
        conversation_id: snapshot.record.conversation_id,
        turn_id: 'turn_1',
        role: 'assistant' as const,
        runtime_mode: 'execute' as const,
        status: 'pending' as const,
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:01Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'msg_exec_request:req_old:user_input_request',
            part_type: 'user_input_request' as const,
            status: 'pending' as const,
            order: 0,
            item_key: 'req_old',
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
            payload: {
              part_id: 'msg_exec_request:req_old:user_input_request',
              request_id: 'req_old',
              request_kind: 'user_input',
              resolution_state: 'pending',
              title: 'Old request',
              questions: [
                {
                  id: 'deprecated',
                  header: 'Deprecated',
                  question: 'Old question',
                  options: [],
                  is_other: true,
                  is_secret: false,
                },
              ],
            },
          },
        ],
      },
      {
        message_id: 'msg_exec_request:req_latest',
        conversation_id: snapshot.record.conversation_id,
        turn_id: 'turn_1',
        role: 'assistant' as const,
        runtime_mode: 'execute' as const,
        status: 'pending' as const,
        created_at: '2026-03-15T00:00:02Z',
        updated_at: '2026-03-15T00:00:02Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'msg_exec_request:req_latest:user_input_request',
            part_type: 'user_input_request' as const,
            status: 'pending' as const,
            order: 0,
            item_key: 'req_latest',
            created_at: '2026-03-15T00:00:02Z',
            updated_at: '2026-03-15T00:00:02Z',
            payload: {
              part_id: 'msg_exec_request:req_latest:user_input_request',
              request_id: 'req_latest',
              request_kind: 'user_input',
              resolution_state: 'pending',
              title: 'Runtime input needed',
              thread_id: 'thread_exec_1',
              turn_id: 'turn_1',
              questions: [
                {
                  id: 'brand_direction',
                  header: 'Brand direction',
                  question: 'What visual direction should we use?',
                  options: [
                    { label: 'Editorial', description: 'Structured and dense.' },
                    { label: 'Playful', description: 'Expressive and bold.' },
                  ],
                  is_other: false,
                  is_secret: false,
                },
              ],
            },
          },
        ],
      },
    ],
  }
}

function makeAskConversationSnapshotWithMessage(
  text: string,
  overrides: {
    conversationId?: string
    nodeId?: string
    eventSeq?: number
  } = {},
) {
  const conversationId = overrides.conversationId ?? 'conv_ask_1'
  const nodeId = overrides.nodeId ?? 'root'
  const eventSeq = overrides.eventSeq ?? 3
  return {
    record: {
      conversation_id: conversationId,
      project_id: 'project-1',
      node_id: nodeId,
      thread_type: 'ask' as const,
      app_server_thread_id: null,
      current_runtime_mode: 'ask' as const,
      status: 'completed' as const,
      active_stream_id: null,
      event_seq: eventSeq,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:01Z',
    },
    messages: [
      {
        message_id: 'ask_msg_1',
        conversation_id: conversationId,
        turn_id: 'turn_1',
        role: 'assistant' as const,
        runtime_mode: 'ask' as const,
        status: 'completed' as const,
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:01Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'ask_part_1',
            part_type: 'assistant_text' as const,
            status: 'completed' as const,
            order: 0,
            item_key: null,
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
            payload: { text },
          },
        ],
      },
    ],
  }
}

function makePlanningConversationSnapshotWithMessage(
  text: string,
  overrides: {
    conversationId?: string
    nodeId?: string
    eventSeq?: number
  } = {},
) {
  const conversationId = overrides.conversationId ?? 'conv_plan_1'
  const nodeId = overrides.nodeId ?? 'root'
  const eventSeq = overrides.eventSeq ?? 5
  return {
    record: {
      conversation_id: conversationId,
      project_id: 'project-1',
      node_id: nodeId,
      thread_type: 'planning' as const,
      app_server_thread_id: null,
      current_runtime_mode: 'planning' as const,
      status: 'completed' as const,
      active_stream_id: null,
      event_seq: eventSeq,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:01Z',
    },
    messages: [
      {
        message_id: 'planning_msg_1',
        conversation_id: conversationId,
        turn_id: 'turn_1',
        role: 'assistant' as const,
        runtime_mode: 'planning' as const,
        status: 'completed' as const,
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:01Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'planning_part_1',
            part_type: 'assistant_text' as const,
            status: 'completed' as const,
            order: 0,
            item_key: null,
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
            payload: { text },
          },
        ],
      },
    ],
  }
}

function makePlanningConversationSnapshotWithUserInputRequests() {
  const snapshot = makePlanningConversationSnapshotWithMessage('Planning v2 transcript', {
    conversationId: 'conv_plan_requests',
    nodeId: 'child-1',
    eventSeq: 8,
  })
  return {
    ...snapshot,
    record: {
      ...snapshot.record,
      status: 'active' as const,
      active_stream_id: 'planning_stream:turn_plan_1',
    },
    messages: [
      ...snapshot.messages,
      {
        message_id: 'planning_request_message:req_old',
        conversation_id: snapshot.record.conversation_id,
        turn_id: 'turn_plan_1',
        role: 'assistant' as const,
        runtime_mode: 'planning' as const,
        status: 'pending' as const,
        created_at: '2026-03-15T00:00:02Z',
        updated_at: '2026-03-15T00:00:02Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'planning_request_message:req_old:user_input_request',
            part_type: 'user_input_request' as const,
            status: 'pending' as const,
            order: 0,
            item_key: 'req_old',
            created_at: '2026-03-15T00:00:02Z',
            updated_at: '2026-03-15T00:00:02Z',
            payload: {
              part_id: 'planning_request_message:req_old:user_input_request',
              request_id: 'req_old',
              request_kind: 'user_input',
              resolution_state: 'pending',
              title: 'Old planner input',
              thread_id: 'thread_plan_1',
              turn_id: 'turn_plan_1',
              questions: [
                {
                  id: 'deprecated',
                  header: 'Deprecated',
                  question: 'Old question',
                  options: [],
                  is_other: false,
                  is_secret: false,
                },
              ],
            },
          },
        ],
      },
      {
        message_id: 'planning_request_message:req_latest',
        conversation_id: snapshot.record.conversation_id,
        turn_id: 'turn_plan_1',
        role: 'assistant' as const,
        runtime_mode: 'planning' as const,
        status: 'pending' as const,
        created_at: '2026-03-15T00:00:03Z',
        updated_at: '2026-03-15T00:00:03Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'planning_request_message:req_latest:user_input_request',
            part_type: 'user_input_request' as const,
            status: 'pending' as const,
            order: 0,
            item_key: 'req_latest',
            created_at: '2026-03-15T00:00:03Z',
            updated_at: '2026-03-15T00:00:03Z',
            payload: {
              part_id: 'planning_request_message:req_latest:user_input_request',
              request_id: 'req_latest',
              request_kind: 'user_input',
              resolution_state: 'pending',
              title: 'Planning runtime input needed',
              thread_id: 'thread_plan_1',
              turn_id: 'turn_plan_1',
              questions: [
                {
                  id: 'brand_direction',
                  header: 'Brand direction',
                  question: 'What visual direction should we use?',
                  options: [
                    { label: 'Editorial', description: 'Structured and dense.' },
                    { label: 'Playful', description: 'Expressive and bold.' },
                  ],
                  is_other: false,
                  is_secret: false,
                },
              ],
            },
          },
        ],
      },
    ],
  }
}

function createDeferredPromise<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function WorkspaceWithLocationProbe() {
  const location = useLocation()
  const hasComposerSeed =
    typeof (location.state as { composerSeed?: unknown } | null)?.composerSeed === 'string'

  return (
    <>
      <BreadcrumbWorkspace />
      <div data-testid="composer-seed-state">{hasComposerSeed ? 'present' : 'cleared'}</div>
    </>
  )
}

function PlanningWorkspaceWithNodeSwitch() {
  const navigate = useNavigate()

  return (
    <>
      <button
        type="button"
        onClick={() =>
          navigate('/projects/project-1/nodes/child-1/chat', {
            state: { activeTab: 'planning' as const },
          })
        }
      >
        Switch Planning Node
      </button>
      <BreadcrumbWorkspace />
    </>
  )
}

describe('BreadcrumbWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllEnvs()
    vi.stubEnv('VITE_EXECUTION_CONVERSATION_V2_ENABLED', 'false')
    vi.stubEnv('VITE_PLANNING_CONVERSATION_V2_ENABLED', 'false')
    useAskStore.setState(useAskStore.getInitialState())
    useChatStore.setState(useChatStore.getInitialState())
    useConversationStore.setState(useConversationStore.getInitialState())
    useProjectStore.setState(useProjectStore.getInitialState())
    useUIStore.setState(useUIStore.getInitialState())
    apiMock.planningEventsUrl.mockReturnValue('/v1/projects/project-1/nodes/root/planning/events')
    apiMock.getPlanningConversation.mockResolvedValue({
      conversation: makePlanningConversationSnapshotWithMessage('Planning v2 transcript'),
    })
    apiMock.planningConversationEventsUrl.mockReturnValue(
      '/v2/projects/project-1/nodes/root/conversations/planning/events?after_event_seq=0',
    )
    apiMock.agentEventsUrl.mockReturnValue('/v1/projects/project-1/nodes/root/agent/events')
    apiMock.chatEventsUrl.mockReturnValue('/v1/projects/project-1/nodes/root/chat/events')
    apiMock.askEventsUrl.mockReturnValue('/v1/projects/project-1/nodes/root/ask/events')
    apiMock.getAskConversation.mockResolvedValue({
      conversation: {
        record: {
          conversation_id: 'conv_ask_1',
          project_id: 'project-1',
          node_id: 'root',
          thread_type: 'ask',
          app_server_thread_id: null,
          current_runtime_mode: 'ask',
          status: 'idle',
          active_stream_id: null,
          event_seq: 0,
          created_at: '2026-03-15T00:00:00Z',
          updated_at: '2026-03-15T00:00:00Z',
        },
        messages: [],
      },
    })
    apiMock.sendAskConversationMessage.mockResolvedValue({
      status: 'accepted',
      conversation_id: 'conv_ask_1',
      turn_id: 'turn_1',
      stream_id: 'ask_stream:turn_1',
      user_message_id: 'msg_user',
      assistant_message_id: 'msg_assistant',
      assistant_text_part_id: 'ask_part:msg_assistant:assistant_text',
    })
    apiMock.askConversationEventsUrl.mockReturnValue(
      '/v2/projects/project-1/nodes/root/conversations/ask/events?after_event_seq=0',
    )
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeExecutionConversationSnapshot(),
    })
    apiMock.sendExecutionConversationMessage.mockResolvedValue({
      status: 'accepted',
      conversation_id: 'conv_exec_1',
      turn_id: 'turn_1',
      stream_id: 'stream_1',
      user_message_id: 'msg_user',
      assistant_message_id: 'msg_assistant',
      assistant_text_part_id: 'part_assistant',
    })
    apiMock.resolveExecutionConversationRequest.mockResolvedValue({
      status: 'resolved',
    })
    apiMock.resolvePlanningConversationRequest.mockResolvedValue({
      status: 'resolved',
    })
    apiMock.executionConversationEventsUrl.mockReturnValue(
      '/v2/projects/project-1/nodes/root/conversations/execution/events?after_event_seq=0',
    )
    apiMock.getNodeDocuments.mockResolvedValue(makeNodeDocuments())
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('renders the breadcrumb chat shell and applies a transient composer seed', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: {
              composerSeed:
                'Task: Alpha\nDescription: Ship phase 3\n\nPlease help me complete this task.',
            },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Planning Thread')).toBeInTheDocument()
    const currentCrumb = screen.getByText('1 - Alpha')
    expect(currentCrumb).toBeInTheDocument()
    expect(currentCrumb).toHaveAttribute('aria-current', 'page')
    expect(currentCrumb).toHaveAttribute('title', '1 - Alpha')
    expect(screen.getByText('1 / Alpha')).toBeInTheDocument()
    expect(useChatStore.getState().composerDraft).toBe(
      'Task: Alpha\nDescription: Ship phase 3\n\nPlease help me complete this task.',
    )
  })

  it('redirects to the graph route when the node is missing', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={['/projects/project-1/nodes/missing/chat']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/" element={<div>graph home</div>} />
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('graph home')).toBeInTheDocument()
    })
  })

  it('does not persist the active node when the breadcrumb route already matches selection', async () => {
    const selectNode = vi.fn(async () => {})

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode,
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={['/projects/project-1/nodes/root/chat']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Planning Thread')).toBeInTheDocument()
    await waitFor(() => {
      expect(selectNode).not.toHaveBeenCalled()
    })
  })

  it('persists the active node once when the route node differs and does not loop after snapshot refresh', async () => {
    const refreshedSnapshot = {
      ...childSnapshot,
      tree_state: {
        ...childSnapshot.tree_state,
        active_node_id: 'child-1',
      },
      updated_at: '2026-03-07T10:06:00Z',
    }
    const selectNode = vi.fn(async () => {
      useProjectStore.setState({
        snapshot: refreshedSnapshot,
        selectedNodeId: 'child-1',
      })
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot: childSnapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode,
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={['/projects/project-1/nodes/child-1/chat']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Planning Thread')).toBeInTheDocument()
    await waitFor(() => {
      expect(selectNode).toHaveBeenCalledTimes(1)
    })
    expect(selectNode).toHaveBeenCalledWith('child-1', true)
    expect(useProjectStore.getState().selectedNodeId).toBe('child-1')
  })

  it('renders the document workflow tabs in the new order', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={['/projects/project-1/nodes/root/chat']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Planning Thread')).toBeInTheDocument()
    const tabs = screen
      .getAllByRole('button')
      .map((button) => button.textContent)
      .filter((value): value is string =>
        value === 'Planning' ||
        value === 'Task' ||
        value === 'Ask' ||
        value === 'Brief' ||
        value === 'Spec' ||
        value === 'Execution',
      )
    expect(tabs).toEqual(['Planning', 'Task', 'Ask', 'Brief', 'Spec', 'Execution'])
  })

  it('opens the Ask tab when route state requests it', async () => {
    const loadAskSession = vi.fn(async () => {
      useAskStore.setState({
        session: {
          project_id: 'project-1',
          node_id: 'root',
          active_turn_id: null,
          event_seq: 0,
          status: null,
          messages: [],
          delta_context_packets: [],
        },
      })
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      loadSession: loadAskSession,
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'ask' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText("Ask a question about this node's plan")).toBeInTheDocument()
    expect(loadAskSession).toHaveBeenCalledWith('project-1', 'root')
  })

  it('uses ask v2 as the visible transcript source when the ask host flag is on', async () => {
    vi.stubEnv('VITE_ASK_CONVERSATION_V2_ENABLED', 'true')
    const loadAskSession = vi.fn(async () => {
      useAskStore.setState({
        session: {
          project_id: 'project-1',
          node_id: 'root',
          active_turn_id: null,
          event_seq: 2,
          status: 'idle',
          messages: [
            {
              message_id: 'legacy_ask_msg',
              role: 'assistant',
              content: 'Legacy ask transcript',
              status: 'completed',
              created_at: '2026-03-15T00:00:00Z',
              updated_at: '2026-03-15T00:00:00Z',
              error: null,
            },
          ],
          delta_context_packets: [],
        },
      })
    })
    apiMock.getAskConversation.mockResolvedValue({
      conversation: makeAskConversationSnapshotWithMessage('Ask v2 transcript'),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      loadSession: loadAskSession,
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'ask' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Ask v2 transcript')).toBeInTheDocument()
    expect(screen.queryByText('Legacy ask transcript')).not.toBeInTheDocument()
    expect(apiMock.getAskConversation).toHaveBeenCalledWith('project-1', 'root')
    expect(loadAskSession).toHaveBeenCalledWith('project-1', 'root')
  })

  it('keeps ask v2 loading visible without falling back to the legacy ask transcript', async () => {
    vi.stubEnv('VITE_ASK_CONVERSATION_V2_ENABLED', 'true')
    const deferredConversation = createDeferredPromise<{
      conversation: ReturnType<typeof makeAskConversationSnapshotWithMessage>
    }>()
    const loadAskSession = vi.fn(async () => {
      useAskStore.setState({
        session: {
          project_id: 'project-1',
          node_id: 'root',
          active_turn_id: null,
          event_seq: 2,
          status: 'idle',
          messages: [
            {
              message_id: 'legacy_ask_msg',
              role: 'assistant',
              content: 'Legacy ask transcript',
              status: 'completed',
              created_at: '2026-03-15T00:00:00Z',
              updated_at: '2026-03-15T00:00:00Z',
              error: null,
            },
          ],
          delta_context_packets: [],
        },
      })
    })
    apiMock.getAskConversation.mockImplementation(() => deferredConversation.promise)

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      loadSession: loadAskSession,
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'ask' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.queryByText('Legacy ask transcript')).not.toBeInTheDocument()

    deferredConversation.resolve({
      conversation: makeAskConversationSnapshotWithMessage('Ask v2 transcript'),
    })

    expect(await screen.findByText('Ask v2 transcript')).toBeInTheDocument()
  })

  it('uses planning v2 as the visible transcript source when the planning host flag is on', async () => {
    vi.stubEnv('VITE_PLANNING_CONVERSATION_V2_ENABLED', 'true')
    apiMock.getPlanningConversation.mockResolvedValue({
      conversation: makePlanningConversationSnapshotWithMessage('Planning v2 transcript'),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      planningHistoryByNode: {
        root: [
          {
            turn_id: 'legacy-turn',
            role: 'assistant',
            content: 'Legacy planning transcript',
            is_inherited: false,
            origin_node_id: 'root',
            timestamp: '2026-03-15T00:00:00Z',
          },
        ],
      },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'planning' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Planning v2 transcript')).toBeInTheDocument()
    expect(screen.queryByText('Legacy planning transcript')).not.toBeInTheDocument()
    expect(apiMock.getPlanningConversation).toHaveBeenCalledWith('project-1', 'root')
    expect(apiMock.planningEventsUrl).not.toHaveBeenCalled()
  })

  it('keeps planning v2 loading visible without falling back to the legacy planning transcript', async () => {
    vi.stubEnv('VITE_PLANNING_CONVERSATION_V2_ENABLED', 'true')
    const deferredConversation = createDeferredPromise<{
      conversation: ReturnType<typeof makePlanningConversationSnapshotWithMessage>
    }>()
    apiMock.getPlanningConversation.mockImplementation(() => deferredConversation.promise)

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      planningHistoryByNode: {
        root: [
          {
            turn_id: 'legacy-turn',
            role: 'assistant',
            content: 'Legacy planning transcript',
            is_inherited: false,
            origin_node_id: 'root',
            timestamp: '2026-03-15T00:00:00Z',
          },
        ],
      },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'planning' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.queryByText('Legacy planning transcript')).not.toBeInTheDocument()
    expect(apiMock.planningEventsUrl).not.toHaveBeenCalled()

    deferredConversation.resolve({
      conversation: makePlanningConversationSnapshotWithMessage('Planning v2 transcript'),
    })

    expect(await screen.findByText('Planning v2 transcript')).toBeInTheDocument()
  })

  it('clears planning busy state when a terminal planning v2 snapshot loads without the legacy planning stream', async () => {
    vi.stubEnv('VITE_PLANNING_CONVERSATION_V2_ENABLED', 'true')
    apiMock.getPlanningConversation.mockResolvedValue({
      conversation: makePlanningConversationSnapshotWithMessage('Planning v2 transcript'),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      isSplittingNode: true,
      splittingNodeId: 'root',
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'planning' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Planning v2 transcript')).toBeInTheDocument()
    await waitFor(() => {
      expect(useProjectStore.getState().isSplittingNode).toBe(false)
      expect(useProjectStore.getState().splittingNodeId).toBeNull()
    })
  })

  it('keeps planning busy state scoped to the current node when the planning v2 host switches nodes', async () => {
    vi.stubEnv('VITE_PLANNING_CONVERSATION_V2_ENABLED', 'true')
    apiMock.getPlanningConversation.mockImplementation(async (_projectId: string, nodeId: string) => {
      if (nodeId === 'root') {
        const activeConversation = makePlanningConversationSnapshotWithMessage('Planning root transcript')
        activeConversation.record.status = 'active'
        activeConversation.record.active_stream_id = 'planning_stream:root'
        activeConversation.messages[0].status = 'pending'
        activeConversation.messages[0].parts[0].status = 'pending'
        return { conversation: activeConversation }
      }

      return {
        conversation: makePlanningConversationSnapshotWithMessage('Planning child transcript', {
          conversationId: 'conv_plan_child',
          nodeId: 'child-1',
          eventSeq: 1,
        }),
      }
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot: childSnapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'planning' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat"
            element={<PlanningWorkspaceWithNodeSwitch />}
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Planning root transcript')).toBeInTheDocument()
    await waitFor(() => {
      expect(useProjectStore.getState().isSplittingNode).toBe(true)
      expect(useProjectStore.getState().splittingNodeId).toBe('root')
    })

    fireEvent.click(screen.getByRole('button', { name: 'Switch Planning Node' }))

    expect(await screen.findByText('Planning child transcript')).toBeInTheDocument()
    await waitFor(() => {
      expect(useProjectStore.getState().isSplittingNode).toBe(false)
      expect(useProjectStore.getState().splittingNodeId).toBeNull()
    })
  })

  it('clears scoped planning busy state when the planning v2 host unmounts', async () => {
    vi.stubEnv('VITE_PLANNING_CONVERSATION_V2_ENABLED', 'true')
    apiMock.getPlanningConversation.mockImplementation(async () => {
      const activeConversation = makePlanningConversationSnapshotWithMessage('Planning root transcript')
      activeConversation.record.status = 'active'
      activeConversation.record.active_stream_id = 'planning_stream:root'
      activeConversation.messages[0].status = 'pending'
      activeConversation.messages[0].parts[0].status = 'pending'
      return { conversation: activeConversation }
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    const view = render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'planning' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Planning root transcript')).toBeInTheDocument()
    await waitFor(() => {
      expect(useProjectStore.getState().isSplittingNode).toBe(true)
      expect(useProjectStore.getState().splittingNodeId).toBe('root')
    })

    view.unmount()

    expect(useProjectStore.getState().isSplittingNode).toBe(false)
    expect(useProjectStore.getState().splittingNodeId).toBeNull()
  })

  it('loads node documents when the task tab is opened', async () => {
    const documents = makeNodeDocuments()
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => {
        useProjectStore.setState((state) => ({
          documentsByNode: {
            ...state.documentsByNode,
            root: documents,
          },
        }))
      }),
      updateNodeBriefing: vi.fn(async () => {}),
      confirmBriefing: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'task' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Task' })).toBeInTheDocument()
  })

  it('loads node documents when the briefing tab is opened', async () => {
    const documents = makeNodeDocuments()
    const loadNodeDocuments = vi.fn(async () => {
      useProjectStore.setState((state) => ({
        documentsByNode: {
          ...state.documentsByNode,
          root: documents,
        },
      }))
    })
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments,
      updateNodeBriefing: vi.fn(async () => {}),
      confirmBriefing: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'briefing' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Brief' })).toBeInTheDocument()
    expect(loadNodeDocuments).toHaveBeenCalledWith('root')
  })

  it('disables start execution before the node is ready', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'root',
      snapshot,
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/root/chat',
            state: { activeTab: 'execution' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('button', { name: 'Plan' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Execute' })).toBeDisabled()
  })

  it('shows the native planner input modal in the execution tab when the plan is waiting for an answer', async () => {
    const documents = makeNodeDocuments()
    documents.state.phase = 'ready_for_execution'
    documents.state.spec_confirmed = true
    documents.state.brief_generation_status = 'ready'
    documents.state.active_spec_version = 2
    documents.state.bound_plan_spec_version = 2
    documents.state.brief_version = 3
    documents.state.bound_plan_brief_version = 3
    documents.state.plan_status = 'waiting_on_input'
    const loadSession = vi.fn(async () => {
      useChatStore.setState({
        session: {
          project_id: 'project-1',
          node_id: 'child-1',
          active_turn_id: 'turn_plan_1',
          event_seq: 0,
          status: 'active',
          mode: 'plan',
          config: {
            access_mode: 'project_write',
            cwd: 'C:/workspace/alpha',
            writable_roots: ['C:/workspace/alpha'],
            timeout_sec: 120,
          },
          pending_input_request: {
            request_id: 'req_1',
            thread_id: 'thread_1',
            turn_id: 'turn_plan_1',
            node_id: 'child-1',
            item_id: 'item_1',
            created_at: '2026-03-13T20:00:00Z',
            resolved_at: null,
            status: 'pending',
            answer_payload: null,
            questions: [
              {
                id: 'brand_direction',
                header: 'Brand direction',
                question:
                  'What visual style should the site shell follow? This choice materially changes layout and typography.',
                is_other: false,
                is_secret: false,
                options: [
                  { label: 'Editorial', description: 'Dense, text-forward, and structured.' },
                  { label: 'Playful', description: 'Expressive, colorful, and motion-led.' },
                ],
              },
            ],
          },
          runtime_request_registry: [
            {
              request_id: 'req_1',
              thread_id: 'thread_1',
              turn_id: 'turn_plan_1',
              node_id: 'child-1',
              item_id: 'item_1',
              created_at: '2026-03-13T20:00:00Z',
              resolved_at: null,
              status: 'pending',
              answer_payload: null,
              questions: [
                {
                  id: 'brand_direction',
                  header: 'Brand direction',
                  question:
                    'What visual style should the site shell follow? This choice materially changes layout and typography.',
                  is_other: false,
                  is_secret: false,
                  options: [
                    { label: 'Editorial', description: 'Dense, text-forward, and structured.' },
                    { label: 'Playful', description: 'Expressive, colorful, and motion-led.' },
                  ],
                },
              ],
            },
          ],
          messages: [
            {
              message_id: 'msg_assistant_1',
              role: 'assistant',
              content: 'I need one blocking clarification before I can finalize the plan.',
              status: 'completed',
              created_at: '2026-03-13T20:00:00Z',
              updated_at: '2026-03-13T20:00:00Z',
              error: null,
            },
          ],
        },
      })
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': documents },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => documents),
      resyncNodeArtifacts: vi.fn(async () => {}),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession,
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: { activeTab: 'execution' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('One quick answer before the plan can finish')).toBeInTheDocument()
    expect(screen.getByText('Brand direction')).toBeInTheDocument()
    expect(
      screen.getByText(
        'What visual style should the site shell follow? This choice materially changes layout and typography.',
      ),
    ).toBeInTheDocument()
    expect(loadSession).toHaveBeenCalledWith('project-1', 'child-1')
    expect(
      screen.getByPlaceholderText('Planner input is handled through the native modal when needed.'),
    ).toBeInTheDocument()
  })

  it('renders the latest unresolved execution-v2 request inline and submits through the v2 resolve route', async () => {
    vi.stubEnv('VITE_EXECUTION_CONVERSATION_V2_ENABLED', 'true')
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeExecutionConversationSnapshotWithUserInputRequest(),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': makeNodeDocuments() },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => makeNodeDocuments()),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: { activeTab: 'execution' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Runtime input needed')).toBeInTheDocument()
    expect(screen.getByText('Brand direction')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('Deprecated')).not.toBeInTheDocument()
    expect(
      screen.getByPlaceholderText('Answer the inline runtime request to continue the current execution.'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('radio', { name: /Editorial Structured and dense\./ }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() => {
      expect(apiMock.resolveExecutionConversationRequest).toHaveBeenCalledWith(
        'project-1',
        'child-1',
        'req_latest',
        {
          request_kind: 'user_input',
          answers: {
            brand_direction: {
              answers: ['Editorial'],
            },
          },
          thread_id: 'thread_exec_1',
          turn_id: 'turn_1',
        },
      )
    })
  })

  it('uses planning-v2 request ownership on the planning tab and submits through the planning resolve route', async () => {
    vi.stubEnv('VITE_PLANNING_CONVERSATION_V2_ENABLED', 'true')
    apiMock.getPlanningConversation.mockResolvedValue({
      conversation: makePlanningConversationSnapshotWithUserInputRequests(),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': makeNodeDocuments() },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => makeNodeDocuments()),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
      session: {
        project_id: 'project-1',
        node_id: 'child-1',
        active_turn_id: 'turn_plan_legacy',
        event_seq: 1,
        status: 'active',
        mode: 'plan',
        config: {
          access_mode: 'project_write',
          cwd: 'C:/workspace/alpha',
          writable_roots: ['C:/workspace/alpha'],
          timeout_sec: 120,
        },
        pending_input_request: {
          request_id: 'legacy_req',
          thread_id: 'thread_legacy',
          turn_id: 'turn_plan_legacy',
          node_id: 'child-1',
          item_id: 'item_legacy',
          created_at: '2026-03-15T00:00:01Z',
          resolved_at: null,
          status: 'pending',
          answer_payload: null,
          questions: [
            {
              id: 'legacy',
              header: 'Legacy',
              question: 'Legacy prompt',
              is_other: false,
              is_secret: false,
              options: [],
            },
          ],
        },
        runtime_request_registry: [],
        messages: [],
      },
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: { activeTab: 'planning' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('One quick answer before the plan can finish')).toBeInTheDocument()
    const dialog = screen.getByRole('dialog', { name: 'One quick answer before the plan can finish' })
    expect(within(dialog).getByText('Brand direction')).toBeInTheDocument()
    expect(within(dialog).queryByText('Deprecated')).not.toBeInTheDocument()
    expect(within(dialog).queryByText('Legacy')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('radio', { name: /Editorial Structured and dense\./ }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue planning' }))

    await waitFor(() => {
      expect(apiMock.resolvePlanningConversationRequest).toHaveBeenCalledWith(
        'project-1',
        'child-1',
        'req_latest',
        {
          request_kind: 'user_input',
          answers: {
            brand_direction: {
              answers: ['Editorial'],
            },
          },
          thread_id: 'thread_plan_1',
          turn_id: 'turn_plan_1',
        },
      )
    })
    expect(apiMock.resolveExecutionConversationRequest).not.toHaveBeenCalled()
  })

  it('mounts the non-visible execution conversation hook only for the execution tab', async () => {
    vi.stubEnv('VITE_EXECUTION_CONVERSATION_V2_ENABLED', 'true')

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': makeNodeDocuments() },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => makeNodeDocuments()),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: { activeTab: 'planning' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Planning Thread')).toBeInTheDocument()
    expect(apiMock.getExecutionConversation).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Execution' }))

    await waitFor(() => {
      expect(apiMock.getExecutionConversation).toHaveBeenCalledWith('project-1', 'child-1')
    })
    expect(apiMock.executionConversationEventsUrl).toHaveBeenCalled()
    expect(screen.getByPlaceholderText('Click Plan to prepare execution.')).toBeInTheDocument()
  })

  it('does not mount hidden execution-v2 plumbing when the feature flag is disabled', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': makeNodeDocuments() },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => makeNodeDocuments()),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: { activeTab: 'execution' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('button', { name: 'Plan' })).toBeInTheDocument()
    expect(apiMock.getExecutionConversation).not.toHaveBeenCalled()
    expect(apiMock.executionConversationEventsUrl).not.toHaveBeenCalled()
    expect(
      screen.getByPlaceholderText('Planner input is handled through the native modal when needed.'),
    ).toBeInTheDocument()
  })

  it('shows the visible execution transcript from v2 when the cutover flag is enabled', async () => {
    vi.stubEnv('VITE_EXECUTION_CONVERSATION_V2_ENABLED', 'true')

    const loadSession = vi.fn(async () => {
      useChatStore.setState({
        session: {
          project_id: 'project-1',
          node_id: 'child-1',
          active_turn_id: null,
          event_seq: 1,
          status: 'active',
          mode: 'plan',
          config: {
            access_mode: 'project_write',
            cwd: 'C:/workspace/alpha',
            writable_roots: ['C:/workspace/alpha'],
            timeout_sec: 120,
          },
          pending_input_request: null,
          messages: [
            {
              message_id: 'legacy_msg_1',
              role: 'assistant',
              content: 'Legacy execution transcript',
              created_at: '2026-03-15T00:00:00Z',
              updated_at: '2026-03-15T00:00:00Z',
              status: 'completed',
              error: null,
            },
          ],
        },
        connectionStatus: 'connected',
      })
    })
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeExecutionConversationSnapshotWithMessage('Execution v2 visible transcript'),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': makeNodeDocuments() },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => makeNodeDocuments()),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession,
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: { activeTab: 'execution' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Execution v2 visible transcript')).toBeInTheDocument()
    expect(loadSession).toHaveBeenCalledWith('project-1', 'child-1')
    expect(screen.queryByText('Legacy execution transcript')).not.toBeInTheDocument()
  })

  it('keeps the visible execution transcript legacy-owned when the cutover flag is disabled', async () => {
    const loadSession = vi.fn(async () => {
      useChatStore.setState({
        session: {
          project_id: 'project-1',
          node_id: 'child-1',
          active_turn_id: null,
          event_seq: 1,
          status: 'active',
          mode: 'plan',
          config: {
            access_mode: 'project_write',
            cwd: 'C:/workspace/alpha',
            writable_roots: ['C:/workspace/alpha'],
            timeout_sec: 120,
          },
          pending_input_request: null,
          messages: [
            {
              message_id: 'legacy_msg_1',
              role: 'assistant',
              content: 'Legacy execution transcript',
              created_at: '2026-03-15T00:00:00Z',
              updated_at: '2026-03-15T00:00:00Z',
              status: 'completed',
              error: null,
            },
          ],
        },
        connectionStatus: 'connected',
      })
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': makeNodeDocuments() },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => makeNodeDocuments()),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession,
    })
    useConversationStore.getState().ensureConversation(
      makeExecutionConversationSnapshotWithMessage('Execution v2 transcript'),
    )

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: { activeTab: 'execution' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Legacy execution transcript')).toBeInTheDocument()
    expect(loadSession).toHaveBeenCalledWith('project-1', 'child-1')
    expect(apiMock.getExecutionConversation).not.toHaveBeenCalled()
    expect(screen.queryByText('Execution v2 transcript')).not.toBeInTheDocument()
  })

  it('applies a delayed execution-v2 composer seed exactly once after hydration, then clears route state', async () => {
    vi.stubEnv('VITE_EXECUTION_CONVERSATION_V2_ENABLED', 'true')

    const deferredSnapshot = createDeferredPromise<{ conversation: ReturnType<typeof makeExecutionConversationSnapshot> }>()
    const seed = 'Ship the execution follow-up'
    const setComposerDraftSpy = vi.spyOn(useConversationStore.getState(), 'setComposerDraft')

    apiMock.getExecutionConversation.mockReturnValue(deferredSnapshot.promise)

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': makeNodeDocuments() },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => makeNodeDocuments()),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus: vi.fn(),
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: {
              activeTab: 'execution' as const,
              composerSeed: seed,
            },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<WorkspaceWithLocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByTestId('composer-seed-state')).toHaveTextContent('present')
    expect(setComposerDraftSpy).not.toHaveBeenCalled()

    await act(async () => {
      deferredSnapshot.resolve({
        conversation: {
          ...makeExecutionConversationSnapshot(),
          record: {
            ...makeExecutionConversationSnapshot().record,
            node_id: 'child-1',
          },
        },
      })
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(
        useConversationStore.getState().conversationsById.conv_exec_1.composerDraft,
      ).toBe(seed)
    })
    await waitFor(() => {
      expect(screen.getByTestId('composer-seed-state')).toHaveTextContent('cleared')
    })
    expect(setComposerDraftSpy).toHaveBeenCalledTimes(1)
  })

  it('does not patch node status from old completed execution history alone when v2 is visible', async () => {
    vi.stubEnv('VITE_EXECUTION_CONVERSATION_V2_ENABLED', 'true')

    const patchNodeStatus = vi.fn()
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeExecutionConversationSnapshotWithMessage('Old completed run', {
        record: {
          node_id: 'child-1',
          status: 'completed',
          active_stream_id: null,
        },
      }),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': makeNodeDocuments() },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => makeNodeDocuments()),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus,
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: { activeTab: 'execution' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Old completed run')).toBeInTheDocument()
    expect(patchNodeStatus).not.toHaveBeenCalled()
  })

  it('patches node status from live execution-v2 activity when the cutover flag is enabled', async () => {
    vi.stubEnv('VITE_EXECUTION_CONVERSATION_V2_ENABLED', 'true')

    const patchNodeStatus = vi.fn((targetNodeId: string, status: 'in_progress') => {
      useProjectStore.setState((state) => ({
        snapshot: state.snapshot
          ? {
              ...state.snapshot,
              tree_state: {
                ...state.snapshot.tree_state,
                node_registry: state.snapshot.tree_state.node_registry.map((item) =>
                  item.node_id === targetNodeId ? { ...item, status } : item,
                ),
              },
            }
          : state.snapshot,
      }))
    })
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeExecutionConversationSnapshotWithMessage('Live execution run', {
        record: {
          node_id: 'child-1',
          status: 'active',
          active_stream_id: 'stream_1',
        },
      }),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      bootstrap: { ready: true, workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: childSnapshot,
      documentsByNode: { 'child-1': makeNodeDocuments() },
      initialize: vi.fn(async () => {}),
      loadProject: vi.fn(async () => {}),
      loadPlanningHistory: vi.fn(async () => {}),
      loadNodeDocuments: vi.fn(async () => makeNodeDocuments()),
      selectNode: vi.fn(async () => {}),
      patchNodeStatus,
      startPlan: vi.fn(async () => {}),
      executeNode: vi.fn(async () => {}),
    })
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      loadSession: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/projects/project-1/nodes/child-1/chat',
            state: { activeTab: 'execution' as const },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbWorkspace />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Live execution run')).toBeInTheDocument()
    await waitFor(() => {
      expect(patchNodeStatus).toHaveBeenCalledWith('child-1', 'in_progress')
    })
  })
})
