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

vi.mock('../../src/features/conversation/components/ConversationFeed', () => ({
  ConversationFeed: ({ prefix, suffix }: { prefix?: React.ReactNode; suffix?: React.ReactNode }) => (
    <div data-testid="conversation-feed">
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

vi.mock('../../src/features/conversation/state/workflowEventBridge', () => ({
  useWorkflowEventBridge: vi.fn(),
}))

import type { NodeWorkflowView, Snapshot, ThreadSnapshotV2 } from '../../src/api/types'
import { BreadcrumbChatViewV2 } from '../../src/features/conversation/BreadcrumbChatViewV2'
import { useThreadByIdStoreV2 } from '../../src/features/conversation/state/threadByIdStoreV2'
import { useWorkflowStateStoreV2 } from '../../src/features/conversation/state/workflowStateStoreV2'
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
  overrides: Partial<ThreadSnapshotV2> = {},
): ThreadSnapshotV2 {
  return {
    projectId: 'project-1',
    nodeId: 'root',
    threadRole: 'execution',
    threadId: 'exec-thread-1',
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-03-28T00:00:00Z',
    updatedAt: '2026-03-28T00:00:00Z',
    lineage: {
      forkedFromThreadId: null,
      forkedFromNodeId: null,
      forkedFromRole: null,
      forkReason: null,
      lineageRootThreadId: 'exec-thread-1',
    },
    items: [],
    pendingRequests: [],
    ...overrides,
  }
}

function makeWorkflowState(overrides: Partial<NodeWorkflowView> = {}): NodeWorkflowView {
  return {
    nodeId: 'root',
    workflowPhase: 'idle',
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

function setBootstrapStatus(enabled: boolean) {
  useProjectStore.setState((state) => ({
    ...state,
    bootstrap: {
      ready: true,
      workspace_configured: true,
      codex_available: true,
      codex_path: 'codex',
      execution_audit_v2_enabled: enabled,
    },
  }))
}

describe('BreadcrumbChatViewV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
    useWorkflowStateStoreV2.getState().reset()
    useThreadByIdStoreV2.getState().disconnectThread()
    setBootstrapStatus(true)
  })

  it('defaults non-review /chat-v2 routes to execution and loads the execution thread by id', async () => {
    const loadProject = vi.fn().mockResolvedValue(undefined)
    const selectNode = vi.fn().mockResolvedValue(undefined)
    const loadDetailState = vi.fn().mockResolvedValue(undefined)
    const loadWorkflowState = vi.fn().mockResolvedValue(
      makeWorkflowState({
        workflowPhase: 'execution_decision_pending',
        canSendExecutionMessage: true,
        canReviewInAudit: true,
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
    )
    const loadThread = vi.fn().mockResolvedValue(undefined)

    useProjectStore.setState({
      activeProjectId: 'project-1',
      snapshot: makeProjectSnapshot('original'),
      selectedNodeId: 'root',
      isLoadingSnapshot: false,
      error: null,
      loadProject,
      selectNode,
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
      loadDetailState,
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)
    useWorkflowStateStoreV2.setState({
      entries: {
        'project-1::root': makeWorkflowState({
          workflowPhase: 'execution_decision_pending',
          canSendExecutionMessage: true,
          canReviewInAudit: true,
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
      },
      loadWorkflowState,
      finishTask: vi.fn().mockResolvedValue(undefined),
      markDoneFromExecution: vi.fn().mockResolvedValue(undefined),
      reviewInAudit: vi.fn().mockResolvedValue(undefined),
      markDoneFromAudit: vi.fn().mockResolvedValue(undefined),
      improveInExecution: vi.fn().mockResolvedValue(undefined),
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)
    useThreadByIdStoreV2.setState({
      snapshot: makeConversationSnapshot(),
      loadThread,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV2.getState>>)

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

    expect(screen.getByTestId('breadcrumb-detail-pane')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/projects/project-1/nodes/root/chat-v2?thread=execution')
    })
    expect(screen.queryByTestId('workflow-finish-task')).not.toBeInTheDocument()
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'false')
    expect(screen.getByTestId('workflow-review-in-audit')).toBeInTheDocument()
    expect(screen.getByTestId('workflow-mark-done-execution')).toBeInTheDocument()
    expect(loadThread).toHaveBeenCalledWith('project-1', 'root', 'exec-thread-1', 'execution')
  })

  it('renders an audit metadata shell until the review thread exists', async () => {
    useProjectStore.setState({
      activeProjectId: 'project-1',
      snapshot: makeProjectSnapshot('original'),
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
    useWorkflowStateStoreV2.setState({
      entries: {
        'project-1::root': makeWorkflowState({
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
      },
      loadWorkflowState: vi.fn().mockResolvedValue(undefined),
      finishTask: vi.fn().mockResolvedValue(undefined),
      markDoneFromExecution: vi.fn().mockResolvedValue(undefined),
      reviewInAudit: vi.fn().mockResolvedValue(undefined),
      markDoneFromAudit: vi.fn().mockResolvedValue(undefined),
      improveInExecution: vi.fn().mockResolvedValue(undefined),
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)
    useThreadByIdStoreV2.setState({
      snapshot: null,
      loadThread: vi.fn().mockResolvedValue(undefined),
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV2.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=audit']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('audit-shell')).toBeInTheDocument()
    expect(screen.getByTestId('frame-context-audit')).toBeInTheDocument()
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'true')
    expect(screen.queryByTestId('conversation-feed')).not.toBeInTheDocument()
  })

  it('uses workflow-state actions and navigates from execution to audit review', async () => {
    const reviewInAudit = vi.fn().mockResolvedValue(undefined)

    useProjectStore.setState({
      activeProjectId: 'project-1',
      snapshot: makeProjectSnapshot('original'),
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
    useWorkflowStateStoreV2.setState({
      entries: {
        'project-1::root': makeWorkflowState({
          workflowPhase: 'execution_decision_pending',
          canSendExecutionMessage: true,
          canReviewInAudit: true,
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
      },
      loadWorkflowState: vi.fn().mockResolvedValue(undefined),
      finishTask: vi.fn().mockResolvedValue(undefined),
      markDoneFromExecution: vi.fn().mockResolvedValue(undefined),
      reviewInAudit,
      markDoneFromAudit: vi.fn().mockResolvedValue(undefined),
      improveInExecution: vi.fn().mockResolvedValue(undefined),
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)
    useThreadByIdStoreV2.setState({
      snapshot: makeConversationSnapshot(),
      loadThread: vi.fn().mockResolvedValue(undefined),
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV2.getState>>)

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
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/projects/project-1/nodes/root/chat-v2?thread=audit')
    })
  })

  it('redirects review-node /chat-v2 routes back to legacy audit', async () => {
    useProjectStore.setState({
      activeProjectId: 'project-1',
      snapshot: makeProjectSnapshot('review'),
      selectedNodeId: 'root',
      isLoadingSnapshot: false,
      error: null,
      loadProject: vi.fn().mockResolvedValue(undefined),
      selectNode: vi.fn().mockResolvedValue(undefined),
    })
    useDetailStateStore.setState({
      entries: {},
      loadDetailState: vi.fn().mockResolvedValue(undefined),
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<LocationProbe />} />
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/projects/project-1/nodes/root/chat?thread=audit')
    })
  })

  it('redirects /chat-v2 ask requests back to legacy /chat ask', async () => {
    useProjectStore.setState({
      activeProjectId: 'project-1',
      snapshot: makeProjectSnapshot('original'),
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
          active_step: 'frame',
          workflow_notice: null,
          frame_needs_reconfirm: false,
          frame_read_only: false,
          clarify_read_only: true,
          clarify_confirmed: false,
          spec_read_only: true,
          spec_stale: false,
          spec_confirmed: false,
          shaping_frozen: false,
          can_accept_local_review: false,
          execution_status: null,
          audit_writable: false,
        },
      },
      loadDetailState: vi.fn().mockResolvedValue(undefined),
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<LocationProbe />} />
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/projects/project-1/nodes/root/chat?thread=ask')
    })
  })

  it('does not redirect to legacy while bootstrap is unresolved', async () => {
    useProjectStore.setState({
      bootstrap: null,
      activeProjectId: 'project-1',
      snapshot: makeProjectSnapshot('original'),
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
    useWorkflowStateStoreV2.setState({
      entries: {
        'project-1::root': makeWorkflowState(),
      },
      loadWorkflowState: vi.fn().mockResolvedValue(undefined),
      finishTask: vi.fn().mockResolvedValue(undefined),
      markDoneFromExecution: vi.fn().mockResolvedValue(undefined),
      reviewInAudit: vi.fn().mockResolvedValue(undefined),
      markDoneFromAudit: vi.fn().mockResolvedValue(undefined),
      improveInExecution: vi.fn().mockResolvedValue(undefined),
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)
    useThreadByIdStoreV2.setState({
      snapshot: makeConversationSnapshot(),
      loadThread: vi.fn().mockResolvedValue(undefined),
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV2.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<LocationProbe />} />
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
  })

  it('falls back to legacy execution when the V2 surface flag is disabled', async () => {
    setBootstrapStatus(false)
    useProjectStore.setState({
      activeProjectId: 'project-1',
      snapshot: makeProjectSnapshot('original'),
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

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<LocationProbe />} />
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/projects/project-1/nodes/root/chat?thread=execution')
    })
  })
})
