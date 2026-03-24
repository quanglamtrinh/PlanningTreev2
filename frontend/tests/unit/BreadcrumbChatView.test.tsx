import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getBootstrapStatus: vi.fn(),
    listProjects: vi.fn(),
    attachProjectFolder: vi.fn(),
    deleteProject: vi.fn(),
    getSnapshot: vi.fn(),
    resetProjectToRoot: vi.fn(),
    setActiveNode: vi.fn(),
    createChild: vi.fn(),
    splitNode: vi.fn(),
    getSplitStatus: vi.fn(),
    updateNode: vi.fn(),
    getNodeDocument: vi.fn(),
    putNodeDocument: vi.fn(),
    getChatSession: vi.fn(),
    sendChatMessage: vi.fn(),
    resetChatSession: vi.fn(),
    getDetailState: vi.fn().mockResolvedValue({
      node_id: 'root',
      frame_confirmed: false,
      frame_confirmed_revision: 0,
      frame_revision: 0,
      active_step: 'frame' as const,
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: false,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    }),
    confirmFrame: vi.fn(),
    confirmSpec: vi.fn(),
    getClarify: vi.fn().mockResolvedValue({
      schema_version: 1,
      source_frame_revision: 0,
      confirmed_at: null,
      questions: [],
      updated_at: null,
    }),
    updateClarify: vi.fn(),
    confirmClarify: vi.fn(),
    generateFrame: vi.fn(),
    getFrameGenStatus: vi.fn().mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    }),
    generateClarify: vi.fn(),
    getClarifyGenStatus: vi.fn().mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    }),
    generateSpec: vi.fn(),
    getSpecGenStatus: vi.fn().mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    }),
  },
}))

vi.mock('@uiw/react-codemirror', () => ({
  default: ({
    value,
    onChange,
    onBlur,
  }: {
    value: string
    onChange?: (value: string) => void
    onBlur?: () => void
  }) => (
    <textarea
      data-testid="mock-codemirror"
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      onBlur={() => onBlur?.()}
    />
  ),
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
    buildChatEventsUrl: (projectId: string, nodeId: string, threadRole = 'ask_planning') =>
      `/v1/projects/${projectId}/nodes/${nodeId}/chat/events?thread_role=${threadRole}`,
    appendAuthToken: (url: string) => url,
  }
})

vi.mock('../../src/features/breadcrumb/MessageFeed', () => ({
  MessageFeed: ({ messages }: { messages: Array<{ message_id: string }> }) => (
    <div data-testid="message-feed">{messages.length} messages</div>
  ),
}))

vi.mock('../../src/features/breadcrumb/ComposerBar', () => ({
  ComposerBar: ({ disabled }: { disabled: boolean }) => (
    <div data-testid="composer" data-disabled={String(disabled)}>
      Composer
    </div>
  ),
}))

import type { ChatSession, Snapshot } from '../../src/api/types'
import { BreadcrumbChatView } from '../../src/features/breadcrumb/BreadcrumbChatView'
import { useChatStore } from '../../src/stores/chat-store'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useNodeDocumentStore } from '../../src/stores/node-document-store'
import { useProjectStore } from '../../src/stores/project-store'

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    thread_id: null,
    thread_role: 'ask_planning',
    active_turn_id: null,
    messages: [],
    created_at: '2026-03-20T00:00:00Z',
    updated_at: '2026-03-20T00:00:00Z',
    ...overrides,
  }
}

function makeSnapshot(projectId = 'project-1', activeNodeId: string | null = 'root'): Snapshot {
  return {
    schema_version: 6,
    project: {
      id: projectId,
      name: `Project ${projectId}`,
      root_goal: `Goal ${projectId}`,
      project_path: `C:/workspace/${projectId}`,
      created_at: '2026-03-20T00:00:00Z',
      updated_at: '2026-03-20T00:00:00Z',
    },
    tree_state: {
      root_node_id: 'root',
      active_node_id: activeNodeId,
      node_registry: [
        {
          node_id: 'root',
          parent_id: null,
          child_ids: ['child-1'],
          title: 'Root',
          description: 'Root node',
          status: 'draft',
          node_kind: 'root',
          depth: 0,
          display_order: 0,
          hierarchical_number: '1',
          is_superseded: false,
          created_at: '2026-03-20T00:00:00Z',
          workflow: {
            frame_confirmed: false,
            active_step: 'frame',
            spec_confirmed: false,
          },
        },
        {
          node_id: 'child-1',
          parent_id: 'root',
          child_ids: [],
          title: 'Child',
          description: 'Child node',
          status: 'ready',
          node_kind: 'original',
          depth: 1,
          display_order: 0,
          hierarchical_number: '1.1',
          is_superseded: false,
          created_at: '2026-03-20T00:00:00Z',
          workflow: {
            frame_confirmed: false,
            active_step: 'frame',
            spec_confirmed: false,
          },
        },
      ],
    },
    updated_at: '2026-03-20T00:00:00Z',
  }
}

function makeIdleSplitStatus() {
  return {
    status: 'idle' as const,
    job_id: null,
    node_id: null,
    mode: null,
    started_at: null,
    completed_at: null,
    error: null,
  }
}

function makeDetailState(overrides: Record<string, unknown> = {}) {
  return {
    node_id: 'root',
    workflow: {
      frame_confirmed: false,
      active_step: 'frame' as const,
      spec_confirmed: false,
      execution_started: false,
      execution_completed: false,
      shaping_frozen: false,
      can_finish_task: false,
      execution_status: null,
    },
    frame_confirmed: false,
    frame_confirmed_revision: 0,
    frame_revision: 0,
    active_step: 'frame' as const,
    workflow_notice: null,
    frame_needs_reconfirm: false,
    frame_read_only: false,
    clarify_read_only: true,
    clarify_confirmed: false,
    spec_read_only: true,
    spec_stale: false,
    spec_confirmed: false,
    execution_started: false,
    execution_completed: false,
    shaping_frozen: false,
    can_finish_task: false,
    execution_status: null,
    audit_writable: false,
    package_audit_ready: false,
    review_status: null,
    ...overrides,
  }
}

function renderBreadcrumbChatView(initialEntry = '/projects/project-1/nodes/root/chat') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbChatView />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('BreadcrumbChatView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const mockFn of Object.values(apiMock)) {
      mockFn.mockReset()
    }
    useChatStore.getState().disconnect()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.getState().reset()
    useNodeDocumentStore.getState().reset()
    apiMock.getChatSession.mockResolvedValue(makeSession())
    apiMock.getSplitStatus.mockResolvedValue(makeIdleSplitStatus())
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-20T00:00:00Z',
    })
    apiMock.putNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-20T00:00:00Z',
    })
    apiMock.getFrameGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
    apiMock.getDetailState.mockResolvedValue(makeDetailState())
    apiMock.getClarify.mockResolvedValue({
      schema_version: 1,
      source_frame_revision: 0,
      confirmed_at: null,
      questions: [],
      updated_at: null,
    })
    apiMock.getClarifyGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
    apiMock.getSpecGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
  })

  it('renders a 60/40 thread and detail layout for the route node', async () => {
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('project-1', 'child-1'))

    renderBreadcrumbChatView()

    expect(screen.getByTestId('breadcrumb-thread-pane')).toBeInTheDocument()
    expect(screen.getByTestId('breadcrumb-detail-pane')).toBeInTheDocument()
    const detailCard = await screen.findByTestId('breadcrumb-node-detail-card')
    expect(screen.getByTestId('message-feed')).toBeInTheDocument()
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'false')
    fireEvent.click(within(detailCard).getByRole('button', { name: 'Describe' }))
    expect(within(detailCard).getByRole('heading', { level: 2, name: 'Root' })).toBeInTheDocument()
    expect(within(detailCard).getByRole('heading', { level: 3, name: 'Root' })).toBeInTheDocument()
    expect(within(detailCard).getByText('Root node')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open Breadcrumb' })).not.toBeInTheDocument()
    expect(within(detailCard).getByRole('button', { name: 'Finish Task' })).toBeDisabled()
    expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-1')
    expect(apiMock.getChatSession).toHaveBeenCalledWith('project-1', 'root', 'ask_planning')

    await waitFor(() => {
      expect(useProjectStore.getState().selectedNodeId).toBe('root')
    })
  })

  it('switches between Ask, Execution, and Audit thread sessions', async () => {
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('project-1', 'child-1'))
    apiMock.getChatSession.mockImplementation(
      async (_projectId: string, _nodeId: string, threadRole?: string) =>
        makeSession({
          thread_role: (threadRole ?? 'ask_planning') as ChatSession['thread_role'],
          messages:
            threadRole === 'execution'
              ? [{ message_id: 'exec-1' } as never]
              : threadRole === 'audit'
                ? [{ message_id: 'audit-1' } as never, { message_id: 'audit-2' } as never]
                : [],
        }),
    )

    renderBreadcrumbChatView()

    await screen.findByTestId('breadcrumb-node-detail-card')

    expect(screen.getByTestId('breadcrumb-thread-tab-ask')).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'false')
    expect(screen.getByTestId('message-feed')).toHaveTextContent('0 messages')

    fireEvent.click(screen.getByTestId('breadcrumb-thread-tab-execution'))
    await waitFor(() => {
      expect(screen.getByTestId('breadcrumb-thread-tab-execution')).toHaveAttribute('aria-selected', 'true')
    })
    expect(screen.getByTestId('message-feed')).toHaveTextContent('1 messages')
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'true')

    fireEvent.click(screen.getByTestId('breadcrumb-thread-tab-audit'))
    await waitFor(() => {
      expect(screen.getByTestId('breadcrumb-thread-tab-audit')).toHaveAttribute('aria-selected', 'true')
    })
    expect(screen.getByTestId('message-feed')).toHaveTextContent('2 messages')
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'true')

    fireEvent.click(screen.getByTestId('breadcrumb-thread-tab-ask'))
    await waitFor(() => {
      expect(screen.getByTestId('breadcrumb-thread-tab-ask')).toHaveAttribute('aria-selected', 'true')
    })
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'false')
    expect(apiMock.getChatSession).toHaveBeenCalledWith('project-1', 'root', 'execution')
    expect(apiMock.getChatSession).toHaveBeenCalledWith('project-1', 'root', 'audit')
  })

  it('disables ask_planning when shaping is frozen', async () => {
    apiMock.getSnapshot.mockResolvedValue(
      makeSnapshot('project-1', 'root'),
    )
    apiMock.getDetailState.mockResolvedValue(
      makeDetailState({
        shaping_frozen: true,
        execution_started: true,
        execution_completed: true,
        execution_status: 'completed',
      }),
    )

    renderBreadcrumbChatView()

    await screen.findByTestId('breadcrumb-node-detail-card')
    await waitFor(() => {
      expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'true')
    })
  })

  it('enables audit only when audit_writable is true', async () => {
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('project-1', 'child-1'))
    apiMock.getDetailState.mockResolvedValue(
      makeDetailState({
        shaping_frozen: true,
        execution_started: true,
        execution_completed: true,
        execution_status: 'completed',
        audit_writable: true,
      }),
    )

    renderBreadcrumbChatView()

    await screen.findByTestId('breadcrumb-node-detail-card')

    fireEvent.click(screen.getByTestId('breadcrumb-thread-tab-audit'))
    await waitFor(() => {
      expect(screen.getByTestId('breadcrumb-thread-tab-audit')).toHaveAttribute('aria-selected', 'true')
    })
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'false')
  })

  it('reloads project details when the store is focused on another project', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-2',
      snapshot: makeSnapshot('project-2'),
      selectedNodeId: 'root',
    })
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('project-1'))

    renderBreadcrumbChatView()

    await waitFor(() => {
      expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-1')
    })
    const detailCard = await screen.findByTestId('breadcrumb-node-detail-card')
    fireEvent.click(within(detailCard).getByRole('button', { name: 'Describe' }))
    expect(within(detailCard).getByRole('heading', { level: 2, name: 'Root' })).toBeInTheDocument()
  })

  it('shows an unavailable state when the route node is missing from the snapshot', async () => {
    const snapshot = makeSnapshot('project-1')
    apiMock.getSnapshot.mockResolvedValue({
      ...snapshot,
      tree_state: {
        ...snapshot.tree_state,
        node_registry: snapshot.tree_state.node_registry.filter((node) => node.node_id !== 'child-1'),
      },
    })

    renderBreadcrumbChatView('/projects/project-1/nodes/missing/chat')

    const detailCard = await screen.findByTestId('breadcrumb-node-detail-card')
    expect(within(detailCard).getByText('Node details unavailable')).toBeInTheDocument()
    expect(
      within(detailCard).getByText('This node was not found in the current project snapshot.'),
    ).toBeInTheDocument()
  })
})
