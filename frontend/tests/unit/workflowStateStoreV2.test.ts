import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getWorkflowStateV2: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
}))

import { useWorkflowStateStoreV2 } from '../../src/features/conversation/state/workflowStateStoreV2'

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

describe('workflowStateStoreV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useWorkflowStateStoreV2.getState().reset()
  })

  it('dedupes concurrent workflow-state loads for the same node', async () => {
    let resolveWorkflowState: ((value: ReturnType<typeof makeWorkflowState>) => void) | null = null
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
  })
})
