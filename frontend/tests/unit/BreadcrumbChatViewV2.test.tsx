import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/features/breadcrumb/ComposerBar', () => ({
  ComposerBar: ({ disabled }: { disabled: boolean }) => (
    <div data-testid="composer" data-disabled={String(disabled)}>
      Composer
    </div>
  ),
}))

vi.mock('../../src/features/conversation/components/v3/MessagesV3', () => ({
  MessagesV3: ({ prefix, suffix }: { prefix?: React.ReactNode; suffix?: React.ReactNode }) => (
    <div data-testid="messages-v3">
      {prefix ? <div data-testid="conversation-prefix">{prefix}</div> : null}
      feed
      {suffix ? <div data-testid="conversation-suffix">{suffix}</div> : null}
    </div>
  ),
}))

vi.mock('../../src/features/breadcrumb/FrameContextFeedBlock', () => ({
  FrameContextFeedBlock: ({ variant }: { variant: 'ask' | 'audit' }) => (
    <div data-testid={`frame-context-${variant}`}>context {variant}</div>
  ),
}))

vi.mock('../../src/features/node/NodeDetailCard', () => ({
  NodeDetailCard: ({ message }: { message?: string | null }) => (
    <div data-testid="node-detail-card">{message ?? 'detail card'}</div>
  ),
}))

vi.mock('../../src/features/conversation/state/workflowEventBridgeV3', () => ({
  useWorkflowEventBridgeV3: vi.fn(),
}))

import type { NodeWorkflowView, Snapshot, ThreadSnapshotV3 } from '../../src/api/types'
import { BreadcrumbChatViewV2 } from '../../src/features/conversation/BreadcrumbChatViewV2'
import { useThreadByIdStoreV3 } from '../../src/features/conversation/state/threadByIdStoreV3'
import { useWorkflowStateStoreV3 } from '../../src/features/conversation/state/workflowStateStoreV3'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useProjectStore } from '../../src/stores/project-store'
import { useUIStore } from '../../src/stores/ui-store'

function makeProjectSnapshot(nodeKind: 'original' | 'review' = 'original'): Snapshot {
  return {
    schema_version: 6,
    project: {
      id: 'project-1',
      name: 'Project',
      root_goal: 'Goal',
      project_path: 'C:/workspace/project-1',
      created_at: '2026-03-28T00:00:00Z',
      updated_at: '2026-03-28T00:00:00Z',
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
          created_at: '2026-03-28T00:00:00Z',
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
    updated_at: '2026-03-28T00:00:00Z',
  }
}

function makeConversationSnapshot(
  overrides: Partial<ThreadSnapshotV3> = {},
): ThreadSnapshotV3 {
  return {
    projectId: 'project-1',
    nodeId: 'root',
    threadId: 'exec-thread-1',
    threadRole: 'execution',
    lane: 'execution',
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-03-28T00:00:00Z',
    updatedAt: '2026-03-28T00:00:00Z',
    items: [],
    uiSignals: {
      planReady: {
        planItemId: null,
        revision: null,
        ready: false,
        failed: false,
      },
      activeUserInputRequests: [],
    },
    ...overrides,
  }
}

function makeWorkflowState(overrides: Partial<NodeWorkflowView> = {}): NodeWorkflowView {
  return {
    nodeId: 'root',
    workflowPhase: 'idle',
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
    canSendExecutionMessage: false,
    canReviewInAudit: false,
    canImproveInExecution: false,
    canMarkDoneFromExecution: false,
    canMarkDoneFromAudit: false,
    ...overrides,
  }
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-probe">{`${location.pathname}${location.search}`}</div>
}

function seedStores(options: {
  nodeKind?: 'original' | 'review'
  workflowState?: NodeWorkflowView
  threadSnapshot?: ThreadSnapshotV3 | null
}) {
  const { nodeKind = 'original', workflowState = makeWorkflowState(), threadSnapshot = makeConversationSnapshot() } =
    options

  useProjectStore.setState({
    activeProjectId: 'project-1',
    bootstrap: {
      ready: true,
      workspace_configured: true,
      codex_available: true,
      codex_path: 'codex',
    },
    snapshot: makeProjectSnapshot(nodeKind),
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
    entries: { 'project-1::root': workflowState },
    loadWorkflowState: vi.fn().mockResolvedValue(undefined),
    finishTask: vi.fn().mockResolvedValue(undefined),
    markDoneFromExecution: vi.fn().mockResolvedValue(undefined),
    reviewInAudit: vi.fn().mockResolvedValue(undefined),
    markDoneFromAudit: vi.fn().mockResolvedValue(undefined),
    improveInExecution: vi.fn().mockResolvedValue(undefined),
  } as Partial<ReturnType<typeof useWorkflowStateStoreV3.getState>>)
  useThreadByIdStoreV3.setState({
    snapshot: threadSnapshot,
    loadThread: vi.fn().mockResolvedValue(undefined),
    sendTurn: vi.fn().mockResolvedValue(undefined),
    resolveUserInput: vi.fn().mockResolvedValue(undefined),
    runPlanAction: vi.fn().mockResolvedValue(undefined),
    recordRenderError: vi.fn(),
    disconnectThread: vi.fn(),
  } as Partial<ReturnType<typeof useThreadByIdStoreV3.getState>>)
}

describe('BreadcrumbChatViewV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
    useWorkflowStateStoreV3.getState().reset()
    useThreadByIdStoreV3.getState().disconnectThread()
    useUIStore.setState(useUIStore.getInitialState())
  })

  it('defaults non-review /chat-v2 routes to execution and loads execution thread by id', async () => {
    const loadThread = vi.fn().mockResolvedValue(undefined)
    seedStores({
      workflowState: makeWorkflowState({
        workflowPhase: 'execution_decision_pending',
        canSendExecutionMessage: true,
      }),
    })
    useThreadByIdStoreV3.setState({
      ...useThreadByIdStoreV3.getState(),
      loadThread,
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2']}>
        <Routes>
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={
              <>
                <BreadcrumbChatViewV2 />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent(
        '/projects/project-1/nodes/root/chat-v2?thread=execution',
      )
    })
    expect(screen.getByTestId('breadcrumb-thread-body')).toBeInTheDocument()
    expect(screen.getByTestId('breadcrumb-thread-composer')).toBeInTheDocument()
    expect(screen.getByTestId('messages-v3')).toBeInTheDocument()
    expect(loadThread).toHaveBeenCalledWith('project-1', 'root', 'exec-thread-1', 'execution')
  })

  it('renders audit shell until review thread exists', () => {
    seedStores({
      workflowState: makeWorkflowState({
        workflowPhase: 'execution_decision_pending',
        reviewThreadId: null,
      }),
      threadSnapshot: null,
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=audit']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('audit-shell')).toBeInTheDocument()
    expect(screen.getByTestId('frame-context-audit')).toBeInTheDocument()
    expect(screen.queryByTestId('messages-v3')).not.toBeInTheDocument()
  })

  it('uses workflow-state actions and navigates from execution to audit review', async () => {
    const reviewInAudit = vi.fn().mockResolvedValue(undefined)
    seedStores({
      workflowState: makeWorkflowState({
        workflowPhase: 'execution_decision_pending',
        canReviewInAudit: true,
        currentExecutionDecision: {
          status: 'current',
          sourceExecutionRunId: 'exec-run-1',
          executionTurnId: 'turn-1',
          candidateWorkspaceHash: 'ws:abc',
          summaryText: 'Execution summary',
          createdAt: '2026-03-28T00:01:00Z',
        },
      }),
    })
    useWorkflowStateStoreV3.setState({
      ...useWorkflowStateStoreV3.getState(),
      reviewInAudit,
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={
              <>
                <BreadcrumbChatViewV2 />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByTestId('workflow-review-in-audit'))

    await waitFor(() => {
      expect(reviewInAudit).toHaveBeenCalledWith('project-1', 'root', 'ws:abc')
    })
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent(
        '/projects/project-1/nodes/root/chat-v2?thread=audit',
      )
    })
  })

  it('keeps ask lane on /chat-v2 and loads ask thread by id', async () => {
    const loadThread = vi.fn().mockResolvedValue(undefined)
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
      threadSnapshot: makeConversationSnapshot({ threadId: 'ask-thread-1', threadRole: 'ask_planning', lane: 'ask' }),
    })
    useThreadByIdStoreV3.setState({
      ...useThreadByIdStoreV3.getState(),
      loadThread,
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={
              <>
                <BreadcrumbChatViewV2 />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/projects/project-1/nodes/root/chat-v2?thread=ask')
    })
    expect(loadThread).toHaveBeenCalledWith('project-1', 'root', 'ask-thread-1', 'ask_planning')
    expect(screen.getByTestId('frame-context-ask')).toBeInTheDocument()
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'false')
  })

  it('keeps ask metadata shell visible when ask transcript is empty', async () => {
    const loadThread = vi.fn().mockResolvedValue(undefined)
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
      threadSnapshot: null,
    })
    useThreadByIdStoreV3.setState({
      ...useThreadByIdStoreV3.getState(),
      loadThread,
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={
              <>
                <BreadcrumbChatViewV2 />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(loadThread).toHaveBeenCalledWith('project-1', 'root', 'ask-thread-1', 'ask_planning')
    })
    expect(screen.getByTestId('frame-context-ask')).toBeInTheDocument()
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'true')
  })

  it('marks done from execution and returns to graph immediately', async () => {
    const markDoneFromExecution = vi.fn().mockResolvedValue(undefined)
    seedStores({
      workflowState: makeWorkflowState({
        workflowPhase: 'execution_decision_pending',
        canMarkDoneFromExecution: true,
        currentExecutionDecision: {
          status: 'current',
          sourceExecutionRunId: 'exec-run-1',
          executionTurnId: 'turn-1',
          candidateWorkspaceHash: 'ws:abc',
          summaryText: 'Execution summary',
          createdAt: '2026-03-28T00:01:00Z',
        },
      }),
    })
    useWorkflowStateStoreV3.setState({
      ...useWorkflowStateStoreV3.getState(),
      markDoneFromExecution,
    })
    useUIStore.setState({ ...useUIStore.getState(), activeSurface: 'breadcrumb' })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/" element={<LocationProbe />} />
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={
              <>
                <BreadcrumbChatViewV2 />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByTestId('workflow-mark-done-execution'))

    await waitFor(() => {
      expect(markDoneFromExecution).toHaveBeenCalledWith('project-1', 'root', 'ws:abc')
    })
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/')
    })
    expect(useUIStore.getState().activeSurface).toBe('graph')
  })

  it('marks done from audit and returns to graph immediately', async () => {
    const markDoneFromAudit = vi.fn().mockResolvedValue(undefined)
    seedStores({
      workflowState: makeWorkflowState({
        workflowPhase: 'audit_decision_pending',
        canMarkDoneFromAudit: true,
        reviewThreadId: 'audit-thread-1',
        currentAuditDecision: {
          status: 'current',
          sourceReviewCycleId: 'review-cycle-1',
          reviewCommitSha: 'sha:abc',
          finalReviewText: 'Audit summary',
          reviewDisposition: 'approve',
          createdAt: '2026-03-28T00:02:00Z',
        },
      }),
      threadSnapshot: makeConversationSnapshot({ threadId: 'audit-thread-1', threadRole: 'audit', lane: 'audit' }),
    })
    useWorkflowStateStoreV3.setState({
      ...useWorkflowStateStoreV3.getState(),
      markDoneFromAudit,
    })
    useUIStore.setState({ ...useUIStore.getState(), activeSurface: 'breadcrumb' })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=audit']}>
        <Routes>
          <Route path="/" element={<LocationProbe />} />
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={
              <>
                <BreadcrumbChatViewV2 />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByTestId('workflow-mark-done-audit'))

    await waitFor(() => {
      expect(markDoneFromAudit).toHaveBeenCalledWith('project-1', 'root', 'sha:abc')
    })
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/')
    })
    expect(useUIStore.getState().activeSurface).toBe('graph')
  })

  it('keeps review-node routes inside chat-v2 audit lane', async () => {
    seedStores({
      nodeKind: 'review',
      workflowState: makeWorkflowState({
        reviewThreadId: 'audit-thread-1',
      }),
      threadSnapshot: makeConversationSnapshot({ threadId: 'audit-thread-1', threadRole: 'audit', lane: 'audit' }),
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2']}>
        <Routes>
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={
              <>
                <BreadcrumbChatViewV2 />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent(
        '/projects/project-1/nodes/root/chat-v2?thread=audit',
      )
    })
  })
})
