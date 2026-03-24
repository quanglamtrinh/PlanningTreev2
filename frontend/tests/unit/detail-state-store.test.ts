import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getDetailState: vi.fn(),
    finishTask: vi.fn(),
    getSnapshot: vi.fn(),
    acceptLocalReview: vi.fn(),
    acceptRollupReview: vi.fn(),
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

import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useProjectStore } from '../../src/stores/project-store'

function makeDetailState(overrides: Record<string, unknown> = {}) {
  return {
    node_id: 'root',
    workflow: {
      frame_confirmed: true,
      active_step: 'spec' as const,
      spec_confirmed: true,
      execution_started: false,
      execution_completed: false,
      shaping_frozen: false,
      can_finish_task: true,
      execution_status: null,
    },
    frame_confirmed: true,
    frame_confirmed_revision: 1,
    frame_revision: 1,
    active_step: 'spec' as const,
    workflow_notice: null,
    generation_error: null,
    frame_needs_reconfirm: false,
    frame_read_only: false,
    clarify_read_only: true,
    clarify_confirmed: true,
    spec_read_only: false,
    spec_stale: false,
    spec_confirmed: true,
    execution_started: false,
    execution_completed: false,
    shaping_frozen: false,
    can_finish_task: true,
    execution_status: null,
    audit_writable: false,
    package_audit_ready: false,
    review_status: null,
    ...overrides,
  }
}

function makeSnapshot(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 6,
    project: {
      id: 'project-1',
      name: 'Project 1',
      root_goal: 'Ship it',
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
          status: 'in_progress' as const,
          node_kind: 'root' as const,
          depth: 0,
          display_order: 0,
          hierarchical_number: '1',
          is_superseded: false,
          created_at: '2026-03-20T00:00:00Z',
          workflow: {
            frame_confirmed: true,
            active_step: 'spec' as const,
            spec_confirmed: true,
            execution_started: true,
            execution_completed: true,
            shaping_frozen: true,
            can_finish_task: false,
            execution_status: 'completed' as const,
          },
        },
      ],
    },
    updated_at: '2026-03-20T00:00:00Z',
    ...overrides,
  }
}

describe('detail-state-store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
    useDetailStateStore.getState().reset()
    useProjectStore.setState(useProjectStore.getInitialState())
  })

  it('polls execution state after finishTask until execution completes', async () => {
    vi.useFakeTimers()
    apiMock.finishTask.mockResolvedValue(
      makeDetailState({
        workflow: {
          frame_confirmed: true,
          active_step: 'spec',
          spec_confirmed: true,
          execution_started: true,
          execution_completed: false,
          shaping_frozen: true,
          can_finish_task: false,
          execution_status: 'executing',
        },
        execution_started: true,
        execution_completed: false,
        shaping_frozen: true,
        can_finish_task: false,
        execution_status: 'executing',
      }),
    )
    apiMock.getDetailState.mockResolvedValue(
      makeDetailState({
        workflow: {
          frame_confirmed: true,
          active_step: 'spec',
          spec_confirmed: true,
          execution_started: true,
          execution_completed: true,
          shaping_frozen: true,
          can_finish_task: false,
          execution_status: 'completed',
        },
        execution_started: true,
        execution_completed: true,
        shaping_frozen: true,
        can_finish_task: false,
        execution_status: 'completed',
      }),
    )
    apiMock.getSnapshot.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useDetailStateStore.getState().finishTask('project-1', 'root')
    })

    expect(useDetailStateStore.getState().entries['project-1::root']?.execution_status).toBe('executing')

    await act(async () => {
      vi.advanceTimersByTime(1000)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(apiMock.getDetailState).toHaveBeenCalledWith('project-1', 'root')
    expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-1')
    expect(useDetailStateStore.getState().entries['project-1::root']?.execution_status).toBe('completed')
    expect(useProjectStore.getState().snapshot?.project.id).toBe('project-1')
  })

  it('acceptLocalReview refreshes detail-state and selects the activated sibling', async () => {
    apiMock.acceptLocalReview.mockResolvedValue({
      node_id: 'root',
      status: 'review_accepted',
      activated_sibling_id: 'child-2',
    })
    apiMock.getDetailState.mockResolvedValue(
      makeDetailState({
        execution_started: true,
        execution_completed: true,
        shaping_frozen: true,
        can_finish_task: false,
        can_accept_local_review: false,
        execution_status: 'review_accepted',
      }),
    )
    apiMock.getSnapshot.mockResolvedValue(
      makeSnapshot({
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'child-2',
          node_registry: [
            {
              node_id: 'root',
              parent_id: null,
              child_ids: ['child-2'],
              title: 'Root',
              description: 'Root node',
              status: 'done' as const,
              node_kind: 'root' as const,
              depth: 0,
              display_order: 0,
              hierarchical_number: '1',
              is_superseded: false,
              created_at: '2026-03-20T00:00:00Z',
              workflow: {
                frame_confirmed: true,
                active_step: 'spec' as const,
                spec_confirmed: true,
                execution_started: true,
                execution_completed: true,
                shaping_frozen: true,
                can_finish_task: false,
                can_accept_local_review: false,
                execution_status: 'review_accepted' as const,
              },
            },
            {
              node_id: 'child-2',
              parent_id: 'root',
              child_ids: [],
              title: 'Child 2',
              description: 'Next sibling',
              status: 'ready' as const,
              node_kind: 'original' as const,
              depth: 1,
              display_order: 1,
              hierarchical_number: '1.2',
              is_superseded: false,
              created_at: '2026-03-20T00:00:00Z',
              workflow: {
                frame_confirmed: true,
                active_step: 'spec' as const,
                spec_confirmed: true,
                execution_started: false,
                execution_completed: false,
                shaping_frozen: false,
                can_finish_task: true,
                can_accept_local_review: false,
                execution_status: null,
              },
            },
          ],
        },
      }),
    )
    useProjectStore.setState({ selectedNodeId: 'root' })

    await act(async () => {
      await useDetailStateStore.getState().acceptLocalReview('project-1', 'root', 'Looks good')
    })

    expect(apiMock.acceptLocalReview).toHaveBeenCalledWith('project-1', 'root', 'Looks good')
    expect(apiMock.getDetailState).toHaveBeenCalledWith('project-1', 'root')
    expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-1')
    expect(useDetailStateStore.getState().entries['project-1::root']?.execution_status).toBe('review_accepted')
    expect(useProjectStore.getState().selectedNodeId).toBe('child-2')
  })

  it('acceptRollupReview refreshes review and parent detail-state and clears stale errors', async () => {
    apiMock.acceptRollupReview.mockResolvedValue({
      review_node_id: 'review-1',
      rollup_status: 'accepted',
      summary: 'Package accepted',
      sha: 'sha256:abc123',
    })
    apiMock.getDetailState
      .mockResolvedValueOnce(
        makeDetailState({
          node_id: 'review-1',
          workflow: null,
          can_finish_task: false,
          can_accept_local_review: false,
          execution_status: null,
          audit_writable: false,
          package_audit_ready: false,
          review_status: 'accepted',
        }),
      )
      .mockResolvedValueOnce(
        makeDetailState({
          node_id: 'parent-1',
          execution_started: true,
          execution_completed: true,
          shaping_frozen: true,
          can_finish_task: false,
          can_accept_local_review: false,
          execution_status: 'review_accepted',
          audit_writable: true,
          package_audit_ready: true,
          review_status: 'accepted',
        }),
      )
    apiMock.getSnapshot.mockResolvedValue(
      makeSnapshot({
        tree_state: {
          root_node_id: 'parent-1',
          active_node_id: 'parent-1',
          node_registry: [
            {
              node_id: 'parent-1',
              parent_id: null,
              child_ids: [],
              title: 'Parent',
              description: 'Parent node',
              status: 'done' as const,
              node_kind: 'root' as const,
              depth: 0,
              display_order: 0,
              hierarchical_number: '1',
              is_superseded: false,
              created_at: '2026-03-20T00:00:00Z',
              workflow: {
                frame_confirmed: true,
                active_step: 'spec' as const,
                spec_confirmed: true,
                execution_started: true,
                execution_completed: true,
                shaping_frozen: true,
                can_finish_task: false,
                can_accept_local_review: false,
                execution_status: 'review_accepted' as const,
              },
              review_node_id: 'review-1',
            },
            {
              node_id: 'review-1',
              parent_id: null,
              child_ids: [],
              title: 'Review',
              description: 'Review node',
              status: 'ready' as const,
              node_kind: 'review' as const,
              depth: 1,
              display_order: 99,
              hierarchical_number: 'R1',
              is_superseded: false,
              created_at: '2026-03-20T00:00:00Z',
              workflow: null,
            },
          ],
        },
      }),
    )
    useDetailStateStore.setState((state) => ({
      errors: {
        ...state.errors,
        'project-1::review-1': 'old review error',
        'project-1::parent-1': 'old parent error',
      },
    }))

    await act(async () => {
      await useDetailStateStore.getState().acceptRollupReview('project-1', 'review-1')
    })

    expect(apiMock.acceptRollupReview).toHaveBeenCalledWith('project-1', 'review-1')
    expect(apiMock.getDetailState).toHaveBeenNthCalledWith(1, 'project-1', 'review-1')
    expect(apiMock.getDetailState).toHaveBeenNthCalledWith(2, 'project-1', 'parent-1')
    expect(useDetailStateStore.getState().entries['project-1::review-1']?.review_status).toBe('accepted')
    expect(useDetailStateStore.getState().entries['project-1::parent-1']?.package_audit_ready).toBe(true)
    expect(useDetailStateStore.getState().errors['project-1::review-1']).toBe('')
    expect(useDetailStateStore.getState().errors['project-1::parent-1']).toBe('')
  })
})
