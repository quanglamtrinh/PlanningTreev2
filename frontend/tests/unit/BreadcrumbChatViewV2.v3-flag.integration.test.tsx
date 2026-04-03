import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/features/breadcrumb/ComposerBar', () => ({
  ComposerBar: ({ disabled }: { disabled: boolean }) => (
    <div data-testid="composer" data-disabled={String(disabled)}>
      Composer
    </div>
  ),
}))

vi.mock('../../src/features/conversation/components/ConversationFeed', () => ({
  ConversationFeed: () => <div data-testid="conversation-feed-v2">V2 Feed</div>,
}))

vi.mock('../../src/features/conversation/components/v3/MessagesV3', () => ({
  MessagesV3: () => <div data-testid="messages-v3">V3 Feed</div>,
}))

vi.mock('../../src/features/breadcrumb/FrameContextFeedBlock', () => ({
  FrameContextFeedBlock: () => <div data-testid="frame-context">context</div>,
}))

vi.mock('../../src/features/node/NodeDetailCard', () => ({
  NodeDetailCard: () => <div data-testid="node-detail-card">detail</div>,
}))

vi.mock('../../src/features/conversation/state/workflowEventBridge', () => ({
  useWorkflowEventBridge: vi.fn(),
}))

import type { NodeWorkflowView, Snapshot, ThreadSnapshotV2, ThreadSnapshotV3 } from '../../src/api/types'
import { BreadcrumbChatViewV2 } from '../../src/features/conversation/BreadcrumbChatViewV2'
import { useThreadByIdStoreV2 } from '../../src/features/conversation/state/threadByIdStoreV2'
import { useThreadByIdStoreV3 } from '../../src/features/conversation/state/threadByIdStoreV3'
import { useWorkflowStateStoreV2 } from '../../src/features/conversation/state/workflowStateStoreV2'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useProjectStore } from '../../src/stores/project-store'

function makeProjectSnapshot(): Snapshot {
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
          node_kind: 'original',
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

function makeConversationSnapshotV2(
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
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:00Z',
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

function makeConversationSnapshotV3(
  overrides: Partial<ThreadSnapshotV3> = {},
): ThreadSnapshotV3 {
  return {
    projectId: 'project-1',
    nodeId: 'root',
    threadId: 'exec-thread-1',
    lane: 'execution',
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:00Z',
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

function makeWorkflowState(): NodeWorkflowView {
  return {
    nodeId: 'root',
    workflowPhase: 'execution_decision_pending',
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
  }
}

function seedBaseStores(options: {
  sharedFrontendFlag: boolean
  executionLaneFlag?: boolean
  auditLaneFlag?: boolean
}) {
  const { sharedFrontendFlag, executionLaneFlag, auditLaneFlag } = options
  useProjectStore.setState({
    activeProjectId: 'project-1',
    bootstrap: {
      ready: true,
      workspace_configured: true,
      codex_available: true,
      codex_path: 'codex',
      execution_audit_v2_enabled: true,
      execution_audit_uiux_v3_frontend_enabled: sharedFrontendFlag,
      execution_uiux_v3_frontend_enabled: executionLaneFlag,
      audit_uiux_v3_frontend_enabled: auditLaneFlag,
    },
    snapshot: makeProjectSnapshot(),
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
}

describe('BreadcrumbChatViewV2 v3 flag integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
    useWorkflowStateStoreV2.getState().reset()
    useThreadByIdStoreV2.getState().disconnectThread()
    useThreadByIdStoreV3.getState().disconnectThread()
  })

  it('uses V3 pipeline when frontend flag is enabled', async () => {
    seedBaseStores({ sharedFrontendFlag: true })
    const loadThreadV2 = vi.fn().mockResolvedValue(undefined)
    const loadThreadV3 = vi.fn().mockResolvedValue(undefined)

    useThreadByIdStoreV2.setState({
      snapshot: makeConversationSnapshotV2(),
      loadThread: loadThreadV2,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV2.getState>>)
    useThreadByIdStoreV3.setState({
      snapshot: makeConversationSnapshotV3(),
      loadThread: loadThreadV3,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV3.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('messages-v3')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('conversation-feed-v2')).not.toBeInTheDocument()
    expect(loadThreadV3).toHaveBeenCalledWith('project-1', 'root', 'exec-thread-1', 'execution')
    expect(loadThreadV2).not.toHaveBeenCalled()
  })

  it('falls back to V2 pipeline when frontend flag is disabled', async () => {
    seedBaseStores({ sharedFrontendFlag: false })
    const loadThreadV2 = vi.fn().mockResolvedValue(undefined)
    const loadThreadV3 = vi.fn().mockResolvedValue(undefined)

    useThreadByIdStoreV2.setState({
      snapshot: makeConversationSnapshotV2(),
      loadThread: loadThreadV2,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV2.getState>>)
    useThreadByIdStoreV3.setState({
      snapshot: makeConversationSnapshotV3(),
      loadThread: loadThreadV3,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV3.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('conversation-feed-v2')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('messages-v3')).not.toBeInTheDocument()
    expect(loadThreadV2).toHaveBeenCalledWith('project-1', 'root', 'exec-thread-1', 'execution')
    expect(loadThreadV3).not.toHaveBeenCalled()
  })

  it('routes execution to V3 and audit to V2 with lane-scoped split flags', async () => {
    seedBaseStores({
      sharedFrontendFlag: false,
      executionLaneFlag: true,
      auditLaneFlag: false,
    })
    const loadThreadV2 = vi.fn().mockResolvedValue(undefined)
    const loadThreadV3 = vi.fn().mockResolvedValue(undefined)

    useThreadByIdStoreV2.setState({
      snapshot: makeConversationSnapshotV2(),
      loadThread: loadThreadV2,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV2.getState>>)
    useThreadByIdStoreV3.setState({
      snapshot: makeConversationSnapshotV3(),
      loadThread: loadThreadV3,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV3.getState>>)

    const executionRender = render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('messages-v3')).toBeInTheDocument()
    })
    expect(loadThreadV3).toHaveBeenCalledWith('project-1', 'root', 'exec-thread-1', 'execution')

    executionRender.unmount()
    useWorkflowStateStoreV2.setState({
      entries: {
        'project-1::root': {
          ...makeWorkflowState(),
          reviewThreadId: 'audit-thread-1',
        },
      },
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=audit']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('conversation-feed-v2')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('messages-v3')).not.toBeInTheDocument()
    expect(loadThreadV2).toHaveBeenCalledWith('project-1', 'root', 'audit-thread-1', 'audit')
  })

  it('routes audit to V3 when audit lane flag is enabled', async () => {
    seedBaseStores({
      sharedFrontendFlag: false,
      executionLaneFlag: false,
      auditLaneFlag: true,
    })
    const loadThreadV2 = vi.fn().mockResolvedValue(undefined)
    const loadThreadV3 = vi.fn().mockResolvedValue(undefined)

    useThreadByIdStoreV2.setState({
      snapshot: makeConversationSnapshotV2({ threadRole: 'audit' }),
      loadThread: loadThreadV2,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV2.getState>>)
    useThreadByIdStoreV3.setState({
      snapshot: makeConversationSnapshotV3({ lane: 'audit' }),
      loadThread: loadThreadV3,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useThreadByIdStoreV3.getState>>)
    useWorkflowStateStoreV2.setState({
      entries: {
        'project-1::root': {
          ...makeWorkflowState(),
          reviewThreadId: 'audit-thread-1',
        },
      },
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=audit']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('messages-v3')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('conversation-feed-v2')).not.toBeInTheDocument()
    expect(loadThreadV3).toHaveBeenCalledWith('project-1', 'root', 'audit-thread-1', 'audit')
  })
})
