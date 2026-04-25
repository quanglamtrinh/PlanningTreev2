import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getWorkflowStateV2: vi.fn(),
    ensureWorkflowThreadV2: vi.fn(),
    startExecutionV2: vi.fn(),
    markDoneFromExecutionV2: vi.fn(),
    startAuditV2: vi.fn(),
    improveExecutionV2: vi.fn(),
    acceptAuditV2: vi.fn(),
  },
}))

vi.mock('../../src/features/workflow_v2/api/client', () => ({
  getWorkflowStateV2: apiMock.getWorkflowStateV2,
  ensureWorkflowThreadV2: apiMock.ensureWorkflowThreadV2,
  startExecutionV2: apiMock.startExecutionV2,
  markDoneFromExecutionV2: apiMock.markDoneFromExecutionV2,
  startAuditV2: apiMock.startAuditV2,
  improveExecutionV2: apiMock.improveExecutionV2,
  acceptAuditV2: apiMock.acceptAuditV2,
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
    expect(useWorkflowStateStoreV2.getState().activeMutations).toEqual({})
  })

  it('runs start execution mutation with idempotency and stores returned workflow state', async () => {
    const after = makeWorkflowState({
      phase: 'executing',
      version: 2,
      threads: {
        askPlanning: null,
        execution: 'exec-thread-1',
        audit: null,
        packageReview: null,
      },
    })
    apiMock.startExecutionV2.mockResolvedValue({
      accepted: true,
      threadId: 'exec-thread-1',
      turnId: 'turn-1',
      workflowState: after,
    })

    const result = await useWorkflowStateStoreV2
      .getState()
      .startExecution('project-1', 'node-1', { model: 'gpt-5.4', modelProvider: 'openai' })

    expect(result).toEqual(after)
    expect(apiMock.startExecutionV2).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      expect.objectContaining({
        idempotencyKey: expect.stringMatching(/^start_execution:/),
        model: 'gpt-5.4',
        modelProvider: 'openai',
      }),
    )
    expect(useWorkflowStateStoreV2.getState().entries['project-1::node-1']).toEqual(after)
    expect(useWorkflowStateStoreV2.getState().activeMutations['project-1::node-1']).toBeNull()
  })

  it('reloads workflow state when a mutation response omits workflowState', async () => {
    const after = makeWorkflowState({ phase: 'done', version: 3 })
    apiMock.markDoneFromExecutionV2.mockResolvedValue({ accepted: true })
    apiMock.getWorkflowStateV2.mockResolvedValue(after)

    await expect(
      useWorkflowStateStoreV2
        .getState()
        .completeExecution('project-1', 'node-1', 'sha256:workspace'),
    ).resolves.toEqual(after)

    expect(apiMock.markDoneFromExecutionV2).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      expect.objectContaining({
        idempotencyKey: expect.stringMatching(/^complete_execution:/),
        expectedWorkspaceHash: 'sha256:workspace',
      }),
    )
    expect(apiMock.getWorkflowStateV2).toHaveBeenCalledWith('project-1', 'node-1')
  })

  it('records mutation errors and clears active mutation', async () => {
    apiMock.startAuditV2.mockRejectedValue(new Error('audit failed'))

    await expect(
      useWorkflowStateStoreV2
        .getState()
        .startAudit('project-1', 'node-1', 'sha256:workspace'),
    ).rejects.toThrow('audit failed')

    expect(useWorkflowStateStoreV2.getState().errors['project-1::node-1']).toBe('audit failed')
    expect(useWorkflowStateStoreV2.getState().activeMutations['project-1::node-1']).toBeNull()
  })
})
