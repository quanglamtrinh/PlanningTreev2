import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockUseSessionFacadeV2, apiMock } = vi.hoisted(() => ({
  mockUseSessionFacadeV2: vi.fn(),
  apiMock: {
    ensureRootThread: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
  appendAuthToken: (url: string) => url,
  initAuthToken: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../../src/features/session_v2/components/ComposerPane', () => ({
  ComposerPane: ({
    isTurnRunning,
    disabled,
    onSubmit,
    onInterrupt,
  }: {
    isTurnRunning?: boolean
    disabled?: boolean
    onSubmit: (payload: {
      input: Array<Record<string, unknown>>
      text: string
      requestedPolicy?: {
        accessMode?: 'full-access' | 'default-permissions'
        effort?: 'low' | 'medium' | 'high' | 'extra-high'
        workMode?: 'local' | 'remote'
        streamMode?: 'streaming' | 'batch'
      }
    }) => Promise<void>
    onInterrupt: () => Promise<void>
  }) => (
    <div
      data-testid="composer-pane"
      data-disabled={String(Boolean(disabled))}
      data-running={String(Boolean(isTurnRunning))}
    >
      <button
        type="button"
        data-testid="composer-submit-mock"
        disabled={Boolean(disabled)}
        onClick={() =>
          void onSubmit({
            input: [{ type: 'text', text: 'queued from composer mock' }],
            text: 'queued from composer mock',
            requestedPolicy: {
              accessMode: 'full-access',
              effort: 'extra-high',
              workMode: 'local',
              streamMode: 'streaming',
            },
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
    onResolve: (requestId: string, result: Record<string, unknown>) => Promise<void>
    onReject: (requestId: string, reason?: string | null) => Promise<void>
  }) => (
    <div data-testid="request-user-input-overlay" data-request-id={request.requestId}>
      <button
        type="button"
        data-testid="overlay-submit"
        onClick={() =>
          void onResolve(request.requestId, {
            answers: [{ id: 'q-1', selectedOption: 'Option A', notes: '', status: 'answered' }],
          })
        }
      >
        Submit
      </button>
      <button
        type="button"
        data-testid="overlay-cancel"
        onClick={() => void onReject(request.requestId, 'cancel')}
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
    onResolve: (requestId: string, result: Record<string, unknown>) => Promise<void>
  }) => (
    <div data-testid="mcp-elicitation-overlay" data-request-id={request.requestId}>
      <button
        type="button"
        data-testid="mcp-overlay-submit"
        onClick={() => void onResolve(request.requestId, { response: { name: 'value' } })}
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
    onResolve: (requestId: string, result: Record<string, unknown>) => Promise<void>
  }) => (
    <div data-testid="approval-overlay" data-request-id={request.requestId}>
      <button
        type="button"
        data-testid="approval-overlay-accept"
        onClick={() => void onResolve(request.requestId, { decision: 'accept' })}
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

vi.mock('../../src/features/workflow_v2/hooks/useWorkflowEventBridgeV2', () => ({
  useWorkflowEventBridgeV2: vi.fn(),
}))

vi.mock('../../src/features/session_v2/facade/useSessionFacadeV2', () => ({
  useSessionFacadeV2: mockUseSessionFacadeV2,
}))

import type { Snapshot } from '../../src/api/types'
import { BreadcrumbViewV2 } from '../../src/features/conversation/BreadcrumbViewV2'
import type { PendingServerRequest, SessionThread, SessionTurn } from '../../src/features/session_v2/contracts'
import type { SessionFacadeV2 } from '../../src/features/session_v2/facade/useSessionFacadeV2'
import { useThreadSessionStore } from '../../src/features/session_v2/store/threadSessionStore'
import { useWorkflowStateStoreV2 } from '../../src/features/workflow_v2/store/workflowStateStoreV2'
import type { WorkflowStateV2 } from '../../src/features/workflow_v2/types'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useProjectStore } from '../../src/stores/project-store'
import { useUIStore } from '../../src/stores/ui-store'

function makeProjectSnapshot(nodeKind: 'root' | 'original' | 'review' = 'original'): Snapshot {
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

type WorkflowStateOverrides = Partial<Omit<WorkflowStateV2, 'threads' | 'decisions' | 'context'>> & {
  threads?: Partial<WorkflowStateV2['threads']>
  decisions?: Partial<WorkflowStateV2['decisions']>
  context?: Partial<WorkflowStateV2['context']>
}

function makeWorkflowState(overrides: WorkflowStateOverrides = {}): WorkflowStateV2 {
  const base: WorkflowStateV2 = {
    schemaVersion: 1,
    projectId: 'project-1',
    nodeId: 'root',
    phase: 'ready_for_execution',
    version: 1,
    threads: {
      askPlanning: 'ask-thread-1',
      execution: 'exec-thread-1',
      audit: null,
      packageReview: null,
    },
    decisions: {
      execution: null,
      audit: null,
    },
    context: {
      frameVersion: null,
      specVersion: null,
      splitManifestVersion: null,
    },
    allowedActions: [],
  }
  return {
    ...base,
    ...overrides,
    threads: {
      ...base.threads,
      ...(overrides.threads ?? {}),
    },
    decisions: {
      ...base.decisions,
      ...(overrides.decisions ?? {}),
    },
    context: {
      ...base.context,
      ...(overrides.context ?? {}),
    },
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

function makeRunningTurn(metadata: Record<string, unknown> = {}): SessionTurn {
  return {
    id: 'turn-running',
    threadId: 'ask-thread-1',
    status: 'inProgress',
    lastCodexStatus: 'inProgress',
    startedAtMs: 1,
    completedAtMs: null,
    items: [],
    error: null,
    metadata,
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
      submitSessionAction: vi.fn().mockResolvedValue(undefined),
      setModel: vi.fn(),
      submit: vi.fn().mockResolvedValue(undefined),
      interrupt: vi.fn().mockResolvedValue(undefined),
      resolveRequest: vi.fn().mockResolvedValue(undefined),
      rejectRequest: vi.fn().mockResolvedValue(undefined),
      resyncThreadTranscript: vi.fn().mockResolvedValue(undefined),
    },
  }
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-probe">{`${location.pathname}${location.search}`}</div>
}

function seedStores(options: {
  nodeKind?: 'root' | 'original' | 'review'
  workflowState?: WorkflowStateV2
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
  useWorkflowStateStoreV2.setState({
    mutationResultByKey: {},
    entries: { 'project-1::root': workflowState },
    errors: workflowError ? { 'project-1::root': workflowError } : {},
    activeMutations: { 'project-1::root': null },
    loadWorkflowState: vi.fn().mockResolvedValue(undefined),
    ensureThread: vi.fn().mockResolvedValue({
      workflowState,
      threadId: workflowState.threads.askPlanning,
      turnId: null,
      executionRunId: null,
      auditRunId: null,
      reviewCycleId: null,
      reviewThreadId: null,
      reviewCommitSha: null,
    }),
    startExecution: vi.fn().mockResolvedValue({
      workflowState,
      threadId: workflowState.threads.execution,
      turnId: null,
      executionRunId: null,
      auditRunId: null,
      reviewCycleId: null,
      reviewThreadId: null,
      reviewCommitSha: null,
    }),
    completeExecution: vi.fn().mockResolvedValue({
      workflowState,
      threadId: null,
      turnId: null,
      executionRunId: null,
      auditRunId: null,
      reviewCycleId: null,
      reviewThreadId: null,
      reviewCommitSha: null,
    }),
    startAudit: vi.fn().mockResolvedValue({
      workflowState,
      threadId: workflowState.threads.audit,
      turnId: null,
      executionRunId: null,
      auditRunId: null,
      reviewCycleId: null,
      reviewThreadId: null,
      reviewCommitSha: null,
    }),
    improveExecution: vi.fn().mockResolvedValue({
      workflowState,
      threadId: workflowState.threads.execution,
      turnId: null,
      executionRunId: null,
      auditRunId: null,
      reviewCycleId: null,
      reviewThreadId: null,
      reviewCommitSha: null,
    }),
    acceptAudit: vi.fn().mockResolvedValue({
      workflowState,
      threadId: null,
      turnId: null,
      executionRunId: null,
      auditRunId: null,
      reviewCycleId: null,
      reviewThreadId: null,
      reviewCommitSha: null,
    }),
  } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)
}

describe('BreadcrumbViewV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.ensureRootThread.mockResolvedValue({ threadId: 'root-thread-1', role: 'root' })
    useThreadSessionStore.getState().clear()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
    useWorkflowStateStoreV2.getState().reset()
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
        phase: 'execution_completed',
      }),
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2']}>
        <Routes>
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={
              <>
                <BreadcrumbViewV2 />
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
    expect(facade.commands.selectThread).not.toHaveBeenCalled()
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
        threads: { askPlanning: 'ask-thread-1', execution: 'exec-thread-1', audit: null, packageReview: null },
      }),
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(facade.commands.selectThread).not.toHaveBeenCalled()
    expect(screen.getByTestId('transcript-panel')).toHaveAttribute('data-thread-id', 'ask-thread-1')
  })

  it('auto-ensures ask planning thread from Workflow V2 when ask lane is unbound', async () => {
    const facade = makeFacade({
      selectedModel: 'gpt-5.4',
      activeThread: makeThread('model-source-thread'),
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    const workflowState = makeWorkflowState({
      threads: { askPlanning: null },
    })
    seedStores({ workflowState })
    const ensureThread = vi.fn().mockResolvedValue(
      makeWorkflowState({
        threads: { askPlanning: 'ask-thread-2' },
      }),
    )
    useWorkflowStateStoreV2.setState({
      ensureThread,
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.queryByTestId('workflow-ensure-ask-thread')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(ensureThread).toHaveBeenCalledWith(
        'project-1',
        'root',
        'ask_planning',
        expect.objectContaining({
          model: 'gpt-5.4',
          modelProvider: 'openai',
        }),
      )
    })
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
        threads: { audit: null },
      }),
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=audit']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
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
        threads: { askPlanning: 'ask-thread-1' },
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
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
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
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'false')
  })

  it.each([
    ['frame', { workflowInternal: true, artifactKind: 'frame' }],
    ['spec', { workflowKind: 'generate_spec' }],
    ['clarify', { workflowAction: 'generate_clarify' }],
    ['split', { step: 'split' }],
    ['execute', { primedByWorkflowAction: true, targetLane: 'execution' }],
    ['review', { action: 'review_in_audit' }],
  ])('disables composer instead of exposing steer while %s workflow turn is running', (_label, metadata) => {
    seedStores({
      workflowState: makeWorkflowState({
        threads: { askPlanning: 'ask-thread-1' },
      }),
    })
    mockUseSessionFacadeV2.mockReturnValue(
      makeFacade({
        activeThreadId: 'ask-thread-1',
        activeThread: makeThread('ask-thread-1'),
        activeRunningTurn: makeRunningTurn(metadata),
        isActiveThreadReady: true,
      }),
    )

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-running', 'true')
    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'true')
  })

  it('submits ask lane via facade command and refreshes workflow state', async () => {
    const facade = makeFacade({
      activeThreadId: 'ask-thread-1',
      activeThread: makeThread('ask-thread-1'),
      isActiveThreadReady: true,
      selectedModel: 'gpt-5.4',
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    const workflowState = makeWorkflowState({
      threads: { askPlanning: 'ask-thread-1' },
    })
    seedStores({ workflowState })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByTestId('composer-submit-mock'))

    await waitFor(() => {
      expect(facade.commands.submit).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'queued from composer mock',
        }),
        expect.objectContaining({
          model: 'gpt-5.4',
          cwd: 'C:/workspace/project-1',
          approvalPolicy: 'never',
          sandboxPolicy: { type: 'dangerFullAccess' },
          effort: 'xhigh',
          summary: null,
        }),
        {
          mcpContext: { projectId: 'project-1', nodeId: 'root', role: 'ask_planning' },
          skillsContext: { projectId: 'project-1', nodeId: 'root', role: 'ask_planning' },
        },
      )
    })
    await waitFor(() => {
      expect(useWorkflowStateStoreV2.getState().loadWorkflowState).toHaveBeenCalledWith('project-1', 'root')
    })
  })

  it('ensures root thread, hides workflow tabs, and submits with root MCP context', async () => {
    const facade = makeFacade({
      activeThreadId: 'root-thread-1',
      activeThread: makeThread('root-thread-1'),
      isActiveThreadReady: true,
      selectedModel: 'gpt-5.4',
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    const workflowState = makeWorkflowState()
    seedStores({ nodeKind: 'root', workflowState })
    const loadWorkflowState = vi.fn().mockResolvedValue(undefined)
    useWorkflowStateStoreV2.setState({
      loadWorkflowState,
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=root']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(apiMock.ensureRootThread).toHaveBeenCalledWith(
        'project-1',
        'root',
        expect.objectContaining({
          model: 'gpt-5.4',
          modelProvider: 'openai',
        }),
      )
    })
    expect(screen.queryByRole('tab', { name: 'Ask' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Execution' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Review' })).not.toBeInTheDocument()
    expect(facade.commands.selectThread).not.toHaveBeenCalled()
    expect(facade.commands.resyncThreadTranscript).toHaveBeenCalledWith('root-thread-1')

    fireEvent.click(screen.getByTestId('composer-submit-mock'))

    await waitFor(() => {
      expect(facade.commands.submit).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'queued from composer mock',
        }),
        undefined,
        {
          mcpContext: { projectId: 'project-1', nodeId: 'root', role: 'root' },
          skillsContext: { projectId: 'project-1', nodeId: 'root', role: 'root' },
        },
      )
    })
    expect(loadWorkflowState).not.toHaveBeenCalled()
  })

  it('keeps root composer enabled once the root thread is selected while metadata hydrates', async () => {
    const facade = makeFacade({
      activeThreadId: 'root-thread-1',
      activeThread: null,
      isActiveThreadReady: false,
      selectedModel: 'gpt-5.4',
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    seedStores({ nodeKind: 'root' })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=root']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(apiMock.ensureRootThread).toHaveBeenCalledWith(
        'project-1',
        'root',
        expect.objectContaining({
          model: 'gpt-5.4',
        }),
      )
    })
    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'false')
  })

  it('enables root composer after ensure even before the facade selection catches up', async () => {
    const facade = makeFacade({
      activeThreadId: null,
      activeThread: null,
      isActiveThreadReady: false,
      selectedModel: 'gpt-5.4',
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    seedStores({ nodeKind: 'root' })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=root']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(apiMock.ensureRootThread).toHaveBeenCalledWith(
        'project-1',
        'root',
        expect.objectContaining({
          model: 'gpt-5.4',
        }),
      )
    })
    await waitFor(() => {
      expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'false')
    })

    fireEvent.click(screen.getByTestId('composer-submit-mock'))

    await waitFor(() => {
      expect(facade.commands.selectThread).toHaveBeenCalledWith('root-thread-1')
    })
    await waitFor(() => {
      expect(facade.commands.submit).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'queued from composer mock',
        }),
        undefined,
        {
          mcpContext: { projectId: 'project-1', nodeId: 'root', role: 'root' },
          skillsContext: { projectId: 'project-1', nodeId: 'root', role: 'root' },
        },
      )
    })
  })

  it('keeps root composer editable while the root thread ensure request is still pending', () => {
    apiMock.ensureRootThread.mockImplementation(
      () =>
        new Promise(() => {
          // Keep the ensure request pending to verify the composer does not wait on it.
        }),
    )
    const facade = makeFacade({
      activeThreadId: null,
      activeThread: null,
      isActiveThreadReady: false,
      selectedModel: 'gpt-5.4',
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    seedStores({ nodeKind: 'root' })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=root']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'false')
  })

  it('preserves requested root thread while the project snapshot is loading', async () => {
    const facade = makeFacade({
      activeThreadId: 'root-thread-1',
      activeThread: makeThread('root-thread-1'),
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    const loadedSnapshot = makeProjectSnapshot('root')
    useProjectStore.setState({
      activeProjectId: 'project-1',
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
        ask_followup_queue_enabled: true,
      },
      snapshot: null,
      selectedNodeId: null,
      isLoadingSnapshot: false,
      error: null,
      loadProject: vi.fn().mockImplementation(async () => {
        useProjectStore.setState({
          snapshot: loadedSnapshot,
          selectedNodeId: 'root',
          isLoadingSnapshot: false,
        } as Partial<ReturnType<typeof useProjectStore.getState>>)
      }),
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
        },
      },
      loadDetailState: vi.fn().mockResolvedValue(undefined),
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=root']}>
        <Routes>
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={
              <>
                <BreadcrumbViewV2 />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('location-probe')).toHaveTextContent(
      '/projects/project-1/nodes/root/chat-v2?thread=root',
    )
    await waitFor(() => {
      expect(apiMock.ensureRootThread).toHaveBeenCalledWith(
        'project-1',
        'root',
        expect.any(Object),
      )
    })
    expect(screen.queryByRole('tab', { name: 'Execution' })).not.toBeInTheDocument()
  })

  it('keeps requested root mode editable while the project snapshot request is pending', () => {
    const facade = makeFacade({
      activeThreadId: null,
      activeThread: null,
      isActiveThreadReady: false,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)
    useProjectStore.setState({
      activeProjectId: 'project-1',
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
        ask_followup_queue_enabled: true,
      },
      snapshot: null,
      selectedNodeId: null,
      isLoadingSnapshot: true,
      error: null,
      loadProject: vi.fn().mockImplementation(
        () =>
          new Promise(() => {
            // Keep snapshot hydration pending so the route itself must preserve root mode.
          }),
      ),
      selectNode: vi.fn().mockResolvedValue(undefined),
    })

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=root']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByRole('tab', { name: 'Execution' })).not.toBeInTheDocument()
    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'false')
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
        threads: { askPlanning: 'ask-thread-1' },
      }),
    })

    const view = render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=ask']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
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
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
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
        'req-on-lane',
        expect.objectContaining({
          answers: expect.any(Array),
        }),
      )
    })
  })

  it('routes overlay renderer by request method (user input, mcp, approval)', () => {
    seedStores({
      workflowState: makeWorkflowState({
        threads: { askPlanning: 'ask-thread-1' },
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
            <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
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
        threads: { askPlanning: 'ask-thread-1' },
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
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Workflow failed first')
  })

  it('does not expose package review action from Breadcrumb', () => {
    seedStores({
      workflowState: makeWorkflowState({
        phase: 'done',
        allowedActions: ['start_package_review'],
      }),
    })
    mockUseSessionFacadeV2.mockReturnValue(
      makeFacade({
        activeThreadId: 'exec-thread-1',
        activeThread: makeThread('exec-thread-1'),
        isActiveThreadReady: true,
      }),
    )

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByTestId('workflow-start-package-review')).not.toBeInTheDocument()
  })

  it('does not expose start execution action from the execution lane', () => {
    const workflowState = makeWorkflowState({
      phase: 'ready_for_execution',
      threads: {
        execution: 'exec-thread-1',
      },
      allowedActions: ['start_execution'],
    })
    seedStores({ workflowState })
    const startExecution = vi.fn()
    useWorkflowStateStoreV2.setState({
      startExecution,
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)
    mockUseSessionFacadeV2.mockReturnValue(
      makeFacade({
        activeThreadId: 'exec-thread-1',
        activeThread: makeThread('exec-thread-1'),
        isActiveThreadReady: true,
      }),
    )

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByTestId('workflow-start-execution')).not.toBeInTheDocument()
    expect(startExecution).not.toHaveBeenCalled()
  })

  it('shows debug panel when debugSession query flag is enabled', async () => {
    seedStores({
      workflowState: makeWorkflowState({
        phase: 'executing',
        threads: {
          execution: 'exec-thread-1',
        },
      }),
    })
    mockUseSessionFacadeV2.mockReturnValue(
      makeFacade({
        activeThreadId: 'exec-thread-1',
        activeThread: makeThread('exec-thread-1'),
        isActiveThreadReady: true,
      }),
    )

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution&debugSession=1']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    const panel = await screen.findByTestId('session-debug-panel')
    expect(panel).toBeInTheDocument()
    expect(panel.textContent ?? '').toContain('workflowLaneThreadId')
    expect(screen.getByRole('button', { name: 'Copy trace payload' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show context items' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show context items' }))
    expect(screen.getByRole('button', { name: 'Hide context items' })).toBeInTheDocument()
  })
})
