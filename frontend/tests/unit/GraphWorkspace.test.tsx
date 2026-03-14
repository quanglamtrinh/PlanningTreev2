import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getBootstrapStatus: vi.fn(),
    getWorkspaceSettings: vi.fn(),
    setWorkspaceRoot: vi.fn(),
    listProjects: vi.fn(),
    createProject: vi.fn(),
    getSnapshot: vi.fn(),
    resetProjectToRoot: vi.fn(),
    getPlanningHistory: vi.fn(),
    planningEventsUrl: vi.fn(),
    agentEventsUrl: vi.fn(),
    setActiveNode: vi.fn(),
    createChild: vi.fn(),
    splitNode: vi.fn(),
    updateNode: vi.fn(),
    completeNode: vi.fn(),
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
    onSplitNode,
    onOpenBreadcrumb,
    onFinishTask,
  }: {
    snapshot: { tree_state: { root_node_id: string } }
    onSplitNode: (nodeId: string, mode: 'walking_skeleton' | 'slice') => Promise<void>
    onOpenBreadcrumb: (nodeId: string) => Promise<void>
    onFinishTask: (nodeId: string) => Promise<void>
  }) => (
    <div data-testid="tree-graph">
      <div data-testid={`root-node-${snapshot.tree_state.root_node_id}`}>
        {snapshot.tree_state.root_node_id}
      </div>
      <button onClick={() => void onSplitNode(snapshot.tree_state.root_node_id, 'slice')}>
        Split Root
      </button>
      <button onClick={() => void onOpenBreadcrumb(snapshot.tree_state.root_node_id)}>
        Open Root Breadcrumb
      </button>
      <button onClick={() => void onFinishTask(snapshot.tree_state.root_node_id)}>
        Finish Root Task
      </button>
    </div>
  ),
}))

import { GraphWorkspace } from '../../src/features/graph/GraphWorkspace'
import { useProjectStore } from '../../src/stores/project-store'
import { useUIStore } from '../../src/stores/ui-store'

function LocationProbe() {
  const location = useLocation()
  return (
    <div>
      <div data-testid="location-path">{location.pathname}</div>
      <div data-testid="location-state">{JSON.stringify(location.state ?? null)}</div>
    </div>
  )
}

describe('GraphWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
    useUIStore.setState(useUIStore.getInitialState())
    apiMock.getPlanningHistory.mockResolvedValue({ node_id: 'root', turns: [] })
    apiMock.planningEventsUrl.mockReturnValue('/v1/projects/project-1/nodes/root/planning/events')
    apiMock.agentEventsUrl.mockReturnValue('/v1/projects/project-1/nodes/root/agent/events')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('gates into workspace setup when bootstrap is not configured', () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: false, workspace_configured: false },
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    expect(screen.getByText('Choose a base workspace folder')).toBeInTheDocument()
    expect(screen.getByText('Save Workspace')).toBeInTheDocument()
  })

  it('renders a loaded graph when projects exist and no project is persisted', async () => {
    apiMock.getBootstrapStatus.mockResolvedValue({ ready: true, workspace_configured: true })
    apiMock.getWorkspaceSettings.mockResolvedValue({ base_workspace_root: 'C:/workspace' })
    apiMock.listProjects.mockResolvedValue([
      {
        id: 'project-2',
        name: 'Newest Project',
        root_goal: 'Ship the graph shell',
        base_workspace_root: 'C:/workspace',
        project_workspace_root: 'C:/workspace/newest-project',
        created_at: '2026-03-07T11:00:00Z',
        updated_at: '2026-03-07T11:00:00Z',
      },
      {
        id: 'project-1',
        name: 'Older Project',
        root_goal: 'Older goal',
        base_workspace_root: 'C:/workspace',
        project_workspace_root: 'C:/workspace/older-project',
        created_at: '2026-03-07T10:00:00Z',
        updated_at: '2026-03-07T10:00:00Z',
      },
    ])
    apiMock.getSnapshot.mockResolvedValue({
      schema_version: 2,
      project: {
        id: 'project-2',
        name: 'Newest Project',
        root_goal: 'Ship the graph shell',
        base_workspace_root: 'C:/workspace',
        project_workspace_root: 'C:/workspace/newest-project',
        created_at: '2026-03-07T11:00:00Z',
        updated_at: '2026-03-07T11:00:00Z',
      },
      tree_state: {
        root_node_id: 'root-2',
        active_node_id: 'root-2',
        node_registry: [
          {
            node_id: 'root-2',
            parent_id: null,
            child_ids: [],
            title: 'Newest Project',
            description: 'Ship the graph shell',
            status: 'draft',
            planning_mode: null,
            depth: 0,
            display_order: 0,
            hierarchical_number: '1',
            split_metadata: null,
            chat_session_id: null,
            has_ask_thread: false,
            ask_thread_status: null,
            is_superseded: false,
            created_at: '2026-03-07T11:00:00Z',
          },
        ],
      },
      updated_at: '2026-03-07T11:00:00Z',
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    expect(await screen.findByTestId('tree-graph')).toBeInTheDocument()
    expect(screen.getByTestId('root-node-root-2')).toBeInTheDocument()
    expect(screen.queryByText('No project loaded')).not.toBeInTheDocument()
    expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-2')
  })

  it('splits without touching the legacy node update route', async () => {
    const initialSnapshot = {
      schema_version: 2,
      project: {
        id: 'project-1',
        name: 'Alpha',
        root_goal: 'Ship split flow',
        base_workspace_root: 'C:/workspace',
        project_workspace_root: 'C:/workspace/alpha',
        created_at: '2026-03-07T10:00:00Z',
        updated_at: '2026-03-07T10:00:00Z',
      },
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          {
            node_id: 'root',
            parent_id: null,
            child_ids: ['child-1'],
            title: 'Alpha',
            description: 'Ship split flow',
            status: 'draft',
            planning_mode: null,
            depth: 0,
            display_order: 0,
            hierarchical_number: '1',
            split_metadata: null,
            chat_session_id: null,
            has_ask_thread: false,
            ask_thread_status: null,
            is_superseded: false,
            created_at: '2026-03-07T10:00:00Z',
          },
          {
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Existing child',
            description: '',
            status: 'ready',
            planning_mode: null,
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            split_metadata: null,
            chat_session_id: null,
            has_ask_thread: false,
            ask_thread_status: null,
            is_superseded: false,
            created_at: '2026-03-07T10:01:00Z',
          },
        ],
      },
      updated_at: '2026-03-07T10:00:00Z',
    }
    apiMock.splitNode.mockResolvedValue({
      status: 'accepted',
      node_id: 'root',
      mode: 'slice',
      planning_status: 'active',
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      activeProjectId: 'project-1',
      snapshot: initialSnapshot,
      selectedNodeId: 'root',
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Split Root' }))

    expect(window.confirm).toHaveBeenCalled()
    await waitFor(() => {
      expect(apiMock.splitNode).toHaveBeenCalledWith('project-1', 'root', 'slice', true)
    })
    expect(apiMock.updateNode).not.toHaveBeenCalled()
  })

  it('cancels re-split when confirmation is declined', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    const snapshot = {
      schema_version: 2,
      project: {
        id: 'project-1',
        name: 'Alpha',
        root_goal: 'Ship split flow',
        base_workspace_root: 'C:/workspace',
        project_workspace_root: 'C:/workspace/alpha',
        created_at: '2026-03-07T10:00:00Z',
        updated_at: '2026-03-07T10:00:00Z',
      },
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          {
            node_id: 'root',
            parent_id: null,
            child_ids: ['child-1'],
            title: 'Alpha',
            description: 'Ship split flow',
            status: 'draft',
            planning_mode: null,
            depth: 0,
            display_order: 0,
            hierarchical_number: '1',
            split_metadata: null,
            chat_session_id: null,
            has_ask_thread: false,
            ask_thread_status: null,
            is_superseded: false,
            created_at: '2026-03-07T10:00:00Z',
          },
          {
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Existing child',
            description: '',
            status: 'ready',
            planning_mode: null,
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            split_metadata: null,
            chat_session_id: null,
            has_ask_thread: false,
            ask_thread_status: null,
            is_superseded: false,
            created_at: '2026-03-07T10:01:00Z',
          },
        ],
      },
      updated_at: '2026-03-07T10:00:00Z',
    }

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      activeProjectId: 'project-1',
      snapshot,
      selectedNodeId: 'root',
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Split Root' }))

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalled()
    })
    expect(apiMock.splitNode).not.toHaveBeenCalled()
  })

  it('contains split failures without leaking rejected promises', async () => {
    apiMock.splitNode.mockRejectedValue(new Error('split failed'))

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      activeProjectId: 'project-1',
      snapshot: {
        schema_version: 2,
        project: {
          id: 'project-1',
          name: 'Alpha',
          root_goal: 'Ship split flow',
          base_workspace_root: 'C:/workspace',
          project_workspace_root: 'C:/workspace/alpha',
          created_at: '2026-03-07T10:00:00Z',
          updated_at: '2026-03-07T10:00:00Z',
        },
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'root',
          node_registry: [
            {
              node_id: 'root',
              parent_id: null,
              child_ids: [],
              title: 'Alpha',
              description: 'Ship split flow',
              status: 'draft',
              planning_mode: null,
              depth: 0,
              display_order: 0,
              hierarchical_number: '1',
              split_metadata: null,
              chat_session_id: null,
              has_ask_thread: false,
              ask_thread_status: null,
              is_superseded: false,
              created_at: '2026-03-07T10:00:00Z',
            },
          ],
        },
        updated_at: '2026-03-07T10:00:00Z',
      },
      selectedNodeId: 'root',
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Split Root' }))

    await waitFor(() => {
      expect(apiMock.splitNode).toHaveBeenCalledWith('project-1', 'root', 'slice', false)
    })
    expect(await screen.findByText('split failed')).toBeInTheDocument()
  })

  it('resets the project without touching the legacy node update route', async () => {
    const initialSnapshot = {
      schema_version: 2,
      project: {
        id: 'project-1',
        name: 'Alpha',
        root_goal: 'Ship reset flow',
        base_workspace_root: 'C:/workspace',
        project_workspace_root: 'C:/workspace/alpha',
        created_at: '2026-03-07T10:00:00Z',
        updated_at: '2026-03-07T10:00:00Z',
      },
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'child-1',
        node_registry: [
          {
            node_id: 'root',
            parent_id: null,
            child_ids: ['child-1'],
            title: 'Alpha',
            description: 'Ship reset flow',
            status: 'draft',
            planning_mode: null,
            depth: 0,
            display_order: 0,
            hierarchical_number: '1',
            split_metadata: null,
            chat_session_id: null,
            has_ask_thread: false,
            ask_thread_status: null,
            is_superseded: false,
            created_at: '2026-03-07T10:00:00Z',
          },
          {
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Child',
            description: '',
            status: 'ready',
            planning_mode: null,
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            split_metadata: null,
            chat_session_id: null,
            has_ask_thread: false,
            ask_thread_status: null,
            is_superseded: false,
            created_at: '2026-03-07T10:01:00Z',
          },
        ],
      },
      updated_at: '2026-03-07T10:00:00Z',
    }
    const resetSnapshot = {
      ...initialSnapshot,
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          {
            ...initialSnapshot.tree_state.node_registry[0],
            child_ids: [],
          },
        ],
      },
    }

    apiMock.resetProjectToRoot.mockResolvedValue(resetSnapshot)

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      activeProjectId: 'project-1',
      snapshot: initialSnapshot,
      selectedNodeId: 'root',
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Reset to Root' }))

    expect(window.confirm).toHaveBeenCalledWith(
      'Reset this project to its root node? This will delete all child nodes and clear planning/chat history.',
    )
    await waitFor(() => {
      expect(apiMock.resetProjectToRoot).toHaveBeenCalledWith('project-1')
    })
    expect(apiMock.updateNode).not.toHaveBeenCalled()
  })

  it('does not reset the project when confirmation is declined', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      activeProjectId: 'project-1',
      snapshot: {
        schema_version: 2,
        project: {
          id: 'project-1',
          name: 'Alpha',
          root_goal: 'Ship reset flow',
          base_workspace_root: 'C:/workspace',
          project_workspace_root: 'C:/workspace/alpha',
          created_at: '2026-03-07T10:00:00Z',
          updated_at: '2026-03-07T10:00:00Z',
        },
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'root',
          node_registry: [
            {
              node_id: 'root',
              parent_id: null,
              child_ids: [],
              title: 'Alpha',
              description: 'Ship reset flow',
              status: 'draft',
              planning_mode: null,
              depth: 0,
              display_order: 0,
              hierarchical_number: '1',
              split_metadata: null,
              chat_session_id: null,
              has_ask_thread: false,
              ask_thread_status: null,
              is_superseded: false,
              created_at: '2026-03-07T10:00:00Z',
            },
          ],
        },
        updated_at: '2026-03-07T10:00:00Z',
      },
      selectedNodeId: 'root',
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Reset to Root' }))

    expect(window.confirm).toHaveBeenCalled()
    expect(apiMock.resetProjectToRoot).not.toHaveBeenCalled()
  })

  it('disables reset while splitting or when no project is loaded', () => {
    act(() => {
      useProjectStore.setState({
        ...useProjectStore.getInitialState(),
        hasInitialized: true,
        isInitializing: false,
        bootstrap: { ready: true, workspace_configured: true },
        activeProjectId: null,
        snapshot: null,
        initialize: vi.fn(async () => {}),
      })
    })

    const { rerender } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Reset to Root' })).toBeDisabled()

    act(() => {
      useProjectStore.setState({
        ...useProjectStore.getInitialState(),
        hasInitialized: true,
        isInitializing: false,
        bootstrap: { ready: true, workspace_configured: true },
        activeProjectId: 'project-1',
        isSplittingNode: true,
        splittingNodeId: 'root',
        selectedNodeId: 'root',
        initialize: vi.fn(async () => {}),
        snapshot: {
          schema_version: 2,
          project: {
            id: 'project-1',
            name: 'Alpha',
            root_goal: 'Ship reset flow',
            base_workspace_root: 'C:/workspace',
            project_workspace_root: 'C:/workspace/alpha',
            created_at: '2026-03-07T10:00:00Z',
            updated_at: '2026-03-07T10:00:00Z',
          },
          tree_state: {
            root_node_id: 'root',
            active_node_id: 'root',
            node_registry: [
              {
                node_id: 'root',
                parent_id: null,
                child_ids: [],
                title: 'Alpha',
                description: 'Ship reset flow',
                status: 'draft',
                planning_mode: null,
                depth: 0,
                display_order: 0,
                hierarchical_number: '1',
                split_metadata: null,
                chat_session_id: null,
                has_ask_thread: false,
                ask_thread_status: null,
                is_superseded: false,
                created_at: '2026-03-07T10:00:00Z',
              },
            ],
          },
          updated_at: '2026-03-07T10:00:00Z',
        },
      })
    })

    rerender(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Reset to Root' })).toBeDisabled()
  })

  it('routes planning nodes to the task tab without seeding a composer draft', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      activeProjectId: 'project-1',
      snapshot: {
        schema_version: 2,
        project: {
          id: 'project-1',
          name: 'Alpha',
          root_goal: 'Ship graph routing',
          base_workspace_root: 'C:/workspace',
          project_workspace_root: 'C:/workspace/alpha',
          created_at: '2026-03-07T10:00:00Z',
          updated_at: '2026-03-07T10:00:00Z',
        },
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'root',
          node_registry: [
            {
              node_id: 'root',
              parent_id: null,
              child_ids: [],
              title: 'Alpha',
              description: 'Ship graph routing',
              status: 'ready',
              phase: 'planning',
              node_kind: 'root',
              planning_mode: null,
              depth: 0,
              display_order: 0,
              hierarchical_number: '1',
              split_metadata: null,
              chat_session_id: null,
              has_planning_thread: false,
              has_execution_thread: false,
              planning_thread_status: null,
              execution_thread_status: null,
              has_ask_thread: false,
              ask_thread_status: null,
              is_superseded: false,
              created_at: '2026-03-07T10:00:00Z',
            },
          ],
        },
        updated_at: '2026-03-07T10:00:00Z',
      },
      selectedNodeId: 'root',
      selectNode: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LocationProbe />
        <GraphWorkspace />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Finish Root Task' }))

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-1/nodes/root/chat')
    })
    expect(screen.getByTestId('location-state')).toHaveTextContent('"activeTab":"task"')
    expect(screen.getByTestId('location-state')).not.toHaveTextContent('composerSeed')
  })

  it('routes execution-ready nodes to the execution tab and seeds the composer draft', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      activeProjectId: 'project-1',
      snapshot: {
        schema_version: 2,
        project: {
          id: 'project-1',
          name: 'Alpha',
          root_goal: 'Ship graph routing',
          base_workspace_root: 'C:/workspace',
          project_workspace_root: 'C:/workspace/alpha',
          created_at: '2026-03-07T10:00:00Z',
          updated_at: '2026-03-07T10:00:00Z',
        },
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'root',
          node_registry: [
            {
              node_id: 'root',
              parent_id: null,
              child_ids: [],
              title: 'Alpha',
              description: 'Ship graph routing',
              status: 'ready',
              phase: 'ready_for_execution',
              node_kind: 'root',
              planning_mode: null,
              depth: 0,
              display_order: 0,
              hierarchical_number: '1',
              split_metadata: null,
              chat_session_id: null,
              has_planning_thread: false,
              has_execution_thread: false,
              planning_thread_status: null,
              execution_thread_status: null,
              has_ask_thread: false,
              ask_thread_status: null,
              is_superseded: false,
              created_at: '2026-03-07T10:00:00Z',
            },
          ],
        },
        updated_at: '2026-03-07T10:00:00Z',
      },
      selectedNodeId: 'root',
      selectNode: vi.fn(async () => {}),
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LocationProbe />
        <GraphWorkspace />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Finish Root Task' }))

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-1/nodes/root/chat')
    })
    expect(screen.getByTestId('location-state')).toHaveTextContent('"activeTab":"execution"')
    expect(screen.getByTestId('location-state')).toHaveTextContent('Task: Alpha')
  })
})
