import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockUseSessionFacadeV2 = vi.hoisted(() => vi.fn())

vi.mock('../../src/features/session_v2/components/ComposerPane', () => ({
  ComposerPane: ({
    disabled,
    onSubmit,
    onInterrupt,
  }: {
    disabled?: boolean
    onSubmit: (payload: {
      input: Array<Record<string, unknown>>
      text: string
      accessMode: 'full-access' | 'default-permissions'
    }) => Promise<void>
    onInterrupt: () => Promise<void>
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
      <button
        type="button"
        data-testid="composer-interrupt-mock"
        onClick={() => void onInterrupt()}
      >
        Interrupt
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

vi.mock('../../src/features/session_v2/components/McpElicitationOverlay', () => ({
  McpElicitationOverlay: ({
    request,
    onResolve,
  }: {
    request: { requestId: string }
    onResolve: (result: Record<string, unknown>) => Promise<void>
  }) => (
    <div data-testid="mcp-elicitation-overlay" data-request-id={request.requestId}>
      <button
        type="button"
        data-testid="mcp-overlay-submit"
        onClick={() => void onResolve({ response: { name: 'value' } })}
      >
        Submit
      </button>
    </div>
  ),
}))

vi.mock('../../src/features/session_v2/components/ApprovalOverlay', () => ({
  ApprovalOverlay: ({
    request,
    onResolve,
  }: {
    request: { requestId: string }
    onResolve: (result: Record<string, unknown>) => Promise<void>
  }) => (
    <div data-testid="approval-overlay" data-request-id={request.requestId}>
      <button
        type="button"
        data-testid="approval-overlay-accept"
        onClick={() => void onResolve({ decision: 'accept' })}
      >
        Accept
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

vi.mock('../../src/features/session_v2/facade/useSessionFacadeV2', () => ({
  useSessionFacadeV2: mockUseSessionFacadeV2,
}))

import type { NodeWorkflowView, Snapshot } from '../../src/api/types'
import { BreadcrumbChatViewV2 } from '../../src/features/conversation/BreadcrumbChatViewV2'
import type { PendingServerRequest, SessionThread, SessionTurn } from '../../src/features/session_v2/contracts'
import type { SessionFacadeV2 } from '../../src/features/session_v2/facade/useSessionFacadeV2'
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

function makeThread(id: string): SessionThread {
  return {
    id,
    name: id,
    modelProvider: 'openai',
    cwd: 'C:/workspace/project-1',
    ephemeral: false,
    archived: false,
    status: { type: 'idle' },
    createdAt: 1,
    updatedAt: 1,
    turns: [],
    model: 'gpt-5',
  }
}

function makePendingRequest(partial: Partial<PendingServerRequest>): PendingServerRequest {
  return {
    requestId: partial.requestId ?? 'req-1',
    method: partial.method ?? 'item/tool/requestUserInput',
    threadId: partial.threadId ?? 'ask-thread-1',
    turnId: partial.turnId ?? 'turn-1',
    itemId: partial.itemId ?? 'item-1',
    status: partial.status ?? 'pending',
    createdAtMs: partial.createdAtMs ?? 1,
    submittedAtMs: partial.submittedAtMs ?? null,
    resolvedAtMs: partial.resolvedAtMs ?? null,
    payload: partial.payload ?? {},
  }
}

function makeFacadeState(
  overrides: Partial<SessionFacadeV2['state']> = {},
): SessionFacadeV2['state'] {
  const activeTurns: SessionTurn[] = overrides.activeTurns ?? []
  return {
    connection: {
      phase: 'initialized',
      clientName: 'PlanningTree Session V2',
      serverVersion: '1.0.0',
      error: null,
    },
    threads: overrides.threads ?? [],
    activeThreadId: overrides.activeThreadId ?? null,
    activeThread: overrides.activeThread ?? null,
    activeTurns,
    activeItemsByTurn: overrides.activeItemsByTurn ?? {},
    activeRunningTurn: overrides.activeRunningTurn ?? null,
    activeRequest: overrides.activeRequest ?? null,
    modelOptions: overrides.modelOptions ?? [],
    selectedModel: overrides.selectedModel ?? null,
    runtimeError: overrides.runtimeError ?? null,
    isBootstrapping: overrides.isBootstrapping ?? false,
    isSelectingThread: overrides.isSelectingThread ?? false,
    isActiveThreadReady: overrides.isActiveThreadReady ?? false,
    isModelLoading: overrides.isModelLoading ?? false,
    queueLength: overrides.queueLength ?? 0,
    gapDetected: overrides.gapDetected ?? false,
    streamConnected: overrides.streamConnected ?? false,
    reconnectCount: overrides.reconnectCount ?? 0,
    threadStatus: overrides.threadStatus ?? null,
    tokenUsage: overrides.tokenUsage ?? null,
    lastPollAtMs: overrides.lastPollAtMs ?? null,
  }
}

function makeFacade(
  stateOverrides: Partial<SessionFacadeV2['state']> = {},
): SessionFacadeV2 {
  return {
    state: makeFacadeState(stateOverrides),
    commands: {
      bootstrap: vi.fn().mockResolvedValue(undefined),
      selectThread: vi.fn().mockResolvedValue(undefined),
      createThread: vi.fn().mockResolvedValue(undefined),
      forkThread: vi.fn().mockResolvedValue(undefined),
      refreshThreads: vi.fn().mockResolvedValue(undefined),
      setModel: vi.fn(),
      submit: vi.fn().mockResolvedValue(undefined),
      interrupt: vi.fn().mockResolvedValue(undefined),
      resolveRequest: vi.fn().mockResolvedValue(undefined),
      rejectRequest: vi.fn().mockResolvedValue(undefined),
    },
  }
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-probe">{`${location.pathname}${location.search}`}</div>
}

function seedStores(options: {
  nodeKind?: 'original' | 'review'
  workflowState?: NodeWorkflowView
  workflowError?: string | null
}) {
  const {
    nodeKind = 'original',
    workflowState = makeWorkflowState(),
    workflowError = null,
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
    errors: workflowError ? { 'project-1::root': workflowError } : {},
    loadWorkflowState: vi.fn().mockResolvedValue(undefined),
    finishTask: vi.fn().mockResolvedValue(undefined),
    markDoneFromExecution: vi.fn().mockResolvedValue(undefined),
    reviewInAudit: vi.fn().mockResolvedValue(undefined),
    markDoneFromAudit: vi.fn().mockResolvedValue(undefined),
    improveInExecution: vi.fn().mockResolvedValue(undefined),
  } as Partial<ReturnType<typeof useWorkflowStateStoreV3.getState>>)
}

describe('BreadcrumbChatViewV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
    useWorkflowStateStoreV3.getState().reset()
    useUIStore.setState(useUIStore.getInitialState())
    mockUseSessionFacadeV2.mockReturnValue(makeFacade())
  })

  it('uses facade with breadcrumb policy and maps execution lane to workflow thread id', async () => {
    const facade = makeFacade({
      activeThreadId: 'exec-thread-1',
      activeThread: makeThread('exec-thread-1'),
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    seedStores({
      workflowState: makeWorkflowState({
        workflowPhase: 'execution_decision_pending',
        canSendExecutionMessage: true,
      }),
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
    await waitFor(() => {
      expect(facade.commands.selectThread).toHaveBeenCalledWith('exec-thread-1')
    })
    expect(mockUseSessionFacadeV2).toHaveBeenCalledWith({
      bootstrapPolicy: {
        autoBootstrapOnMount: true,
        autoSelectInitialThread: false,
        autoCreateThreadWhenEmpty: false,
      },
      pendingRequestScope: 'activeThread',
    })
  })

  it('maps ask lane to ask thread id', async () => {
    const facade = makeFacade({
      activeThreadId: 'ask-thread-1',
      activeThread: makeThread('ask-thread-1'),
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(facade.commands.selectThread).toHaveBeenCalledWith('ask-thread-1')
    })
    expect(screen.getByTestId('transcript-panel')).toHaveAttribute('data-thread-id', 'ask-thread-1')
  })

  it('lane without thread id clears selection and keeps transcript empty/composer disabled', async () => {
    const facade = makeFacade({
      activeThreadId: 'exec-thread-1',
      activeThread: makeThread('exec-thread-1'),
      activeTurns: [
        {
          id: 'turn-old',
          threadId: 'exec-thread-1',
          status: 'completed',
          lastCodexStatus: 'completed',
          startedAtMs: 1,
          completedAtMs: 2,
          items: [],
          error: null,
        },
      ],
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    seedStores({
      workflowState: makeWorkflowState({
        reviewThreadId: null,
      }),
    })

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

  it('disables composer while selecting/hydrating and enables when active thread is ready', async () => {
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
    })

    mockUseSessionFacadeV2.mockReturnValue(
      makeFacade({
        activeThreadId: 'ask-thread-1',
        activeThread: makeThread('ask-thread-1'),
        isSelectingThread: true,
        isActiveThreadReady: false,
      }),
    )

    const view = render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'true')

    mockUseSessionFacadeV2.mockReturnValue(
      makeFacade({
        activeThreadId: 'ask-thread-1',
        activeThread: makeThread('ask-thread-1'),
        isSelectingThread: false,
        isActiveThreadReady: true,
      }),
    )

    view.rerender(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'false')
  })

  it('submits via facade command and refreshes workflow state', async () => {
    const facade = makeFacade({
      activeThreadId: 'exec-thread-1',
      activeThread: makeThread('exec-thread-1'),
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    seedStores({
      workflowState: makeWorkflowState({
        workflowPhase: 'execution_decision_pending',
        canSendExecutionMessage: true,
      }),
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
      expect(facade.commands.submit).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'queued from composer mock',
        }),
      )
    })
    await waitFor(() => {
      expect(useWorkflowStateStoreV3.getState().loadWorkflowState).toHaveBeenCalledWith('project-1', 'root')
    })
  })

  it('shows overlay only when pending request belongs to active lane thread', async () => {
    const offLaneFacade = makeFacade({
      activeThreadId: 'ask-thread-1',
      activeThread: makeThread('ask-thread-1'),
      activeRequest: makePendingRequest({
        requestId: 'req-off-lane',
        threadId: 'execution-thread-1',
        method: 'item/tool/requestUserInput',
      }),
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(offLaneFacade)
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
    })

    const view = render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByTestId('request-user-input-overlay')).not.toBeInTheDocument()

    const onLaneFacade = makeFacade({
      activeThreadId: 'ask-thread-1',
      activeThread: makeThread('ask-thread-1'),
      activeRequest: makePendingRequest({
        requestId: 'req-on-lane',
        threadId: 'ask-thread-1',
        method: 'item/tool/requestUserInput',
      }),
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(onLaneFacade)

    view.rerender(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('request-user-input-overlay')).toHaveAttribute(
      'data-request-id',
      'req-on-lane',
    )
    fireEvent.click(screen.getByTestId('overlay-submit'))
    await waitFor(() => {
      expect(onLaneFacade.commands.resolveRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          answers: expect.any(Array),
        }),
      )
    })
  })

  it('routes overlay renderer by request method (user input, mcp, approval)', () => {
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
    })

    const renderWithRequest = (request: PendingServerRequest) => {
      mockUseSessionFacadeV2.mockReturnValue(
        makeFacade({
          activeThreadId: 'ask-thread-1',
          activeThread: makeThread('ask-thread-1'),
          activeRequest: request,
          isActiveThreadReady: true,
        }),
      )
      return render(
        <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
          <Routes>
            <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
          </Routes>
        </MemoryRouter>,
      )
    }

    const first = renderWithRequest(
      makePendingRequest({
        requestId: 'req-user-input',
        method: 'item/tool/requestUserInput',
      }),
    )
    expect(screen.getByTestId('request-user-input-overlay')).toBeInTheDocument()
    first.unmount()

    const second = renderWithRequest(
      makePendingRequest({
        requestId: 'req-mcp',
        method: 'mcpServer/elicitation/request',
      }),
    )
    expect(screen.getByTestId('mcp-elicitation-overlay')).toBeInTheDocument()
    second.unmount()

    renderWithRequest(
      makePendingRequest({
        requestId: 'req-approval',
        method: 'item/commandExecution/requestApproval',
      }),
    )
    expect(screen.getByTestId('approval-overlay')).toBeInTheDocument()
  })

  it('uses error precedence workflowError -> runtimeError -> connection.error', () => {
    seedStores({
      workflowState: makeWorkflowState({
        askThreadId: 'ask-thread-1',
      }),
      workflowError: 'Workflow failed first',
    })
    mockUseSessionFacadeV2.mockReturnValue(
      makeFacade({
        activeThreadId: 'ask-thread-1',
        activeThread: makeThread('ask-thread-1'),
        runtimeError: 'Runtime failed second',
        connection: {
          phase: 'error',
          clientName: 'PlanningTree Session V2',
          serverVersion: '1.0.0',
          error: { code: 'ERR_INTERNAL', message: 'Connection failed third' },
        },
      }),
    )

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Workflow failed first')
  })
})
