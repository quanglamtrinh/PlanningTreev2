import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getBootstrapStatus: vi.fn(),
    getWorkspaceSettings: vi.fn(),
    setWorkspaceRoot: vi.fn(),
    listProjects: vi.fn(),
    createProject: vi.fn(),
    getSnapshot: vi.fn(),
    getPlanningHistory: vi.fn(),
    resetProjectToRoot: vi.fn(),
    setActiveNode: vi.fn(),
    createChild: vi.fn(),
    splitNode: vi.fn(),
    updateNode: vi.fn(),
    updateNodeTask: vi.fn(),
    getNodeDocuments: vi.fn(),
    updateNodeBriefing: vi.fn(),
    updateNodeSpec: vi.fn(),
    confirmTask: vi.fn(),
    confirmBriefing: vi.fn(),
    confirmSpec: vi.fn(),
    generateNodeSpec: vi.fn(),
    startExecution: vi.fn(),
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

import type { ProjectSummary, Snapshot } from '../../src/api/types'
import { useProjectStore } from '../../src/stores/project-store'

function makeNodeState(
  overrides: Partial<{
    phase: 'planning' | 'briefing_review' | 'spec_review' | 'ready_for_execution' | 'executing' | 'closed'
    task_confirmed: boolean
    briefing_confirmed: boolean
    spec_generated: boolean
    spec_generation_status: 'idle' | 'generating' | 'failed'
    spec_confirmed: boolean
    planning_thread_id: string
    execution_thread_id: string
    ask_thread_id: string
    planning_thread_forked_from_node: string
    planning_thread_bootstrapped_at: string
    chat_session_id: string
  }> = {},
) {
  return {
    phase: 'planning' as const,
    task_confirmed: false,
    briefing_confirmed: false,
    spec_generated: false,
    spec_generation_status: 'idle' as const,
    spec_confirmed: false,
    planning_thread_id: '',
    execution_thread_id: '',
    ask_thread_id: '',
    planning_thread_forked_from_node: '',
    planning_thread_bootstrapped_at: '',
    chat_session_id: '',
    ...overrides,
  }
}

function makeDocuments(
  overrides: Partial<{
    task: { title: string; purpose: string; responsibility: string }
    briefing: {
      user_notes: string
      business_context: string
      technical_context: string
      execution_context: string
      clarified_answers: string
    }
    spec: {
      business_contract: string
      technical_contract: string
      delivery_acceptance: string
      assumptions: string
    }
    state: ReturnType<typeof makeNodeState>
  }> = {},
) {
  return {
    task: {
      title: 'Alpha',
      purpose: 'Ship phase 3',
      responsibility: '',
      ...(overrides.task ?? {}),
    },
    briefing: {
      user_notes: '',
      business_context: '',
      technical_context: '',
      execution_context: '',
      clarified_answers: '',
      ...(overrides.briefing ?? {}),
    },
    spec: {
      business_contract: '',
      technical_contract: '',
      delivery_acceptance: '',
      assumptions: '',
      ...(overrides.spec ?? {}),
    },
    state: makeNodeState(overrides.state),
  }
}

function makeProject(id: string, name: string, updatedAt: string): ProjectSummary {
  return {
    id,
    name,
    root_goal: `Goal for ${name}`,
    base_workspace_root: 'C:/workspace',
    project_workspace_root: `C:/workspace/${name.toLowerCase().replace(/\s+/g, '-')}`,
    created_at: updatedAt,
    updated_at: updatedAt,
  }
}

function makeSnapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    schema_version: 2,
    project: {
      id: 'project-1',
      name: 'Alpha',
      root_goal: 'Ship phase 3',
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
          description: 'Ship phase 3',
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
          created_at: '2026-03-07T10:00:00Z',
        },
      ],
    },
    updated_at: '2026-03-07T10:00:00Z',
    ...overrides,
  }
}

describe('project-store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
  })

  it('initializes configured workspace and loads the single project snapshot', async () => {
    const project: ProjectSummary = {
      id: 'project-1',
      name: 'Alpha',
      root_goal: 'Ship phase 3',
      base_workspace_root: 'C:/workspace',
      project_workspace_root: 'C:/workspace/alpha',
      created_at: '2026-03-07T10:00:00Z',
      updated_at: '2026-03-07T10:00:00Z',
    }
    const snapshot = makeSnapshot()

    apiMock.getBootstrapStatus.mockResolvedValue({ ready: true, workspace_configured: true })
    apiMock.getWorkspaceSettings.mockResolvedValue({ base_workspace_root: 'C:/workspace' })
    apiMock.listProjects.mockResolvedValue([project])
    apiMock.getSnapshot.mockResolvedValue(snapshot)

    await act(async () => {
      await useProjectStore.getState().initialize()
    })

    const state = useProjectStore.getState()
    expect(state.baseWorkspaceRoot).toBe('C:/workspace')
    expect(state.projects).toEqual([project])
    expect(state.activeProjectId).toBe('project-1')
    expect(state.snapshot?.tree_state.root_node_id).toBe('root')
    expect(state.selectedNodeId).toBe('root')
  })

  it('initializes with the newest project when multiple projects exist and none is persisted', async () => {
    const newestProject = makeProject('project-2', 'Newest Project', '2026-03-07T11:00:00Z')
    const olderProject = makeProject('project-1', 'Older Project', '2026-03-07T10:00:00Z')
    const newestSnapshot = makeSnapshot({
      project: {
        ...makeSnapshot().project,
        id: newestProject.id,
        name: newestProject.name,
        root_goal: newestProject.root_goal,
        project_workspace_root: newestProject.project_workspace_root,
        updated_at: newestProject.updated_at,
      },
      tree_state: {
        root_node_id: 'root-2',
        active_node_id: 'root-2',
        node_registry: [
          {
            ...makeSnapshot().tree_state.node_registry[0],
            node_id: 'root-2',
            title: newestProject.name,
            description: newestProject.root_goal,
          },
        ],
      },
    })

    apiMock.getBootstrapStatus.mockResolvedValue({ ready: true, workspace_configured: true })
    apiMock.getWorkspaceSettings.mockResolvedValue({ base_workspace_root: 'C:/workspace' })
    apiMock.listProjects.mockResolvedValue([newestProject, olderProject])
    apiMock.getSnapshot.mockResolvedValue(newestSnapshot)

    await act(async () => {
      await useProjectStore.getState().initialize()
    })

    const state = useProjectStore.getState()
    expect(state.activeProjectId).toBe('project-2')
    expect(state.snapshot?.project.id).toBe('project-2')
    expect(state.selectedNodeId).toBe('root-2')
    expect(window.localStorage.getItem('planningtree.active-project-id')).toBe('project-2')
  })

  it('falls back to the newest project when the persisted project id is stale', async () => {
    const newestProject = makeProject('project-2', 'Newest Project', '2026-03-07T11:00:00Z')
    const olderProject = makeProject('project-1', 'Older Project', '2026-03-07T10:00:00Z')

    apiMock.getBootstrapStatus.mockResolvedValue({ ready: true, workspace_configured: true })
    apiMock.getWorkspaceSettings.mockResolvedValue({ base_workspace_root: 'C:/workspace' })
    apiMock.listProjects.mockResolvedValue([newestProject, olderProject])
    apiMock.getSnapshot.mockResolvedValue(
      makeSnapshot({
        project: {
          ...makeSnapshot().project,
          id: newestProject.id,
          name: newestProject.name,
          root_goal: newestProject.root_goal,
          project_workspace_root: newestProject.project_workspace_root,
          updated_at: newestProject.updated_at,
        },
      }),
    )

    window.localStorage.setItem('planningtree.active-project-id', 'missing-project')

    await act(async () => {
      await useProjectStore.getState().initialize()
    })

    expect(useProjectStore.getState().activeProjectId).toBe('project-2')
    expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-2')
    expect(window.localStorage.getItem('planningtree.active-project-id')).toBe('project-2')
  })

  it('selects the backend active node after creating a child', async () => {
    const initialSnapshot = makeSnapshot()
    const childSnapshot = makeSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'child-1',
        node_registry: [
          {
            ...initialSnapshot.tree_state.node_registry[0],
            child_ids: ['child-1'],
            status: 'draft',
          },
          {
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'New Node',
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
            created_at: '2026-03-07T10:05:00Z',
          },
        ],
      },
      updated_at: '2026-03-07T10:05:00Z',
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: initialSnapshot,
      selectedNodeId: 'root',
    })

    apiMock.createChild.mockResolvedValue(childSnapshot)

    await act(async () => {
      await useProjectStore.getState().createChild('root')
    })

    const state = useProjectStore.getState()
    expect(state.snapshot?.tree_state.active_node_id).toBe('child-1')
    expect(state.selectedNodeId).toBe('child-1')
  })

  it('keeps split loading active until the planning completion event refreshes history and snapshot', async () => {
    const initialSnapshot = makeSnapshot()
    const splitSnapshot = makeSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'workflow-1',
        node_registry: [
          {
            ...initialSnapshot.tree_state.node_registry[0],
            child_ids: ['workflow-1', 'workflow-2', 'workflow-3'],
            planning_mode: 'workflow',
            split_metadata: {
              mode: 'workflow',
              output_family: 'flat_subtasks_v1',
              source: 'model',
              warnings: [],
              created_child_ids: ['workflow-1', 'workflow-2', 'workflow-3'],
              replaced_child_ids: [],
              created_at: '2026-03-07T10:05:00Z',
              revision: 1,
              materialized: {
                family: 'flat_subtasks_v1',
                subtasks: [
                  {
                    subtask_id: 'S1',
                    title: 'Setup',
                    objective: 'Prepare the workspace and plan execution order.',
                    why_now: 'This unlocks the implementation steps.',
                    child_node_id: 'workflow-1',
                    display_order: 0,
                  },
                  {
                    subtask_id: 'S2',
                    title: 'Implement',
                    objective: 'Ship the main implementation slice.',
                    why_now: 'This is the core delivery path.',
                    child_node_id: 'workflow-2',
                    display_order: 1,
                  },
                  {
                    subtask_id: 'S3',
                    title: 'Verify',
                    objective: 'Validate behavior and finish the handoff.',
                    why_now: 'This closes the loop before execution continues.',
                    child_node_id: 'workflow-3',
                    display_order: 2,
                  },
                ],
              },
            },
          },
          {
            node_id: 'workflow-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Setup',
            description: 'Prepare the workspace and plan execution order.\n\nWhy now: This unlocks the implementation steps.',
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
            created_at: '2026-03-07T10:05:00Z',
          },
          {
            node_id: 'workflow-2',
            parent_id: 'root',
            child_ids: [],
            title: 'Implement',
            description: 'Ship the main implementation slice.\n\nWhy now: This is the core delivery path.',
            status: 'locked',
            planning_mode: null,
            depth: 1,
            display_order: 1,
            hierarchical_number: '1.2',
            split_metadata: null,
            chat_session_id: null,
            has_ask_thread: false,
            ask_thread_status: null,
            is_superseded: false,
            created_at: '2026-03-07T10:05:00Z',
          },
          {
            node_id: 'workflow-3',
            parent_id: 'root',
            child_ids: [],
            title: 'Verify',
            description: 'Validate behavior and finish the handoff.\n\nWhy now: This closes the loop before execution continues.',
            status: 'locked',
            planning_mode: null,
            depth: 1,
            display_order: 2,
            hierarchical_number: '1.3',
            split_metadata: null,
            chat_session_id: null,
            has_ask_thread: false,
            ask_thread_status: null,
            is_superseded: false,
            created_at: '2026-03-07T10:05:00Z',
          },
        ],
      },
      updated_at: '2026-03-07T10:05:00Z',
    })

    apiMock.splitNode.mockResolvedValue({
      status: 'accepted',
      node_id: 'root',
      mode: 'workflow',
      planning_status: 'active',
    })
    apiMock.getPlanningHistory.mockResolvedValue({
      node_id: 'root',
      turns: [
        {
          turn_id: 'turn-1',
          role: 'tool_call',
          tool_name: 'emit_render_data',
          is_inherited: false,
          origin_node_id: 'root',
          arguments: {
            kind: 'split_result',
            payload: {
              subtasks: [
                {
                  id: 'S1',
                  title: 'Setup',
                  objective: 'Prepare the workspace and plan execution order.',
                  why_now: 'This unlocks the implementation steps.',
                },
              ],
            },
          },
          timestamp: '2026-03-07T10:05:00Z',
        },
      ],
    })
    apiMock.getSnapshot.mockResolvedValue(splitSnapshot)

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: initialSnapshot,
      selectedNodeId: 'root',
      nodeDrafts: { root: { title: 'Draft title' } },
    })

    await act(async () => {
      await useProjectStore.getState().splitNode('root', 'workflow', true)
    })

    expect(useProjectStore.getState().isSplittingNode).toBe(true)
    expect(useProjectStore.getState().splittingNodeId).toBe('root')
    expect(useProjectStore.getState().selectedNodeId).toBe('root')
    expect(useProjectStore.getState().nodeDrafts).toEqual({ root: { title: 'Draft title' } })

    await act(async () => {
      useProjectStore.getState().applyPlanningEvent('project-1', 'root', {
        type: 'planning_turn_completed',
        node_id: 'root',
        turn_id: 'turn-1',
        created_child_ids: ['workflow-1', 'workflow-2', 'workflow-3'],
        fallback_used: false,
        timestamp: '2026-03-07T10:05:00Z',
      })
      await Promise.resolve()
      await Promise.resolve()
    })

    const state = useProjectStore.getState()
    expect(apiMock.splitNode).toHaveBeenCalledWith('project-1', 'root', 'workflow', true)
    expect(apiMock.getPlanningHistory).toHaveBeenCalledWith('project-1', 'root')
    expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-1')
    expect(state.isSplittingNode).toBe(false)
    expect(state.selectedNodeId).toBe('root')
    expect(state.nodeDrafts).toEqual({})
    expect(state.planningHistoryByNode.root).toEqual([
      {
        turn_id: 'turn-1',
        role: 'tool_call',
        tool_name: 'emit_render_data',
        is_inherited: false,
        origin_node_id: 'root',
        arguments: {
          kind: 'split_result',
          payload: {
            subtasks: [
              {
                id: 'S1',
                title: 'Setup',
                objective: 'Prepare the workspace and plan execution order.',
                why_now: 'This unlocks the implementation steps.',
              },
            ],
          },
        },
        timestamp: '2026-03-07T10:05:00Z',
      },
    ])
  })

  it('keeps the current project loaded after workspace changes when it still exists', async () => {
    const currentProject = makeProject('project-1', 'Alpha', '2026-03-07T10:00:00Z')
    const currentSnapshot = makeSnapshot()

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      bootstrap: { ready: true, workspace_configured: true },
      hasInitialized: true,
      activeProjectId: currentProject.id,
      projects: [currentProject],
      snapshot: currentSnapshot,
      selectedNodeId: 'root',
    })
    window.localStorage.setItem('planningtree.active-project-id', currentProject.id)

    apiMock.setWorkspaceRoot.mockResolvedValue({ base_workspace_root: 'C:/new-workspace' })
    apiMock.getBootstrapStatus.mockResolvedValue({ ready: true, workspace_configured: true })
    apiMock.listProjects.mockResolvedValue([
      { ...currentProject, base_workspace_root: 'C:/new-workspace' },
    ])

    await act(async () => {
      await useProjectStore.getState().setWorkspaceRoot('C:/new-workspace')
    })

    const state = useProjectStore.getState()
    expect(state.baseWorkspaceRoot).toBe('C:/new-workspace')
    expect(state.activeProjectId).toBe(currentProject.id)
    expect(state.snapshot?.project.id).toBe(currentProject.id)
    expect(apiMock.getSnapshot).not.toHaveBeenCalled()
  })

  it('falls back to the newest project after workspace changes when the current project is unavailable', async () => {
    const currentProject = makeProject('project-1', 'Alpha', '2026-03-07T10:00:00Z')
    const fallbackProject = makeProject('project-2', 'Beta', '2026-03-07T11:00:00Z')
    const fallbackSnapshot = makeSnapshot({
      project: {
        ...makeSnapshot().project,
        id: fallbackProject.id,
        name: fallbackProject.name,
        root_goal: fallbackProject.root_goal,
        project_workspace_root: fallbackProject.project_workspace_root,
        updated_at: fallbackProject.updated_at,
      },
      tree_state: {
        root_node_id: 'root-2',
        active_node_id: 'root-2',
        node_registry: [
          {
            ...makeSnapshot().tree_state.node_registry[0],
            node_id: 'root-2',
            title: fallbackProject.name,
            description: fallbackProject.root_goal,
          },
        ],
      },
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      bootstrap: { ready: true, workspace_configured: true },
      hasInitialized: true,
      activeProjectId: currentProject.id,
      projects: [currentProject],
      snapshot: makeSnapshot(),
      selectedNodeId: 'root',
    })
    window.localStorage.setItem('planningtree.active-project-id', currentProject.id)

    apiMock.setWorkspaceRoot.mockResolvedValue({ base_workspace_root: 'C:/new-workspace' })
    apiMock.getBootstrapStatus.mockResolvedValue({ ready: true, workspace_configured: true })
    apiMock.listProjects.mockResolvedValue([fallbackProject])
    apiMock.getSnapshot.mockResolvedValue(fallbackSnapshot)

    await act(async () => {
      await useProjectStore.getState().setWorkspaceRoot('C:/new-workspace')
    })

    const state = useProjectStore.getState()
    expect(state.activeProjectId).toBe(fallbackProject.id)
    expect(state.snapshot?.project.id).toBe(fallbackProject.id)
    expect(state.selectedNodeId).toBe('root-2')
    expect(window.localStorage.getItem('planningtree.active-project-id')).toBe(fallbackProject.id)
  })

  it('resets the active project to the root node and clears local planning state', async () => {
    const resetSnapshot = makeSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          {
            ...makeSnapshot().tree_state.node_registry[0],
            child_ids: [],
            status: 'draft',
          },
        ],
      },
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: makeSnapshot({
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'child-1',
          node_registry: [
            {
              ...makeSnapshot().tree_state.node_registry[0],
              child_ids: ['child-1'],
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
              created_at: '2026-03-07T10:05:00Z',
            },
          ],
        },
      }),
      selectedNodeId: 'child-1',
      nodeDrafts: { 'child-1': { title: 'Draft child' } },
      planningHistoryByNode: {
        'child-1': [
          {
            turn_id: 'turn-1',
            role: 'assistant',
            is_inherited: false,
            origin_node_id: 'child-1',
            timestamp: '2026-03-07T10:05:00Z',
          },
        ],
      },
      planningConnectionStatus: 'connected',
      isSplittingNode: true,
      splittingNodeId: 'child-1',
    })

    apiMock.resetProjectToRoot.mockResolvedValue(resetSnapshot)

    await act(async () => {
      await useProjectStore.getState().resetProjectToRoot()
    })

    const state = useProjectStore.getState()
    expect(apiMock.resetProjectToRoot).toHaveBeenCalledWith('project-1')
    expect(state.snapshot?.tree_state.node_registry).toHaveLength(1)
    expect(state.selectedNodeId).toBe('root')
    expect(state.nodeDrafts).toEqual({})
    expect(state.planningHistoryByNode).toEqual({})
    expect(state.planningConnectionStatus).toBe('disconnected')
    expect(state.isSplittingNode).toBe(false)
    expect(state.splittingNodeId).toBeNull()
    expect(state.isResettingProject).toBe(false)
  })

  it('surfaces reset-to-root failures and clears the loading flag', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: makeSnapshot(),
    })

    apiMock.resetProjectToRoot.mockRejectedValue(new Error('reset failed'))

    await act(async () => {
      await expect(useProjectStore.getState().resetProjectToRoot()).rejects.toThrow('reset failed')
    })

    const state = useProjectStore.getState()
    expect(state.isResettingProject).toBe(false)
    expect(state.error).toBe('reset failed')
  })

  it('tracks the active planning mode from planning_turn_started and clears it on completion', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: makeSnapshot(),
      selectedNodeId: 'root',
    })
    apiMock.getPlanningHistory.mockResolvedValue({ node_id: 'root', turns: [] })
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot())

    act(() => {
      useProjectStore.getState().applyPlanningEvent('project-1', 'root', {
        type: 'planning_turn_started',
        node_id: 'root',
        turn_id: 'turn-1',
        mode: 'workflow',
        timestamp: '2026-03-07T10:05:00Z',
      })
    })

    expect(useProjectStore.getState().activePlanningMode).toBe('workflow')

    await act(async () => {
      useProjectStore.getState().applyPlanningEvent('project-1', 'root', {
        type: 'planning_turn_completed',
        node_id: 'root',
        turn_id: 'turn-1',
        created_child_ids: ['child-1'],
        fallback_used: false,
        timestamp: '2026-03-07T10:06:00Z',
      })
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(useProjectStore.getState().activePlanningMode).toBeNull()
  })

  it('clearPlanningState clears planning cache and in-progress markers', () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      planningHistoryByNode: {
        root: [
          {
            turn_id: 'turn-1',
            role: 'assistant',
            content: 'hello',
            is_inherited: false,
            origin_node_id: 'root',
            timestamp: '2026-03-07T10:05:00Z',
          },
        ],
      },
      planningConnectionStatus: 'connected',
      isSplittingNode: true,
      splittingNodeId: 'root',
      activePlanningMode: 'workflow',
    })

    act(() => {
      useProjectStore.getState().clearPlanningState()
    })

    const state = useProjectStore.getState()
    expect(state.planningConnectionStatus).toBe('disconnected')
    expect(state.planningHistoryByNode).toEqual({})
    expect(state.isSplittingNode).toBe(false)
    expect(state.splittingNodeId).toBeNull()
    expect(state.activePlanningMode).toBeNull()
  })

  it('loads node documents into the cache for the selected node', async () => {
    const documents = makeDocuments({
      briefing: { user_notes: 'Pinned', business_context: '', technical_context: '', execution_context: '', clarified_answers: '' },
      state: makeNodeState({ phase: 'briefing_review' }),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: makeSnapshot(),
      selectedNodeId: 'root',
    })
    apiMock.getNodeDocuments.mockResolvedValue(documents)

    await act(async () => {
      await useProjectStore.getState().loadNodeDocuments('root')
    })

    expect(apiMock.getNodeDocuments).toHaveBeenCalledWith('project-1', 'root')
    expect(useProjectStore.getState().documentsByNode.root).toEqual(documents)
  })

  it('confirms the task and refreshes both snapshot and document cache', async () => {
    const refreshedSnapshot = makeSnapshot({
      tree_state: {
        ...makeSnapshot().tree_state,
        node_registry: [
          {
            ...makeSnapshot().tree_state.node_registry[0],
            phase: 'briefing_review',
          },
        ],
      },
    })
    const refreshedDocuments = makeDocuments({
      state: makeNodeState({ phase: 'briefing_review', task_confirmed: true }),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: makeSnapshot(),
      selectedNodeId: 'root',
    })
    apiMock.confirmTask.mockResolvedValue({ state: makeNodeState({ phase: 'briefing_review', task_confirmed: true }) })
    apiMock.getSnapshot.mockResolvedValue(refreshedSnapshot)
    apiMock.getNodeDocuments.mockResolvedValue(refreshedDocuments)

    await act(async () => {
      await useProjectStore.getState().confirmTask('root')
    })

    expect(apiMock.confirmTask).toHaveBeenCalledWith('project-1', 'root')
    expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-1')
    expect(useProjectStore.getState().snapshot?.tree_state.node_registry[0].phase).toBe(
      'briefing_review',
    )
    expect(useProjectStore.getState().documentsByNode.root).toEqual(refreshedDocuments)
  })

  it('updates the task through document endpoints and refreshes snapshot plus documents', async () => {
    const refreshedSnapshot = makeSnapshot({
      tree_state: {
        ...makeSnapshot().tree_state,
        node_registry: [
          {
            ...makeSnapshot().tree_state.node_registry[0],
            title: 'Clarified title',
            description: 'Clarified purpose',
          },
        ],
      },
    })
    const refreshedDocuments = makeDocuments({
      task: {
        title: 'Clarified title',
        purpose: 'Clarified purpose',
        responsibility: 'Owns delivery',
      },
      state: makeNodeState({ phase: 'planning' }),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: makeSnapshot(),
      selectedNodeId: 'root',
    })
    apiMock.updateNodeTask.mockResolvedValue({ task: refreshedDocuments.task })
    apiMock.getSnapshot.mockResolvedValue(refreshedSnapshot)
    apiMock.getNodeDocuments.mockResolvedValue(refreshedDocuments)

    await act(async () => {
      await useProjectStore.getState().updateNodeTask('root', refreshedDocuments.task)
    })

    expect(apiMock.updateNodeTask).toHaveBeenCalledWith('project-1', 'root', refreshedDocuments.task)
    expect(apiMock.updateNode).not.toHaveBeenCalled()
    expect(useProjectStore.getState().documentsByNode.root).toEqual(refreshedDocuments)
    expect(useProjectStore.getState().snapshot?.tree_state.node_registry[0].title).toBe('Clarified title')
  })

  it('generates a spec and refreshes snapshot plus documents', async () => {
    const refreshedSnapshot = makeSnapshot({
      tree_state: {
        ...makeSnapshot().tree_state,
        node_registry: [
          {
            ...makeSnapshot().tree_state.node_registry[0],
            phase: 'spec_review',
          },
        ],
      },
    })
    const refreshedDocuments = makeDocuments({
      spec: {
        business_contract: 'Business',
        technical_contract: 'Technical',
        delivery_acceptance: 'Acceptance',
        assumptions: 'Assumptions',
      },
      state: makeNodeState({
        phase: 'spec_review',
        task_confirmed: true,
        briefing_confirmed: true,
        spec_generated: true,
      }),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: makeSnapshot(),
      selectedNodeId: 'root',
    })
    apiMock.generateNodeSpec.mockResolvedValue({
      spec: refreshedDocuments.spec,
      state: refreshedDocuments.state,
    })
    apiMock.getSnapshot.mockResolvedValue(refreshedSnapshot)
    apiMock.getNodeDocuments.mockResolvedValue(refreshedDocuments)

    await act(async () => {
      await useProjectStore.getState().generateNodeSpec('root')
    })

    expect(apiMock.generateNodeSpec).toHaveBeenCalledWith('project-1', 'root')
    expect(useProjectStore.getState().isGeneratingSpec).toBe(false)
    expect(useProjectStore.getState().documentsByNode.root).toEqual(refreshedDocuments)
  })

  it('re-syncs failed spec generation state without using the legacy update route', async () => {
    const syncedDocuments = makeDocuments({
      spec: {
        business_contract: 'Existing business',
        technical_contract: 'Existing technical',
        delivery_acceptance: 'Existing acceptance',
        assumptions: 'Existing assumptions',
      },
      state: makeNodeState({
        phase: 'spec_review',
        task_confirmed: true,
        briefing_confirmed: true,
        spec_generated: true,
        spec_generation_status: 'failed',
      }),
    })

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: makeSnapshot(),
      selectedNodeId: 'root',
    })
    apiMock.generateNodeSpec.mockRejectedValue(new Error('invalid response'))
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot())
    apiMock.getNodeDocuments.mockResolvedValue(syncedDocuments)

    await act(async () => {
      await expect(useProjectStore.getState().generateNodeSpec('root')).rejects.toThrow('invalid response')
    })

    expect(apiMock.generateNodeSpec).toHaveBeenCalledWith('project-1', 'root')
    expect(apiMock.updateNode).not.toHaveBeenCalled()
    expect(useProjectStore.getState().documentsByNode.root).toEqual(syncedDocuments)
    expect(useProjectStore.getState().error).toBe('invalid response')
    expect(useProjectStore.getState().isGeneratingSpec).toBe(false)
  })
})
