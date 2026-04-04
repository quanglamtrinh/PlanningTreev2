import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
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
    getDetailState: vi.fn(),
    confirmFrame: vi.fn(),
    confirmSpec: vi.fn(),
    getClarify: vi.fn(),
    updateClarify: vi.fn(),
    confirmClarify: vi.fn(),
    generateFrame: vi.fn(),
    getFrameGenStatus: vi.fn(),
    generateClarify: vi.fn(),
    getClarifyGenStatus: vi.fn(),
    generateSpec: vi.fn(),
    getSpecGenStatus: vi.fn(),
    acceptLocalReview: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
  buildChatEventsUrl: (projectId: string, nodeId: string, threadRole = 'ask_planning') =>
    `/v1/projects/${projectId}/nodes/${nodeId}/chat/events?thread_role=${threadRole}`,
  appendAuthToken: (url: string) => url,
}))

vi.mock('../../src/features/breadcrumb/MessageFeed', () => ({
  MessageFeed: () => <div data-testid="message-feed">feed</div>,
}))

vi.mock('../../src/features/breadcrumb/ComposerBar', () => ({
  ComposerBar: ({ disabled }: { disabled: boolean }) => (
    <div data-testid="composer" data-disabled={String(disabled)}>
      Composer
    </div>
  ),
}))

vi.mock('../../src/features/node/NodeDetailCard', () => ({
  NodeDetailCard: () => <div data-testid="breadcrumb-node-detail-card">detail</div>,
}))

import type { ChatSession, Snapshot } from '../../src/api/types'
import { BreadcrumbChatView } from '../../src/features/breadcrumb/BreadcrumbChatView'
import { useChatStore } from '../../src/stores/chat-store'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
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

function makeSnapshot(nodeKind: 'root' | 'original' | 'review' = 'original'): Snapshot {
  return {
    schema_version: 6,
    project: {
      id: 'project-1',
      name: 'Project',
      root_goal: 'Goal',
      project_path: 'C:/workspace/project-1',
      created_at: '2026-03-20T00:00:00Z',
      updated_at: '2026-03-20T00:00:00Z',
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
          is_superseded: false,
          created_at: '2026-03-20T00:00:00Z',
          workflow: nodeKind === 'review' ? null : { frame_confirmed: false, active_step: 'frame', spec_confirmed: false },
        },
      ],
    },
    updated_at: '2026-03-20T00:00:00Z',
  }
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-path">{`${location.pathname}${location.search}`}</div>
}

function renderBreadcrumbChatView(initialEntry = '/projects/project-1/nodes/root/chat') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <LocationProbe />
      <Routes>
        <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbChatView />} />
        <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<div data-testid="chat-v2-route" />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('BreadcrumbChatView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useChatStore.getState().disconnect()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.getState().reset()

    useProjectStore.setState({
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
      },
    })

    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('original'))
    apiMock.getChatSession.mockResolvedValue(makeSession())
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      workflow: null,
      frame_confirmed: false,
      frame_confirmed_revision: 0,
      frame_revision: 0,
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
    })
    apiMock.getSplitStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      node_id: null,
      mode: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '',
      updated_at: '2026-03-20T00:00:00Z',
    })
    apiMock.putNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '',
      updated_at: '2026-03-20T00:00:00Z',
    })
    apiMock.getFrameGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
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

  it('redirects ask lane from legacy /chat to /chat-v2', async () => {
    renderBreadcrumbChatView('/projects/project-1/nodes/root/chat?thread=ask')

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-1/nodes/root/chat-v2?thread=ask')
    })
    expect(screen.getByTestId('chat-v2-route')).toBeInTheDocument()
  })

  it('redirects bare legacy /chat route to /chat-v2 ask', async () => {
    renderBreadcrumbChatView('/projects/project-1/nodes/root/chat')

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-1/nodes/root/chat-v2?thread=ask')
    })
  })

  it('redirects direct legacy execution route to /chat-v2 without loading legacy session', async () => {
    renderBreadcrumbChatView('/projects/project-1/nodes/root/chat?thread=execution')

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-1/nodes/root/chat-v2?thread=execution')
    })
    expect(apiMock.getChatSession).not.toHaveBeenCalled()
  })

  it('redirects review-node legacy routes to /chat-v2 audit', async () => {
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('review'))

    renderBreadcrumbChatView('/projects/project-1/nodes/root/chat')

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-1/nodes/root/chat-v2?thread=audit')
    })
  })
})
