import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getWorkflowStateV2: vi.fn(),
  },
}))

vi.mock('../../src/features/workflow_v2/api/client', () => ({
  getWorkflowStateV2: apiMock.getWorkflowStateV2,
}))

import { useWorkflowStateStoreV2 } from '../../src/features/workflow_v2/store/workflowStateStoreV2'
import type { WorkflowStateV2 } from '../../src/features/workflow_v2/types'

function makeWorkflowState(overrides: Partial<WorkflowStateV2> = {}): WorkflowStateV2 {
  return {
    schemaVersion: 1,
    projectId: 'project-1',
    nodeId: 'node-1',
    phase: 'ready_for_execution',
    version: 1,
    threads: {
      askPlanning: null,
      execution: null,
      audit: null,
      packageReview: null,
    },
    decisions: {
      execution: null,
      audit: null,
    },
    context: {
      frameVersion: null,
      specVersion: null,
      splitManifestVersion: null,
      stale: false,
      staleReason: null,
    },
    allowedActions: ['start_execution'],
    ...overrides,
  }
}

describe('workflowStateStoreV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useWorkflowStateStoreV2.getState().reset()
  })

  it('dedupes concurrent workflow-state loads for the same node', async () => {
    let resolveWorkflowState: ((value: WorkflowStateV2) => void) | null = null
    apiMock.getWorkflowStateV2.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveWorkflowState = resolve
        }),
    )

    const firstLoad = useWorkflowStateStoreV2.getState().loadWorkflowState('project-1', 'node-1')
    const secondLoad = useWorkflowStateStoreV2.getState().loadWorkflowState('project-1', 'node-1')

    expect(apiMock.getWorkflowStateV2).toHaveBeenCalledTimes(1)

    const payload = makeWorkflowState()
    resolveWorkflowState?.(payload)

    await expect(firstLoad).resolves.toEqual(payload)
    await expect(secondLoad).resolves.toEqual(payload)
    expect(useWorkflowStateStoreV2.getState().entries['project-1::node-1']).toEqual(payload)
    expect(useWorkflowStateStoreV2.getState().loading['project-1::node-1']).toBe(false)
    expect(useWorkflowStateStoreV2.getState().errors['project-1::node-1']).toBe('')
  })

  it('records load errors and clears loading', async () => {
    apiMock.getWorkflowStateV2.mockRejectedValue(new Error('workflow failed'))

    await expect(
      useWorkflowStateStoreV2.getState().loadWorkflowState('project-1', 'node-1'),
    ).rejects.toThrow('workflow failed')

    expect(useWorkflowStateStoreV2.getState().loading['project-1::node-1']).toBe(false)
    expect(useWorkflowStateStoreV2.getState().errors['project-1::node-1']).toBe('workflow failed')
  })

  it('resets entries, loading, errors, and in-flight state', async () => {
    const payload = makeWorkflowState({ version: 2 })
    apiMock.getWorkflowStateV2.mockResolvedValue(payload)

    await useWorkflowStateStoreV2.getState().loadWorkflowState('project-1', 'node-1')
    useWorkflowStateStoreV2.getState().reset()

    expect(useWorkflowStateStoreV2.getState().entries).toEqual({})
    expect(useWorkflowStateStoreV2.getState().loading).toEqual({})
    expect(useWorkflowStateStoreV2.getState().errors).toEqual({})
  })
})
