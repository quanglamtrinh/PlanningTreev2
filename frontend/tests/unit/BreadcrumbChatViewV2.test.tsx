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
  ConversationFeed: ({ prefix }: { prefix?: React.ReactNode }) => (
    <div data-testid="conversation-feed">
      {prefix ? <div data-testid="conversation-prefix">{prefix}</div> : null}
      feed
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

import type { Snapshot, ThreadSnapshotV2 } from '../../src/api/types'
import { BreadcrumbChatViewV2 } from '../../src/features/conversation/BreadcrumbChatViewV2'
import { useConversationThreadStoreV2 } from '../../src/features/conversation/state/threadStoreV2'
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
    threadRole: 'ask_planning',
    threadId: 'thread-1',
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
      lineageRootThreadId: 'thread-1',
    },
    items: [],
    pendingRequests: [],
    ...overrides,
  }
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-probe">{location.pathname}</div>
}

describe('BreadcrumbChatViewV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
    useConversationThreadStoreV2.getState().disconnectThread()
  })

  it('renders prefix and detail pane for non-review nodes', () => {
    const loadProject = vi.fn().mockResolvedValue(undefined)
    const selectNode = vi.fn().mockResolvedValue(undefined)
    const loadDetailState = vi.fn().mockResolvedValue(undefined)
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
          audit_writable: true,
        },
      },
      loadDetailState,
      acceptLocalReview: vi.fn(),
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)
    useConversationThreadStoreV2.setState({
      snapshot: makeConversationSnapshot(),
      loadThread,
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      resetThread: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useConversationThreadStoreV2.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('breadcrumb-detail-pane')).toBeInTheDocument()
    expect(screen.getByTestId('frame-context-ask')).toBeInTheDocument()
    expect(screen.getByTestId('composer')).toHaveAttribute('data-disabled', 'true')
    expect(screen.queryByTestId('breadcrumb-v2-reset-thread')).not.toBeInTheDocument()
  })

  it('forces audit layout and hides the detail pane for review nodes', () => {
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
      entries: { 'project-1::root': undefined as never },
      loadDetailState: vi.fn().mockResolvedValue(undefined),
      acceptLocalReview: vi.fn(),
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)
    useConversationThreadStoreV2.setState({
      snapshot: makeConversationSnapshot({ threadRole: 'audit' }),
      loadThread: vi.fn().mockResolvedValue(undefined),
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      resetThread: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useConversationThreadStoreV2.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('breadcrumb-review-audit-header')).toBeInTheDocument()
    expect(screen.queryByTestId('breadcrumb-detail-pane')).not.toBeInTheDocument()
  })

  it('accept-review success resets tab to ask and navigates to sibling /chat-v2', async () => {
    const acceptLocalReview = vi.fn().mockResolvedValue('sibling-1')

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
          can_accept_local_review: true,
          execution_status: 'completed',
          audit_writable: true,
        },
      },
      loadDetailState: vi.fn().mockResolvedValue(undefined),
      acceptLocalReview,
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)
    useConversationThreadStoreV2.setState({
      snapshot: makeConversationSnapshot({ threadRole: 'audit' }),
      loadThread: vi.fn().mockResolvedValue(undefined),
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      resetThread: vi.fn().mockResolvedValue(undefined),
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useConversationThreadStoreV2.getState>>)

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

    fireEvent.click(screen.getByTestId('breadcrumb-thread-tab-audit'))
    fireEvent.change(screen.getByPlaceholderText('Review summary...'), {
      target: { value: 'Looks good' },
    })
    fireEvent.click(screen.getByTestId('accept-review-button'))

    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/projects/project-1/nodes/sibling-1/chat-v2')
    })
    await waitFor(() => {
      expect(screen.getByTestId('breadcrumb-thread-tab-ask')).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('shows reset on writable ask and calls resetThread after confirmation', async () => {
    const resetThread = vi.fn().mockResolvedValue(undefined)
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

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
          audit_writable: true,
        },
      },
      loadDetailState: vi.fn().mockResolvedValue(undefined),
      acceptLocalReview: vi.fn(),
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)
    useConversationThreadStoreV2.setState({
      snapshot: makeConversationSnapshot(),
      loadThread: vi.fn().mockResolvedValue(undefined),
      sendTurn: vi.fn().mockResolvedValue(undefined),
      resolveUserInput: vi.fn().mockResolvedValue(undefined),
      resetThread,
      disconnectThread: vi.fn(),
    } as Partial<ReturnType<typeof useConversationThreadStoreV2.getState>>)

    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat-v2']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<BreadcrumbChatViewV2 />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByTestId('breadcrumb-v2-reset-thread'))

    await waitFor(() => {
      expect(confirmSpy).toHaveBeenCalledWith('Reset this thread?')
    })
    expect(resetThread).toHaveBeenCalledTimes(1)
  })
})
