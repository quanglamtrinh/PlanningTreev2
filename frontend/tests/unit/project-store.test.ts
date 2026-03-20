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
    resetProjectToRoot: vi.fn(),
    setActiveNode: vi.fn(),
    createChild: vi.fn(),
    splitNode: vi.fn(),
    updateNode: vi.fn(),
    getPlanningHistory: vi.fn(),
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

import { useProjectStore } from '../../src/stores/project-store'

function makeProjectSummary(id: string) {
  return {
    id,
    name: `Project ${id}`,
    root_goal: `Goal ${id}`,
    base_workspace_root: 'C:/workspace',
    project_workspace_root: `C:/workspace/${id}`,
    created_at: '2026-03-07T10:00:00Z',
    updated_at: '2026-03-07T10:00:00Z',
  }
}

function makeSnapshot(projectId = 'project-1') {
  return {
    schema_version: 2,
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
}

describe('project-store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const mockFn of Object.values(apiMock)) {
      mockFn.mockReset()
    }
    useProjectStore.setState(useProjectStore.getInitialState())
    window.localStorage.clear()
  })

  it('initializes with the preferred stored project and loads its snapshot', async () => {
    const projectOne = makeProjectSummary('project-1')
    const projectTwo = makeProjectSummary('project-2')
    window.localStorage.setItem('planningtree.active-project-id', 'project-2')
    apiMock.getBootstrapStatus.mockResolvedValue({ ready: true, workspace_configured: true })
    apiMock.getWorkspaceSettings.mockResolvedValue({ base_workspace_root: 'C:/workspace' })
    apiMock.listProjects.mockResolvedValue([projectOne, projectTwo])
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('project-2'))

    await act(async () => {
      await useProjectStore.getState().initialize()
    })

    const state = useProjectStore.getState()
    expect(state.activeProjectId).toBe('project-2')
    expect(state.snapshot?.project.id).toBe('project-2')
    expect(state.selectedNodeId).toBe('root')
  })

  it('flushes staged node edits through the snapshot update route', async () => {
    const snapshot = makeSnapshot()
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot,
      selectedNodeId: 'root',
      nodeDrafts: {
        root: {
          title: 'Updated Root',
          description: 'Updated purpose',
        },
      },
    })
    apiMock.updateNode.mockResolvedValue({
      ...snapshot,
      tree_state: {
        ...snapshot.tree_state,
        node_registry: [
          {
            ...snapshot.tree_state.node_registry[0],
            title: 'Updated Root',
            description: 'Updated purpose',
          },
        ],
      },
    })

    await act(async () => {
      await useProjectStore.getState().flushNodeDraft('root')
    })

    expect(apiMock.updateNode).toHaveBeenCalledWith('project-1', 'root', {
      title: 'Updated Root',
      description: 'Updated purpose',
    })
    expect(useProjectStore.getState().nodeDrafts).toEqual({})
    expect(useProjectStore.getState().snapshot?.tree_state.node_registry[0]?.title).toBe(
      'Updated Root',
    )
  })

  it('marks split state while requesting a split', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
    })
    apiMock.splitNode.mockResolvedValue({
      status: 'accepted',
      node_id: 'root',
      mode: 'workflow',
      planning_status: 'active',
    })

    await act(async () => {
      await useProjectStore.getState().splitNode('root', 'workflow', true)
    })

    expect(apiMock.splitNode).toHaveBeenCalledWith('project-1', 'root', 'workflow', true)
    const state = useProjectStore.getState()
    expect(state.isSplittingNode).toBe(true)
    expect(state.splittingNodeId).toBe('root')
    expect(state.activePlanningMode).toBe('workflow')
  })

  it('clears planning cache and in-progress markers', () => {
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
})
