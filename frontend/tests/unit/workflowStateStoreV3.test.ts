import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getWorkflowStateV3: vi.fn(),
    finishTaskWorkflowV3: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
}))

import { useWorkflowStateStoreV3 } from '../../src/features/conversation/state/workflowStateStoreV3'

function makeWorkflowState(overrides: Record<string, unknown> = {}) {
  return {
    nodeId: 'node-1',
    workflowPhase: 'execution_decision_pending',
    executionThreadId: 'thread-execution-1',
    auditLineageThreadId: 'thread-audit-1',
    reviewThreadId: null,
    activeExecutionRunId: null,
    latestExecutionRunId: null,
    activeReviewCycleId: null,
    latestReviewCycleId: null,
    currentExecutionDecision: null,
    currentAuditDecision: null,
    acceptedSha: null,
    runtimeBlock: null,
    canSendExecutionMessage: true,
    canReviewInAudit: true,
    canImproveInExecution: false,
    canMarkDoneFromExecution: true,
    canMarkDoneFromAudit: false,
    ...overrides,
  }
}

describe('workflowStateStoreV3', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useWorkflowStateStoreV3.getState().reset()
  })

  it('dedupes concurrent workflow-state loads for the same node', async () => {
    let resolveWorkflowState: ((value: ReturnType<typeof makeWorkflowState>) => void) | null = null
    apiMock.getWorkflowStateV3.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveWorkflowState = resolve
        }),
    )

    const firstLoad = useWorkflowStateStoreV3.getState().loadWorkflowState('project-1', 'node-1')
    const secondLoad = useWorkflowStateStoreV3.getState().loadWorkflowState('project-1', 'node-1')

    expect(apiMock.getWorkflowStateV3).toHaveBeenCalledTimes(1)

    const payload = makeWorkflowState()
    resolveWorkflowState?.(payload)

    await expect(firstLoad).resolves.toEqual(payload)
    await expect(secondLoad).resolves.toEqual(payload)
    expect(useWorkflowStateStoreV3.getState().entries['project-1::node-1']).toEqual(payload)
  })

  it('runs finish-task mutation through V3 endpoint and clears active mutation', async () => {
    const before = makeWorkflowState({ workflowPhase: 'idle' })
    const after = makeWorkflowState({ workflowPhase: 'execution_running' })
    apiMock.getWorkflowStateV3.mockResolvedValueOnce(before).mockResolvedValueOnce(after)
    apiMock.finishTaskWorkflowV3.mockResolvedValue({
      accepted: true,
      workflowPhase: 'execution_running',
      executionRunId: 'run-1',
    })

    await useWorkflowStateStoreV3.getState().loadWorkflowState('project-1', 'node-1')
    const mutationPromise = useWorkflowStateStoreV3.getState().finishTask('project-1', 'node-1')

    expect(useWorkflowStateStoreV3.getState().activeMutations['project-1::node-1']).toBe('finish_task')
    await expect(mutationPromise).resolves.toEqual(after)
    expect(apiMock.finishTaskWorkflowV3).toHaveBeenCalledTimes(1)
    expect(useWorkflowStateStoreV3.getState().activeMutations['project-1::node-1']).toBeNull()
    expect(useWorkflowStateStoreV3.getState().entries['project-1::node-1']).toEqual(after)
  })

  it('records mutation error and resets active mutation on failure', async () => {
    const before = makeWorkflowState({ workflowPhase: 'idle' })
    apiMock.getWorkflowStateV3.mockResolvedValueOnce(before)
    apiMock.finishTaskWorkflowV3.mockRejectedValue(new Error('workflow failed'))

    await useWorkflowStateStoreV3.getState().loadWorkflowState('project-1', 'node-1')
    await expect(
      useWorkflowStateStoreV3.getState().finishTask('project-1', 'node-1'),
    ).rejects.toThrow('workflow failed')

    expect(useWorkflowStateStoreV3.getState().activeMutations['project-1::node-1']).toBeNull()
    expect(useWorkflowStateStoreV3.getState().errors['project-1::node-1']).toBe('workflow failed')
  })
})
