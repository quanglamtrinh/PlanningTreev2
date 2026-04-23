import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/features/session_v2/components/ComposerPane', () => ({
  ComposerPane: ({
    disabled,
    onSubmit,
  }: {
    disabled?: boolean
    onSubmit: (payload: {
      input: Array<Record<string, unknown>>
      text: string
      accessMode: 'full-access' | 'default-permissions'
    }) => Promise<void>
  }) => (
    <div data-testid="composer-pane" data-disabled={String(Boolean(disabled))}>
      <button
        type="button"
        data-testid="composer-submit-mock"
        disabled={Boolean(disabled)}
        onClick={() =>
          void onSubmit({
            input: [{ type: 'text', text: 'queued from composer mock' }],
            text: 'queued from composer mock',
            accessMode: 'full-access',
          })
        }
      >
        Send
      </button>
    </div>
  ),
}))

vi.mock('../../src/features/session_v2/components/TranscriptPanel', () => ({
  TranscriptPanel: ({ threadId }: { threadId: string | null }) => (
    <div data-testid="transcript-panel" data-thread-id={threadId ?? ''}>
      transcript
    </div>
  ),
}))

vi.mock('../../src/features/session_v2/components/RequestUserInputOverlay', () => ({
  RequestUserInputOverlay: ({
    request,
    onResolve,
    onReject,
  }: {
    request: { requestId: string }
    onResolve: (result: Record<string, unknown>) => Promise<void>
    onReject: (reason?: string | null) => Promise<void>
  }) => (
    <div data-testid="request-user-input-overlay" data-request-id={request.requestId}>
      <button
        type="button"
        data-testid="overlay-submit"
        onClick={() =>
          void onResolve({
            answers: [{ id: 'q-1', selectedOption: 'Option A', notes: '', status: 'answered' }],
          })
        }
      >
        Submit
      </button>
      <button
        type="button"
        data-testid="overlay-cancel"
        onClick={() => void onReject('cancel')}
      >
        Cancel
      </button>
    </div>
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
  const {
    nodeKind = 'original',
    workflowState = makeWorkflowState(),
    threadSnapshot = makeConversationSnapshot(),
  } = options

  useProjectStore.setState({
    activeProjectId: 'project-1',
    bootstrap: {
      ready: true,
      workspace_configured: true,
      codex_available: true,
      codex_path: 'codex',
      ask_followup_queue_enabled: true,
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
    askFollowupQueueEnabled: true,
    loadThread: vi.fn().mockResolvedValue(undefined),
    sendTurn: vi.fn().mockResolvedValue(undefined),
    resolveUserInput: vi.fn().mockResolvedValue(undefined),
    runPlanAction: vi.fn().mockResolvedValue(undefined),
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

  it('defaults non-review /chat-v2 route to execution and loads execution thread by id', async () => {
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
    expect(screen.getByTestId('transcript-panel')).toBeInTheDocument()
    expect(screen.getByTestId('composer-pane')).toBeInTheDocument()
    expect(loadThread).toHaveBeenCalledWith('project-1', 'root', 'exec-thread-1', 'execution')
  })

  it('keeps ask lane on /chat-v2 and loads ask thread by id', async () => {
    const loadThread = vi.fn().mockResolvedValue(undefined)
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
      threadSnapshot: makeConversationSnapshot({ threadId: 'ask-thread-1', threadRole: 'ask_planning' }),
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
      expect(screen.getByTestId('location-probe')).toHaveTextContent(
        '/projects/project-1/nodes/root/chat-v2?thread=ask',
      )
    })
    expect(loadThread).toHaveBeenCalledWith('project-1', 'root', 'ask-thread-1', 'ask_planning')
    expect(screen.getByTestId('transcript-panel')).toHaveAttribute('data-thread-id', 'ask-thread-1')
  })

  it('routes execution submit directly through sendTurn', async () => {
    const enqueueFollowup = vi.fn().mockResolvedValue(undefined)
    const sendTurn = vi.fn().mockResolvedValue(undefined)

    seedStores({
      workflowState: makeWorkflowState({
        workflowPhase: 'execution_decision_pending',
        canSendExecutionMessage: true,
      }),
    })
    useThreadByIdStoreV3.setState({
      ...useThreadByIdStoreV3.getState(),
      enqueueFollowup,
      sendTurn,
      activeThreadRole: 'execution',
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByTestId('composer-submit-mock'))

    await waitFor(() => {
      expect(sendTurn).toHaveBeenCalledWith('queued from composer mock')
    })
    expect(enqueueFollowup).not.toHaveBeenCalled()
    expect(screen.queryByTestId('execution-followup-queue-panel')).not.toBeInTheDocument()
    expect(screen.queryByTestId('ask-followup-queue-panel')).not.toBeInTheDocument()
  })

  it('renders workflow actions in strip and runs review-in-audit action', async () => {
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

    expect(screen.getByTestId('workflow-action-strip')).toBeInTheDocument()
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

  it('uses transcript native empty state path for audit lane without review thread', async () => {
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

    expect(screen.getByTestId('transcript-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('audit-shell')).not.toBeInTheDocument()
  })

  it('renders pending request overlay and resolves user input with mapped answers', async () => {
    const resolveUserInput = vi.fn().mockResolvedValue(undefined)
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
      threadSnapshot: makeConversationSnapshot({
        threadId: 'ask-thread-1',
        threadRole: 'ask_planning',
        items: [
          {
            id: 'item-user-input-1',
            kind: 'userInput',
            threadId: 'ask-thread-1',
            turnId: 'turn-1',
            sequence: 1,
            createdAt: '2026-03-28T00:00:01Z',
            updatedAt: '2026-03-28T00:00:01Z',
            status: 'requested',
            source: 'upstream',
            tone: 'neutral',
            metadata: {},
            requestId: 'req-1',
            title: 'Need confirmation',
            questions: [
              {
                id: 'q-1',
                header: 'Decision',
                prompt: 'Choose an option',
                inputType: 'single_select',
                options: [{ label: 'Option A', description: 'Recommended' }],
              },
            ],
            answers: [],
            requestedAt: '2026-03-28T00:00:01Z',
            resolvedAt: null,
          },
        ],
        uiSignals: {
          planReady: {
            planItemId: null,
            revision: null,
            ready: false,
            failed: false,
          },
          activeUserInputRequests: [
            {
              requestId: 'req-1',
              itemId: 'item-user-input-1',
              threadId: 'ask-thread-1',
              turnId: 'turn-1',
              status: 'requested',
              createdAt: '2026-03-28T00:00:01Z',
              submittedAt: null,
              resolvedAt: null,
              answers: [],
            },
          ],
        },
      }),
    })
    useThreadByIdStoreV3.setState({
      ...useThreadByIdStoreV3.getState(),
      resolveUserInput,
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('request-user-input-overlay')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('overlay-submit'))

    await waitFor(() => {
      expect(resolveUserInput).toHaveBeenCalledWith('req-1', [
        {
          questionId: 'q-1',
          value: 'Option A',
          label: 'Option A',
        },
      ])
    })
  })

  it('rejects pending user input by resolving with empty answers', async () => {
    const resolveUserInput = vi.fn().mockResolvedValue(undefined)
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
      threadSnapshot: makeConversationSnapshot({
        threadId: 'ask-thread-1',
        threadRole: 'ask_planning',
        items: [
          {
            id: 'item-user-input-1',
            kind: 'userInput',
            threadId: 'ask-thread-1',
            turnId: 'turn-1',
            sequence: 1,
            createdAt: '2026-03-28T00:00:01Z',
            updatedAt: '2026-03-28T00:00:01Z',
            status: 'requested',
            source: 'upstream',
            tone: 'neutral',
            metadata: {},
            requestId: 'req-1',
            title: 'Need confirmation',
            questions: [],
            answers: [],
            requestedAt: '2026-03-28T00:00:01Z',
            resolvedAt: null,
          },
        ],
        uiSignals: {
          planReady: {
            planItemId: null,
            revision: null,
            ready: false,
            failed: false,
          },
          activeUserInputRequests: [
            {
              requestId: 'req-1',
              itemId: 'item-user-input-1',
              threadId: 'ask-thread-1',
              turnId: 'turn-1',
              status: 'requested',
              createdAt: '2026-03-28T00:00:01Z',
              submittedAt: null,
              resolvedAt: null,
              answers: [],
            },
          ],
        },
      }),
    })
    useThreadByIdStoreV3.setState({
      ...useThreadByIdStoreV3.getState(),
      resolveUserInput,
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByTestId('overlay-cancel'))

    await waitFor(() => {
      expect(resolveUserInput).toHaveBeenCalledWith('req-1', [])
    })
  })
})
