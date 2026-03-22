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
import { useNodeDocumentStore } from '../../src/stores/node-document-store'
import { useProjectStore } from '../../src/stores/project-store'

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    thread_id: null,
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
    expect(screen.queryByRole('button', { name: 'Finish Task' })).not.toBeInTheDocument()
    expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-1')
    expect(apiMock.getChatSession).toHaveBeenCalledWith('project-1', 'root')

    await waitFor(() => {
      expect(useProjectStore.getState().selectedNodeId).toBe('root')
    })
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
