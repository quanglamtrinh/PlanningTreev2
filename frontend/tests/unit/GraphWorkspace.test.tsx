import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
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
    createTask: vi.fn(),
    generateFrame: vi.fn(),
    splitNode: vi.fn(),
    getSplitStatus: vi.fn(),
    updateNode: vi.fn(),
    getNodeDocument: vi.fn(),
    putNodeDocument: vi.fn(),
  },
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

vi.mock('../../src/features/graph/TreeGraph', () => ({
  TreeGraph: ({
    snapshot,
    selectedNodeId,
    onOpenBreadcrumb,
    onResetProject,
  }: {
    snapshot: { tree_state: { root_node_id: string } }
    selectedNodeId: string | null
    onOpenBreadcrumb: (nodeId: string) => Promise<void>
    onResetProject: () => Promise<void>
  }) => (
    <div data-testid="tree-graph">
      <div data-testid={`root-node-${snapshot.tree_state.root_node_id}`}>
        {snapshot.tree_state.root_node_id}
      </div>
      <div data-testid="selected-node-id">{selectedNodeId}</div>
      <button onClick={() => void onOpenBreadcrumb(snapshot.tree_state.root_node_id)}>
        Open Root Breadcrumb
      </button>
      <button onClick={() => void onResetProject()}>Reset to Root</button>
    </div>
  ),
}))

import { GraphWorkspace } from '../../src/features/graph/GraphWorkspace'
import { useProjectStore } from '../../src/stores/project-store'
import { useUIStore } from '../../src/stores/ui-store'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-path">{`${location.pathname}${location.search}`}</div>
}

function makeProjectSummary(id: string) {
  return {
    id,
    name: `Project ${id}`,
    root_goal: `Goal ${id}`,
    project_path: `C:/workspace/${id}`,
    created_at: '2026-03-20T00:00:00Z',
    updated_at: '2026-03-20T00:00:00Z',
  }
}

function makeSnapshot(projectId = 'project-1') {
  return {
    schema_version: 6,
    project: makeProjectSummary(projectId),
    tree_state: {
      root_node_id: 'root',
      active_node_id: 'root',
      node_registry: [
        {
          node_id: 'root',
          parent_id: null,
          child_ids: [],
          title: 'Root',
          description: 'Ship it',
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
      ],
    },
    updated_at: '2026-03-20T00:00:00Z',
  }
}

function makeReviewSnapshot(projectId = 'project-1') {
  const snapshot = makeSnapshot(projectId)
  snapshot.tree_state.node_registry[0] = {
    ...snapshot.tree_state.node_registry[0],
    node_kind: 'review',
    title: 'Review Node',
  }
  return snapshot
}

describe('GraphWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const mockFn of Object.values(apiMock)) {
      mockFn.mockReset()
    }
    useProjectStore.setState(useProjectStore.getInitialState())
    useUIStore.setState(useUIStore.getInitialState())
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('shows the empty state when no project folders are attached', () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
      },
      projects: [],
    })

    render(
      <MemoryRouter>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    expect(screen.getByText('No project loaded')).toBeInTheDocument()
    expect(screen.getByText('Add a project folder to get started.')).toBeInTheDocument()
  })

  it('renders a loaded graph after initialization', async () => {
    apiMock.getBootstrapStatus.mockResolvedValue({
      ready: true,
      workspace_configured: true,
      codex_available: true,
      codex_path: 'codex',
    })
    apiMock.listProjects.mockResolvedValue([makeProjectSummary('project-2')])
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('project-2'))
    apiMock.getSplitStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      node_id: null,
      mode: null,
      started_at: null,
      completed_at: null,
      error: null,
    })

    render(
      <MemoryRouter>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    expect(await screen.findByTestId('tree-graph')).toBeInTheDocument()
    expect(screen.getByTestId('root-node-root')).toBeInTheDocument()
    expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-2')
  })

  it('navigates to the breadcrumb placeholder from the graph action', async () => {
    apiMock.getBootstrapStatus.mockResolvedValue({
      ready: true,
      workspace_configured: true,
      codex_available: true,
      codex_path: 'codex',
    })
    apiMock.listProjects.mockResolvedValue([makeProjectSummary('project-1')])
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('project-1'))
    apiMock.setActiveNode.mockResolvedValue(makeSnapshot('project-1'))
    apiMock.getSplitStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      node_id: null,
      mode: null,
      started_at: null,
      completed_at: null,
      error: null,
    })

    render(
      <MemoryRouter>
        <GraphWorkspace />
        <LocationProbe />
      </MemoryRouter>,
    )

    await screen.findByTestId('tree-graph')
    await act(async () => {
      fireEvent.click(screen.getByText('Open Root Breadcrumb'))
    })

    expect(screen.getByTestId('location-path').textContent).toBe('/projects/project-1/nodes/root/chat-v2?thread=ask')
  })

  it('still navigates to breadcrumb when persisting the active node fails', async () => {
    apiMock.getBootstrapStatus.mockResolvedValue({
      ready: true,
      workspace_configured: true,
      codex_available: false,
      codex_path: null,
    })
    apiMock.listProjects.mockResolvedValue([makeProjectSummary('project-1')])
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('project-1'))
    apiMock.setActiveNode.mockRejectedValue(new Error('selection failed'))
    apiMock.getSplitStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      node_id: null,
      mode: null,
      started_at: null,
      completed_at: null,
      error: null,
    })

    render(
      <MemoryRouter>
        <GraphWorkspace />
        <LocationProbe />
      </MemoryRouter>,
    )

    await screen.findByTestId('tree-graph')
    await act(async () => {
      fireEvent.click(screen.getByText('Open Root Breadcrumb'))
    })

    expect(screen.getByTestId('location-path').textContent).toBe('/projects/project-1/nodes/root/chat-v2?thread=ask')
  })

  it('routes review-node breadcrumb entry to chat-v2 audit', async () => {
    apiMock.getBootstrapStatus.mockResolvedValue({
      ready: true,
      workspace_configured: true,
      codex_available: true,
      codex_path: 'codex',
    })
    apiMock.listProjects.mockResolvedValue([makeProjectSummary('project-1')])
    apiMock.getSnapshot.mockResolvedValue(makeReviewSnapshot('project-1'))
    apiMock.setActiveNode.mockResolvedValue(makeReviewSnapshot('project-1'))
    apiMock.getSplitStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      node_id: null,
      mode: null,
      started_at: null,
      completed_at: null,
      error: null,
    })

    render(
      <MemoryRouter>
        <GraphWorkspace />
        <LocationProbe />
      </MemoryRouter>,
    )

    await screen.findByTestId('tree-graph')
    await act(async () => {
      fireEvent.click(screen.getByText('Open Root Breadcrumb'))
    })

    expect(screen.getByTestId('location-path').textContent).toBe('/projects/project-1/nodes/root/chat-v2?thread=audit')
  })

  it('routes review-node breadcrumb entry to chat-v2 audit without gate flags', async () => {
    apiMock.getBootstrapStatus.mockResolvedValue({
      ready: true,
      workspace_configured: true,
      codex_available: true,
      codex_path: 'codex',
    })
    apiMock.listProjects.mockResolvedValue([makeProjectSummary('project-1')])
    apiMock.getSnapshot.mockResolvedValue(makeReviewSnapshot('project-1'))
    apiMock.setActiveNode.mockResolvedValue(makeReviewSnapshot('project-1'))
    apiMock.getSplitStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      node_id: null,
      mode: null,
      started_at: null,
      completed_at: null,
      error: null,
    })

    render(
      <MemoryRouter>
        <GraphWorkspace />
        <LocationProbe />
      </MemoryRouter>,
    )

    await screen.findByTestId('tree-graph')
    await act(async () => {
      fireEvent.click(screen.getByText('Open Root Breadcrumb'))
    })

    expect(screen.getByTestId('location-path').textContent).toBe('/projects/project-1/nodes/root/chat-v2?thread=audit')
  })

  it('auto-redirects out of graph when split finishes', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
      },
      projects: [makeProjectSummary('project-1')],
      activeProjectId: 'project-1',
      snapshot: makeSnapshot('project-1'),
      selectedNodeId: 'root',
      splitStatus: 'active',
      splitNodeId: 'root',
    })

    render(
      <MemoryRouter initialEntries={['/graph']}>
        <GraphWorkspace />
        <LocationProbe />
      </MemoryRouter>,
    )

    await screen.findByTestId('tree-graph')

    await act(async () => {
      useProjectStore.setState({
        splitStatus: 'idle',
        splitNodeId: null,
      })
    })

    await waitFor(() => {
      expect(screen.getByTestId('location-path').textContent).toBe(
        '/projects/project-1/nodes/root/chat-v2?thread=ask',
      )
    })
  })
})
