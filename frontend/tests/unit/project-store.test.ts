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
    getSplitStatus: vi.fn(),
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

import { useProjectStore } from '../../src/stores/project-store'

function makeProjectSummary(id: string) {
  return {
    id,
    name: `Project ${id}`,
    root_goal: `Goal ${id}`,
    base_workspace_root: 'C:/workspace',
    project_workspace_root: `C:/workspace/${id}`,
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

describe('project-store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const mockFn of Object.values(apiMock)) {
      mockFn.mockReset()
    }
    useProjectStore.setState(useProjectStore.getInitialState())
    window.localStorage.clear()
    vi.useRealTimers()
  })

  it('initializes with the preferred stored project and loads its snapshot', async () => {
    const projectOne = makeProjectSummary('project-1')
    const projectTwo = makeProjectSummary('project-2')
    window.localStorage.setItem('planningtree.active-project-id', 'project-2')
    apiMock.getBootstrapStatus.mockResolvedValue({ ready: true, workspace_configured: true })
    apiMock.getWorkspaceSettings.mockResolvedValue({ base_workspace_root: 'C:/workspace' })
    apiMock.listProjects.mockResolvedValue([projectOne, projectTwo])
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot('project-2'))
    apiMock.getSplitStatus.mockResolvedValue(makeIdleSplitStatus())

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
          description: 'Updated description',
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
            description: 'Updated description',
          },
        ],
      },
    })

    await act(async () => {
      await useProjectStore.getState().flushNodeDraft('root')
    })

    expect(apiMock.updateNode).toHaveBeenCalledWith('project-1', 'root', {
      title: 'Updated Root',
      description: 'Updated description',
    })
    expect(useProjectStore.getState().nodeDrafts).toEqual({})
  })

  it('maps legacy project errors to the graph-only message', async () => {
    const ApiError = (await import('../../src/api/client')).ApiError
    apiMock.getSnapshot.mockRejectedValue(
      new ApiError(409, { code: 'legacy_project_unsupported', message: 'legacy project' }),
    )

    await expect(useProjectStore.getState().loadProject('project-legacy')).rejects.toThrow()

    expect(useProjectStore.getState().error).toBe('Project này thuộc schema legacy đã bị loại bỏ; hãy xóa hoặc tạo lại.')
  })

  it('starts split polling after accepting a split request', async () => {
    vi.useFakeTimers()
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
      snapshot: makeSnapshot(),
      selectedNodeId: 'root',
    })
    apiMock.splitNode.mockResolvedValue({
      status: 'accepted',
      job_id: 'split_123',
      node_id: 'root',
      mode: 'workflow',
    })
    apiMock.getSplitStatus.mockResolvedValue({
      status: 'active',
      job_id: 'split_123',
      node_id: 'root',
      mode: 'workflow',
      started_at: '2026-03-20T00:00:00Z',
      completed_at: null,
      error: null,
    })

    await act(async () => {
      await useProjectStore.getState().splitNode('root', 'workflow')
    })

    expect(apiMock.splitNode).toHaveBeenCalledWith('project-1', 'root', 'workflow')
    expect(useProjectStore.getState().splitStatus).toBe('active')
    expect(useProjectStore.getState().splitNodeId).toBe('root')

    await act(async () => {
      vi.advanceTimersByTime(1600)
      await Promise.resolve()
    })

    expect(apiMock.getSplitStatus).toHaveBeenCalledWith('project-1')
  })
})
