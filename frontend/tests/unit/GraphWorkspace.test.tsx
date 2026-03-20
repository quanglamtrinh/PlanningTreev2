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
    setActiveNode: vi.fn(),
    createChild: vi.fn(),
    splitNode: vi.fn(),
    updateNode: vi.fn(),
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
    isResetDisabled,
    isResettingProject,
    onSplitNode,
    onOpenBreadcrumb,
    onFinishTask,
    onResetProject,
  }: {
    snapshot: { tree_state: { root_node_id: string } }
    selectedNodeId: string | null
    isResetDisabled: boolean
    isResettingProject: boolean
    onSplitNode: (
      nodeId: string,
      mode: 'workflow' | 'simplify_workflow' | 'phase_breakdown' | 'agent_breakdown',
    ) => Promise<void>
    onOpenBreadcrumb: (nodeId: string) => Promise<void>
    onFinishTask: (nodeId: string) => Promise<void>
    onResetProject: () => Promise<void>
  }) => (
    <div data-testid="tree-graph">
      <div data-testid={`root-node-${snapshot.tree_state.root_node_id}`}>
        {snapshot.tree_state.root_node_id}
      </div>
      <div data-testid="selected-node-id">{selectedNodeId}</div>
      <button onClick={() => void onSplitNode(snapshot.tree_state.root_node_id, 'workflow')}>
        Split Root
      </button>
      <button onClick={() => void onOpenBreadcrumb(snapshot.tree_state.root_node_id)}>
        Open Root Breadcrumb
      </button>
      <button
        disabled={!selectedNodeId}
        onClick={() => {
          if (!selectedNodeId) {
            return
          }
          void onOpenBreadcrumb(selectedNodeId)
        }}
      >
        Open Selected Breadcrumb
      </button>
      <button onClick={() => void onFinishTask(snapshot.tree_state.root_node_id)}>
        Finish Root Task
      </button>
      <button disabled={isResetDisabled} onClick={() => void onResetProject()}>
        {isResettingProject ? 'Resetting...' : 'Reset to Root'}
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

function makeProjectSummary(
  id: string,
  name: string,
  projectWorkspaceRoot: string,
  updatedAt: string,
) {
  return {
    id,
    name,
    root_goal: `Goal for ${name}`,
    base_workspace_root: 'C:/workspace',
    project_workspace_root: projectWorkspaceRoot,
    created_at: updatedAt,
    updated_at: updatedAt,
  }
}

function makeGraphSnapshot(
  project: ReturnType<typeof makeProjectSummary>,
  rootNodeId: string,
  activeNodeId: string,
  nodeRegistry: Array<Record<string, unknown>>,
) {
  return {
    schema_version: 2,
    project: {
      ...project,
    },
    tree_state: {
      root_node_id: rootNodeId,
      active_node_id: activeNodeId,
      node_registry: nodeRegistry,
    },
    updated_at: project.updated_at,
  }
}

describe('GraphWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const mockFn of Object.values(apiMock)) {
      mockFn.mockReset()
    }
    useProjectStore.setState(useProjectStore.getInitialState())
    useUIStore.setState(useUIStore.getInitialState())
    apiMock.getPlanningHistory.mockResolvedValue({ node_id: 'root', turns: [] })
    apiMock.planningEventsUrl.mockReturnValue('/v1/projects/project-1/nodes/root/planning/events')
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

  it('switches the rendered graph when the active project changes from the sidebar', async () => {
    const alphaProject = makeProjectSummary(
      'project-1',
      'Alpha',
      'C:/workspace/alpha-app',
      '2026-03-07T10:00:00Z',
    )
    const betaProject = makeProjectSummary(
      'project-2',
      'Beta',
      'C:/workspace/beta-service',
      '2026-03-07T11:00:00Z',
    )
    const alphaSnapshot = makeGraphSnapshot(alphaProject, 'root-1', 'root-1', [
      {
        node_id: 'root-1',
        parent_id: null,
        child_ids: [],
        title: 'Alpha',
        description: alphaProject.root_goal,
        status: 'draft',
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
        created_at: alphaProject.created_at,
      },
    ])
    const betaSnapshot = makeGraphSnapshot(betaProject, 'root-2', 'root-2', [
      {
        node_id: 'root-2',
        parent_id: null,
        child_ids: [],
        title: 'Beta',
        description: betaProject.root_goal,
        status: 'draft',
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
        created_at: betaProject.created_at,
      },
    ])

    apiMock.getSnapshot.mockImplementation(async (projectId: string) =>
      projectId === 'project-2' ? betaSnapshot : alphaSnapshot,
    )

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      projects: [alphaProject, betaProject],
      activeProjectId: 'project-1',
      snapshot: alphaSnapshot,
      selectedNodeId: 'root-1',
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('root-node-root-1')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Beta' }))

    await waitFor(() => {
      expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-2')
      expect(screen.getByTestId('root-node-root-2')).toBeInTheDocument()
    })
  })

  it('collapses the sidebar into a compact Projects rail and expands it again', () => {
    const project = makeProjectSummary(
      'project-1',
      'Alpha',
      'C:/workspace/alpha-app',
      '2026-03-07T10:00:00Z',
    )
    const snapshot = makeGraphSnapshot(project, 'root-1', 'root-1', [
      {
        node_id: 'root-1',
        parent_id: null,
        child_ids: [],
        title: 'Alpha',
        description: project.root_goal,
        status: 'draft',
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
        created_at: project.created_at,
      },
    ])

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      projects: [project],
      activeProjectId: 'project-1',
      snapshot,
      selectedNodeId: 'root-1',
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GraphWorkspace />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Alpha' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Collapse projects sidebar' }))

    expect(screen.queryByRole('button', { name: 'Alpha' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expand projects sidebar' })).toBeInTheDocument()
    expect(screen.getByText('Projects')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Expand projects sidebar' }))

    expect(screen.getByRole('button', { name: 'Alpha' })).toBeInTheDocument()
  })

  it('opens breadcrumb on the newly selected project using that project active-node fallback', async () => {
    const alphaProject = makeProjectSummary(
      'project-1',
      'Alpha',
      'C:/workspace/alpha-app',
      '2026-03-07T10:00:00Z',
    )
    const betaProject = makeProjectSummary(
      'project-2',
      'Beta',
      'C:/workspace/beta-service',
      '2026-03-07T11:00:00Z',
    )
    const alphaSnapshot = makeGraphSnapshot(alphaProject, 'root-1', 'root-1', [
      {
        node_id: 'root-1',
        parent_id: null,
        child_ids: [],
        title: 'Alpha',
        description: alphaProject.root_goal,
        status: 'draft',
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
        created_at: alphaProject.created_at,
      },
    ])
    const betaSnapshot = makeGraphSnapshot(betaProject, 'root-2', 'child-2', [
      {
        node_id: 'root-2',
        parent_id: null,
        child_ids: ['child-2'],
        title: 'Beta',
        description: betaProject.root_goal,
        status: 'draft',
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
        created_at: betaProject.created_at,
      },
      {
        node_id: 'child-2',
        parent_id: 'root-2',
        child_ids: [],
        title: 'Beta Task',
        description: 'Continue the selected task',
        status: 'ready',
        phase: 'planning',
        node_kind: 'original',
        planning_mode: null,
        depth: 1,
        display_order: 0,
        hierarchical_number: '1.1',
        split_metadata: null,
        chat_session_id: null,
        has_planning_thread: true,
        has_execution_thread: true,
        planning_thread_status: 'idle',
        execution_thread_status: 'idle',
        has_ask_thread: true,
        ask_thread_status: 'idle',
        is_superseded: false,
        created_at: betaProject.updated_at,
      },
    ])

    apiMock.getSnapshot.mockImplementation(async (projectId: string) =>
      projectId === 'project-2' ? betaSnapshot : alphaSnapshot,
    )
    apiMock.setActiveNode.mockImplementation(async (projectId: string, nodeId: string) => {
      if (projectId === 'project-2') {
        return {
          ...betaSnapshot,
          tree_state: {
            ...betaSnapshot.tree_state,
            active_node_id: nodeId,
          },
        }
      }
      return alphaSnapshot
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      projects: [alphaProject, betaProject],
      activeProjectId: 'project-1',
      snapshot: alphaSnapshot,
      selectedNodeId: 'root-1',
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LocationProbe />
        <GraphWorkspace />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Beta' }))

    await waitFor(() => {
      expect(screen.getByTestId('selected-node-id')).toHaveTextContent('child-2')
    })

    fireEvent.click(screen.getByRole('button', { name: 'Open Selected Breadcrumb' }))

    await waitFor(() => {
      expect(apiMock.setActiveNode).toHaveBeenCalledWith('project-2', 'child-2')
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-2/nodes/child-2/chat')
    })
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
      mode: 'workflow',
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
      expect(apiMock.splitNode).toHaveBeenCalledWith('project-1', 'root', 'workflow', true)
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
      expect(apiMock.splitNode).toHaveBeenCalledWith('project-1', 'root', 'workflow', false)
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

  it('renders reset only when a project snapshot is loaded and disables it while splitting', () => {
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

    expect(screen.queryByRole('button', { name: 'Reset to Root' })).not.toBeInTheDocument()

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

  it('routes planning nodes to the breadcrumb placeholder without route state', async () => {
    const project = {
      id: 'project-1',
      name: 'Alpha',
      root_goal: 'Ship graph routing',
      base_workspace_root: 'C:/workspace',
      project_workspace_root: 'C:/workspace/alpha',
      created_at: '2026-03-07T10:00:00Z',
      updated_at: '2026-03-07T10:00:00Z',
    }
    const snapshot = {
      schema_version: 2,
      project,
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
    }
    apiMock.setActiveNode.mockResolvedValue(snapshot)

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      projects: [project],
      activeProjectId: 'project-1',
      snapshot,
      selectedNodeId: 'root',
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
    expect(screen.getByTestId('location-state')).toHaveTextContent('null')
  })

  it('routes execution-ready nodes to the breadcrumb placeholder without composer state', async () => {
    const project = {
      id: 'project-1',
      name: 'Alpha',
      root_goal: 'Ship graph routing',
      base_workspace_root: 'C:/workspace',
      project_workspace_root: 'C:/workspace/alpha',
      created_at: '2026-03-07T10:00:00Z',
      updated_at: '2026-03-07T10:00:00Z',
    }
    const snapshot = {
      schema_version: 2,
      project,
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
    }
    apiMock.setActiveNode.mockResolvedValue(snapshot)

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      hasInitialized: true,
      isInitializing: false,
      bootstrap: { ready: true, workspace_configured: true },
      baseWorkspaceRoot: 'C:/workspace',
      projects: [project],
      activeProjectId: 'project-1',
      snapshot,
      selectedNodeId: 'root',
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
    expect(screen.getByTestId('location-state')).toHaveTextContent('null')
  })
})
