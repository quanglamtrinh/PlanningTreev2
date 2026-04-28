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

vi.mock('../../src/features/workflow_v2/hooks/useWorkflowEventBridgeV2', () => ({
  useWorkflowEventBridgeV2: vi.fn(),
}))

vi.mock('../../src/features/session_v2/facade/useSessionFacadeV2', () => ({
  useSessionFacadeV2: mockUseSessionFacadeV2,
}))

import type { Snapshot } from '../../src/api/types'
import { BreadcrumbViewV2 } from '../../src/features/conversation/BreadcrumbViewV2'
import type { SessionFacadeV2, SessionFacadeState } from '../../src/features/session_v2/facade/useSessionFacadeV2'
import { useWorkflowStateStoreV2 } from '../../src/features/workflow_v2/store/workflowStateStoreV2'
import type { WorkflowStateV2 } from '../../src/features/workflow_v2/types'
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

function makeWorkflowState(overrides: Partial<WorkflowStateV2> = {}): WorkflowStateV2 {
  return {
    schemaVersion: 1,
    projectId: 'project-1',
    nodeId: 'root',
    phase: 'execution_completed',
    version: 1,
    threads: {
      askPlanning: 'ask-thread-1',
      execution: 'exec-thread-1',
      audit: 'audit-thread-1',
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
    ...overrides,
  }
}

function seedBaseStores(workflowState: WorkflowStateV2, snapshot: Snapshot) {
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
  useWorkflowStateStoreV2.setState({
    entries: {
      'project-1::root': workflowState,
    },
    activeMutations: {
      'project-1::root': null,
    },
    loadWorkflowState: vi.fn().mockResolvedValue(undefined),
  } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)
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

describe('BreadcrumbChatViewV2 Workflow V2 cutover integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
    useWorkflowStateStoreV2.getState().reset()
    useUIStore.setState(useUIStore.getInitialState())
    mockUseSessionFacadeV2.mockReturnValue(makeFacade({}))
  })

  it('renders execution lane from Workflow V2 thread binding and Session V2 transcript', async () => {
    seedBaseStores(makeWorkflowState(), makeProjectSnapshot('original'))
    const facade = makeFacade({
      activeThreadId: 'exec-thread-1',
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=execution']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('transcript-panel')).toHaveAttribute('data-thread-id', 'exec-thread-1')
    })
    expect(screen.getByTestId('composer-pane')).toHaveAttribute('data-disabled', 'true')
    expect(facade.commands.selectThread).not.toHaveBeenCalled()
  })

  it('renders audit lane with transcript when Workflow V2 audit thread exists', async () => {
    seedBaseStores(makeWorkflowState({ phase: 'review_pending' }), makeProjectSnapshot('original'))
    const facade = makeFacade({
      activeThreadId: 'audit-thread-1',
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=audit']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('transcript-panel')).toHaveAttribute('data-thread-id', 'audit-thread-1')
    })
    expect(facade.commands.selectThread).not.toHaveBeenCalled()
  })

  it('clears selection for audit lane when Workflow V2 audit thread is missing', async () => {
    seedBaseStores(
      makeWorkflowState({
        phase: 'review_pending',
        threads: {
          askPlanning: 'ask-thread-1',
          execution: 'exec-thread-1',
          audit: null,
          packageReview: null,
        },
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

  it('falls back package thread routes to the execution lane', async () => {
    seedBaseStores(
      makeWorkflowState({
        phase: 'done',
        threads: {
          askPlanning: 'ask-thread-1',
          execution: 'exec-thread-1',
          audit: 'audit-thread-1',
          packageReview: 'package-thread-1',
        },
      }),
      makeProjectSnapshot('original'),
    )
    const facade = makeFacade({
      activeThreadId: 'exec-thread-1',
      isActiveThreadReady: true,
    })
    mockUseSessionFacadeV2.mockReturnValue(facade)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2?thread=package']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('transcript-panel')).toHaveAttribute('data-thread-id', 'exec-thread-1')
    })
    expect(screen.getByTestId('breadcrumb-thread-tab-execution')).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByTestId('breadcrumb-thread-tab-package')).not.toBeInTheDocument()
  })
})
