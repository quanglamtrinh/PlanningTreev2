import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockUseSessionFacadeV2 = vi.hoisted(() => vi.fn())

vi.mock('../../src/features/session_v2/components/ComposerPane', () => ({
  ComposerPane: ({ disabled }: { disabled?: boolean }) => (
    <div data-testid="composer-pane" data-disabled={String(Boolean(disabled))}>
      Composer
    </div>
  ),
}))

vi.mock('../../src/features/session_v2/components/TranscriptPanel', () => ({
  TranscriptPanel: ({ threadId }: { threadId: string | null }) => (
    <div data-testid="transcript-panel" data-thread-id={threadId ?? ''}>
      Transcript
    </div>
  ),
}))

vi.mock('../../src/features/session_v2/components/RequestUserInputOverlay', () => ({
  RequestUserInputOverlay: () => <div data-testid="request-user-input-overlay">Overlay</div>,
}))

vi.mock('../../src/features/session_v2/components/McpElicitationOverlay', () => ({
  McpElicitationOverlay: () => <div data-testid="mcp-elicitation-overlay">MCP</div>,
}))

vi.mock('../../src/features/session_v2/components/ApprovalOverlay', () => ({
  ApprovalOverlay: () => <div data-testid="approval-overlay">Approval</div>,
}))

vi.mock('../../src/features/node/NodeDetailCard', () => ({
  NodeDetailCard: () => <div data-testid="node-detail-card">detail</div>,
}))

vi.mock('../../src/features/conversation/state/workflowEventBridgeV3', () => ({
  useWorkflowEventBridgeV3: vi.fn(),
}))

vi.mock('../../src/features/session_v2/facade/useSessionFacadeV2', () => ({
  useSessionFacadeV2: mockUseSessionFacadeV2,
}))

import type { NodeWorkflowView, Snapshot } from '../../src/api/types'
import { BreadcrumbChatViewV2 } from '../../src/features/conversation/BreadcrumbChatViewV2'
import type { SessionFacadeV2, SessionFacadeState } from '../../src/features/session_v2/facade/useSessionFacadeV2'
import { useWorkflowStateStoreV3 } from '../../src/features/conversation/state/workflowStateStoreV3'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useProjectStore } from '../../src/stores/project-store'

function makeProjectSnapshot(nodeKind: 'original' | 'review' = 'original'): Snapshot {
  return {
    schema_version: 6,
    project: {
      id: 'project-1',
      name: 'Project',
      root_goal: 'Goal',
      project_path: 'C:/workspace/project-1',
      created_at: '2026-04-01T00:00:00Z',
      updated_at: '2026-04-01T00:00:00Z',
    },
    tree_state: {
      root_node_id: 'root',
      active_node_id: 'root',
      node_registry: [
        {
          node_id: 'root',
          parent_id: null,
          child_ids: [],
          title: 'Root',
          description: 'Root node',
          status: 'draft',
          node_kind: nodeKind,
          depth: 0,
          display_order: 0,
          hierarchical_number: '1',
          created_at: '2026-04-01T00:00:00Z',
          is_superseded: false,
          workflow: {
            frame_confirmed: true,
            active_step: 'spec',
            spec_confirmed: true,
            shaping_frozen: true,
          },
        },
      ],
    },
    updated_at: '2026-04-01T00:00:00Z',
  }
}

function makeWorkflowState(overrides: Partial<NodeWorkflowView> = {}): NodeWorkflowView {
  return {
    nodeId: 'root',
    workflowPhase: 'execution_decision_pending',
    askThreadId: 'ask-thread-1',
    executionThreadId: 'exec-thread-1',
    auditLineageThreadId: 'audit-lineage-1',
    reviewThreadId: null,
    activeExecutionRunId: null,
    latestExecutionRunId: null,
    activeReviewCycleId: null,
    latestReviewCycleId: null,
    currentExecutionDecision: null,
    currentAuditDecision: null,
    acceptedSha: null,
    runtimeBlock: null,
    canSendExecutionMessage: true,
    canReviewInAudit: false,
    canImproveInExecution: false,
    canMarkDoneFromExecution: false,
    canMarkDoneFromAudit: false,
    ...overrides,
  }
}

function seedBaseStores(workflowState: NodeWorkflowView, snapshot: Snapshot) {
  useProjectStore.setState({
    activeProjectId: 'project-1',
    bootstrap: {
      ready: true,
      workspace_configured: true,
      codex_available: true,
      codex_path: 'codex',
      ask_followup_queue_enabled: true,
    },
    snapshot,
    selectedNodeId: 'root',
    isLoadingSnapshot: false,
    error: null,
    loadProject: vi.fn().mockResolvedValue(undefined),
    selectNode: vi.fn().mockResolvedValue(undefined),
  })
  useDetailStateStore.setState({
    entries: {
      'project-1::root': {
        node_id: 'root',
        workflow: null,
        frame_confirmed: true,
        frame_confirmed_revision: 1,
        frame_revision: 1,
        active_step: 'spec',
        workflow_notice: null,
        frame_needs_reconfirm: false,
        frame_read_only: true,
        clarify_read_only: true,
        clarify_confirmed: true,
        spec_read_only: true,
        spec_stale: false,
        spec_confirmed: true,
        shaping_frozen: true,
        can_accept_local_review: false,
        execution_status: 'completed',
        audit_writable: false,
      },
    },
    loadDetailState: vi.fn().mockResolvedValue(undefined),
  } as Partial<ReturnType<typeof useDetailStateStore.getState>>)
  useWorkflowStateStoreV3.setState({
    entries: {
      'project-1::root': workflowState,
    },
    loadWorkflowState: vi.fn().mockResolvedValue(undefined),
    finishTask: vi.fn().mockResolvedValue(undefined),
    markDoneFromExecution: vi.fn().mockResolvedValue(undefined),
    reviewInAudit: vi.fn().mockResolvedValue(undefined),
    markDoneFromAudit: vi.fn().mockResolvedValue(undefined),
    improveInExecution: vi.fn().mockResolvedValue(undefined),
  } as Partial<ReturnType<typeof useWorkflowStateStoreV3.getState>>)
}

function makeFacade(state: Partial<SessionFacadeState>): SessionFacadeV2 {
  return {
    state: {
      connection: {
        phase: 'initialized',
        clientName: 'PlanningTree Session V2',
        serverVersion: '1.0.0',
        error: null,
      },
      threads: [],
      activeThreadId: null,
      activeThread: null,
      activeTurns: [],
      activeItemsByTurn: {},
      activeRunningTurn: null,
      activeRequest: null,
      modelOptions: [],
      selectedModel: null,
      runtimeError: null,
      isBootstrapping: false,
      isSelectingThread: false,
      isActiveThreadReady: false,
      isModelLoading: false,
      queueLength: 0,
      gapDetected: false,
      streamConnected: false,
      reconnectCount: 0,
      threadStatus: null,
      tokenUsage: null,
      lastPollAtMs: null,
      ...state,
    },
    commands: {
      bootstrap: vi.fn().mockResolvedValue(undefined),
      selectThread: vi.fn().mockResolvedValue(undefined),
      createThread: vi.fn().mockResolvedValue(undefined),
      forkThread: vi.fn().mockResolvedValue(undefined),
      refreshThreads: vi.fn().mockResolvedValue(undefined),
      submitSessionAction: vi.fn().mockResolvedValue(undefined),
      setModel: vi.fn(),
      submit: vi.fn().mockResolvedValue(undefined),
      interrupt: vi.fn().mockResolvedValue(undefined),
      resolveRequest: vi.fn().mockResolvedValue(undefined),
      rejectRequest: vi.fn().mockResolvedValue(undefined),
    },
  }
}

describe('BreadcrumbChatViewV2 hard-cutover integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
    useWorkflowStateStoreV3.getState().reset()
    mockUseSessionFacadeV2.mockReturnValue(makeFacade({}))
  })

  it('renders execution lane using facade-native transcript/composer pipeline', async () => {
    seedBaseStores(makeWorkflowState(), makeProjectSnapshot('original'))
    const facade = makeFacade({
      activeThreadId: 'exec-thread-1',
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('transcript-panel')).toHaveAttribute('data-thread-id', 'exec-thread-1')
    })
    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'false')
    expect(facade.commands.selectThread).toHaveBeenCalledWith('exec-thread-1')
  })

  it('renders audit lane with transcript when review thread exists', async () => {
    seedBaseStores(
      makeWorkflowState({
        workflowPhase: 'audit_decision_pending',
        reviewThreadId: 'audit-thread-1',
        canSendExecutionMessage: false,
      }),
      makeProjectSnapshot('original'),
    )
    const facade = makeFacade({
      activeThreadId: 'audit-thread-1',
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=audit']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('transcript-panel')).toHaveAttribute('data-thread-id', 'audit-thread-1')
    })
    expect(facade.commands.selectThread).toHaveBeenCalledWith('audit-thread-1')
  })

  it('clears selection for audit lane when review thread is missing', async () => {
    seedBaseStores(
      makeWorkflowState({
        workflowPhase: 'audit_decision_pending',
        reviewThreadId: null,
        canSendExecutionMessage: false,
      }),
      makeProjectSnapshot('original'),
    )
    const facade = makeFacade({
      activeThreadId: 'stale-thread',
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=audit']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(facade.commands.selectThread).toHaveBeenCalledWith(null)
    })
    expect(screen.getByTestId('transcript-panel')).toHaveAttribute('data-thread-id', '')
    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'true')
  })
})
