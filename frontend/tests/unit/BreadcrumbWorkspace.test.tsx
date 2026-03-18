import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock, hookMocks } = vi.hoisted(() => ({
  apiMock: {
    resolveExecutionConversationRequest: vi.fn(),
    resolvePlanningConversationRequest: vi.fn(),
  },
  hookMocks: {
    useAgentEventStream: vi.fn(),
    useAskSidecarStream: vi.fn(),
    useExecutionConversation: vi.fn(),
    useAskConversation: vi.fn(),
    usePlanningConversation: vi.fn(),
    useConversationRequests: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
}))

vi.mock('../../src/api/hooks', () => ({
  useAgentEventStream: hookMocks.useAgentEventStream,
  useAskSidecarStream: hookMocks.useAskSidecarStream,
}))

vi.mock('../../src/features/conversation/hooks/useExecutionConversation', () => ({
  useExecutionConversation: hookMocks.useExecutionConversation,
}))

vi.mock('../../src/features/conversation/hooks/useAskConversation', () => ({
  useAskConversation: hookMocks.useAskConversation,
}))

vi.mock('../../src/features/conversation/hooks/usePlanningConversation', () => ({
  usePlanningConversation: hookMocks.usePlanningConversation,
}))

vi.mock('../../src/features/conversation/hooks/useConversationRequests', () => ({
  useConversationRequests: hookMocks.useConversationRequests,
}))

import { BreadcrumbWorkspace } from '../../src/features/breadcrumb/BreadcrumbWorkspace'
import type { ConversationSnapshot } from '../../src/features/conversation/types'
import { useAskStore } from '../../src/stores/ask-store'
import { useConversationStore } from '../../src/stores/conversation-store'
import { useProjectStore } from '../../src/stores/project-store'
import { useUIStore } from '../../src/stores/ui-store'

function makeNode(overrides: Record<string, unknown> = {}) {
  return {
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
    has_execution_thread: true,
    planning_thread_status: 'idle' as const,
    execution_thread_status: 'idle' as const,
    has_ask_thread: true,
    ask_thread_status: 'idle' as const,
    is_superseded: false,
    created_at: '2026-03-07T10:05:00Z',
    ...overrides,
  }
}

function makeDocuments() {
  return {
    task: { title: 'Alpha', purpose: 'Ship phase 6.3', responsibility: '' },
    brief: null,
    briefing: null,
    spec: null,
    plan: { content: '1. Do the work\n2. Verify it' },
    state: {
      phase: 'ready_for_execution',
      task_confirmed: true,
      briefing_confirmed: true,
      brief_generation_status: 'ready',
      brief_version: 1,
      brief_created_at: '',
      brief_created_from_predecessor_node_id: '',
      brief_generated_by: '',
      brief_source_hash: '',
      brief_source_refs: [],
      brief_late_upstream_policy: 'ignore',
      spec_initialized: true,
      spec_generated: true,
      spec_generation_status: 'ready',
      spec_confirmed: true,
      active_spec_version: 1,
      spec_status: 'confirmed',
      spec_confirmed_at: '',
      initialized_from_brief_version: 1,
      spec_content_hash: '',
      active_plan_version: 1,
      plan_status: 'ready',
      bound_plan_spec_version: 1,
      bound_plan_brief_version: 1,
      bound_plan_input_version: 1,
      active_plan_input_version: 1,
      run_status: 'idle',
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

function makeSnapshot(text: string, threadType: 'execution' | 'ask' | 'planning'): ConversationSnapshot {
  return {
    record: {
      conversation_id: `conv_${threadType}_1`,
      project_id: 'project-1',
      node_id: 'child-1',
      thread_type: threadType,
      app_server_thread_id: null,
      current_runtime_mode:
        threadType === 'execution' ? 'execute' : threadType,
      status: 'completed',
      active_stream_id: null,
      event_seq: 4,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:01Z',
    },
    messages: [
      {
        message_id: `msg_${threadType}_1`,
        conversation_id: `conv_${threadType}_1`,
        turn_id: 'turn_1',
        role: 'assistant',
        runtime_mode:
          threadType === 'execution' ? 'execute' : threadType,
        status: 'completed',
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:01Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: `part_${threadType}_1`,
            part_type: 'assistant_text',
            status: 'completed',
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

function makeConversationViewState(snapshot: ConversationSnapshot) {
  return {
    snapshot,
    connectionStatus: 'connected' as const,
    isLoading: false,
    isSending: false,
    error: null,
  }
}

function renderWorkspace({
  activeTab = 'execution',
  locationState = undefined,
}: {
  activeTab?: 'execution' | 'ask' | 'planning'
  locationState?: Record<string, unknown> | undefined
}) {
  return render(
    <MemoryRouter
      initialEntries={[
        {
          pathname: '/projects/project-1/nodes/child-1',
          state: { activeTab, ...(locationState ?? {}) },
        },
      ]}
    >
      <Routes>
        <Route path="/projects/:projectId/nodes/:nodeId" element={<BreadcrumbWorkspace />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('BreadcrumbWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAskStore.setState(useAskStore.getInitialState())
    useConversationStore.setState(useConversationStore.getInitialState())
    useUIStore.setState(useUIStore.getInitialState())
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      initialize: vi.fn(async () => undefined),
      loadProject: vi.fn(async () => undefined),
      selectNode: vi.fn(async () => undefined),
      startPlan: vi.fn(async () => undefined),
      executeNode: vi.fn(async () => undefined),
      loadNodeDocuments: vi.fn(async () => undefined),
      updateNodeTask: vi.fn(async () => undefined),
      updateNodeSpec: vi.fn(async () => undefined),
      confirmTask: vi.fn(async () => undefined),
      confirmSpec: vi.fn(async () => undefined),
      generateNodeSpec: vi.fn(async () => undefined),
      patchNodeStatus: vi.fn(),
      hasInitialized: true,
      isInitializing: false,
      isLoadingSnapshot: false,
      bootstrap: { workspace_configured: true },
      activeProjectId: 'project-1',
      selectedNodeId: 'child-1',
      snapshot: {
        schema_version: 2,
        project: {
          id: 'project-1',
          name: 'Alpha',
          root_goal: 'Ship phase 6.3',
          base_workspace_root: 'C:/workspace',
          project_workspace_root: 'C:/workspace/alpha',
          created_at: '2026-03-07T10:00:00Z',
          updated_at: '2026-03-07T10:00:00Z',
        },
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'child-1',
          node_registry: [makeNode()],
        },
        updated_at: '2026-03-07T10:05:00Z',
      },
      documentsByNode: {
        'child-1': makeDocuments(),
      },
      agentActivityByNode: {},
    })
    hookMocks.useConversationRequests.mockImplementation(({ conversation }) => ({
      activeRequest: null,
      isSubmitting: false,
      submitError: null,
      submitUserInputResponse: vi.fn(async () => undefined),
      respondToApproval: vi.fn(async () => undefined),
      refresh: vi.fn(),
      conversation,
    }))
  })

  it('renders the execution tab through the v2 conversation host only', async () => {
    const snapshot = makeSnapshot('Execution v2 transcript', 'execution')
    hookMocks.useExecutionConversation.mockReturnValue({
      conversationId: snapshot.record.conversation_id,
      conversation: makeConversationViewState(snapshot),
      bootstrapStatus: 'idle',
      bootstrapError: null,
      send: vi.fn(async () => undefined),
      continueFromMessage: vi.fn(async () => undefined),
      retryFromMessage: vi.fn(async () => undefined),
      regenerateFromMessage: vi.fn(async () => undefined),
      cancelStream: vi.fn(async () => undefined),
      refresh: vi.fn(),
    })
    hookMocks.useAskConversation.mockReturnValue({
      conversationId: null,
      conversation: null,
      bootstrapStatus: 'idle',
      bootstrapError: null,
      send: vi.fn(async () => undefined),
      refresh: vi.fn(),
    })
    hookMocks.usePlanningConversation.mockReturnValue({
      conversationId: null,
      conversation: null,
      bootstrapStatus: 'idle',
      bootstrapError: null,
      refresh: vi.fn(),
    })

    renderWorkspace({ activeTab: 'execution' })

    expect(await screen.findByText('Execution v2 transcript')).toBeInTheDocument()
    expect(screen.queryByText('Legacy execution transcript')).not.toBeInTheDocument()
  })

  it('renders ask v2 transcript with preserved packet sidecar on the ask tab', async () => {
    const snapshot = makeSnapshot('Ask v2 transcript', 'ask')
    hookMocks.useExecutionConversation.mockReturnValue({
      conversationId: null,
      conversation: null,
      bootstrapStatus: 'idle',
      bootstrapError: null,
      send: vi.fn(async () => undefined),
      continueFromMessage: vi.fn(async () => undefined),
      retryFromMessage: vi.fn(async () => undefined),
      regenerateFromMessage: vi.fn(async () => undefined),
      cancelStream: vi.fn(async () => undefined),
      refresh: vi.fn(),
    })
    hookMocks.useAskConversation.mockReturnValue({
      conversationId: snapshot.record.conversation_id,
      conversation: makeConversationViewState(snapshot),
      bootstrapStatus: 'idle',
      bootstrapError: null,
      send: vi.fn(async () => undefined),
      refresh: vi.fn(),
    })
    hookMocks.usePlanningConversation.mockReturnValue({
      conversationId: null,
      conversation: null,
      bootstrapStatus: 'idle',
      bootstrapError: null,
      refresh: vi.fn(),
    })
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      sidecar: {
        projectId: 'project-1',
        nodeId: 'child-1',
        eventSeq: 2,
        packetList: [
          {
            packet_id: 'packet_1',
            node_id: 'child-1',
            created_at: '2026-03-15T00:00:00Z',
            source_message_ids: [],
            summary: 'Context packet',
            context_text: 'Preserved ask-sidecar packet.',
            status: 'pending',
            status_reason: null,
            merged_at: null,
            merged_planning_turn_id: null,
            suggested_by: 'agent',
          },
        ],
      },
    })

    renderWorkspace({ activeTab: 'ask' })

    expect(await screen.findByText('Ask v2 transcript')).toBeInTheDocument()
    expect(screen.getByText('Delta Context Packets')).toBeInTheDocument()
    expect(screen.queryByText('Legacy ask transcript')).not.toBeInTheDocument()
  })

  it('keeps planning loading visible without falling back to legacy planning history', async () => {
    hookMocks.useExecutionConversation.mockReturnValue({
      conversationId: null,
      conversation: null,
      bootstrapStatus: 'idle',
      bootstrapError: null,
      send: vi.fn(async () => undefined),
      continueFromMessage: vi.fn(async () => undefined),
      retryFromMessage: vi.fn(async () => undefined),
      regenerateFromMessage: vi.fn(async () => undefined),
      cancelStream: vi.fn(async () => undefined),
      refresh: vi.fn(),
    })
    hookMocks.useAskConversation.mockReturnValue({
      conversationId: null,
      conversation: null,
      bootstrapStatus: 'idle',
      bootstrapError: null,
      send: vi.fn(async () => undefined),
      refresh: vi.fn(),
    })
    hookMocks.usePlanningConversation.mockReturnValue({
      conversationId: null,
      conversation: null,
      bootstrapStatus: 'loading_snapshot',
      bootstrapError: null,
      refresh: vi.fn(),
    })
    useProjectStore.setState({
      ...useProjectStore.getState(),
      planningHistoryByNode: {
        'child-1': [
          {
            turn_id: 'legacy-turn',
            role: 'assistant',
            content: 'Legacy planning transcript',
            timestamp: '2026-03-16T00:00:00Z',
          },
        ],
      },
    })

    renderWorkspace({ activeTab: 'planning' })

    expect(await screen.findByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.queryByText('Legacy planning transcript')).not.toBeInTheDocument()
  })

  it('writes composerSeed into the keyed execution conversation draft instead of a legacy store', async () => {
    const snapshot = makeSnapshot('Execution v2 transcript', 'execution')
    useConversationStore.getState().ensureConversation(snapshot)
    hookMocks.useExecutionConversation.mockReturnValue({
      conversationId: snapshot.record.conversation_id,
      conversation: makeConversationViewState(snapshot),
      bootstrapStatus: 'idle',
      bootstrapError: null,
      send: vi.fn(async () => undefined),
      continueFromMessage: vi.fn(async () => undefined),
      retryFromMessage: vi.fn(async () => undefined),
      regenerateFromMessage: vi.fn(async () => undefined),
      cancelStream: vi.fn(async () => undefined),
      refresh: vi.fn(),
    })
    hookMocks.useAskConversation.mockReturnValue({
      conversationId: null,
      conversation: null,
      bootstrapStatus: 'idle',
      bootstrapError: null,
      send: vi.fn(async () => undefined),
      refresh: vi.fn(),
    })
    hookMocks.usePlanningConversation.mockReturnValue({
      conversationId: null,
      conversation: null,
      bootstrapStatus: 'idle',
      bootstrapError: null,
      refresh: vi.fn(),
    })

    renderWorkspace({
      activeTab: 'execution',
      locationState: { composerSeed: 'Ship phase 6.3 cleanup' },
    })

    await waitFor(() => {
      expect(
        useConversationStore.getState().conversationsById[snapshot.record.conversation_id]
          ?.composerDraft,
      ).toBe('Ship phase 6.3 cleanup')
    })
  })
})
