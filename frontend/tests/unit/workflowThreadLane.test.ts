import { describe, expect, it } from 'vitest'

import type { NodeWorkflowView } from '../../src/api/types'
import {
  mergeSessionConfig,
  resolveWorkflowSubmitSessionConfig,
  resolveWorkflowThreadLane,
} from '../../src/features/conversation/workflowThreadLane'

function makeWorkflowState(overrides: Partial<NodeWorkflowView> = {}): NodeWorkflowView {
  return {
    nodeId: 'node-1',
    workflowPhase: 'idle',
    askThreadId: 'ask-thread-1',
    executionThreadId: 'exec-thread-1',
    auditLineageThreadId: 'audit-lineage-1',
    reviewThreadId: 'audit-thread-1',
    activeExecutionRunId: null,
    latestExecutionRunId: null,
    activeReviewCycleId: null,
    latestReviewCycleId: null,
    currentExecutionDecision: null,
    currentAuditDecision: null,
    acceptedSha: null,
    runtimeBlock: null,
    canSendExecutionMessage: false,
    canReviewInAudit: false,
    canImproveInExecution: false,
    canMarkDoneFromExecution: false,
    canMarkDoneFromAudit: false,
    ...overrides,
  }
}

describe('workflowThreadLane', () => {
  it('resolves lane thread id, policy, and base session config', () => {
    const lane = resolveWorkflowThreadLane({
      workflowState: makeWorkflowState({ canSendExecutionMessage: true }),
      threadTab: 'execution',
      selectedModel: 'gpt-5.4',
      selectedModelProvider: 'openai',
      projectPath: 'C:/repo',
    })

    expect(lane).toMatchObject({
      lane: 'execution',
      threadId: 'exec-thread-1',
      policy: {
        kind: 'execution',
        canSubmit: true,
        disabledReason: null,
      },
      sessionConfig: {
        model: 'gpt-5.4',
        modelProvider: 'openai',
        cwd: 'C:/repo',
      },
      actions: [],
    })
  })

  it('blocks submit when the workflow lane has no thread', () => {
    const lane = resolveWorkflowThreadLane({
      workflowState: makeWorkflowState({ askThreadId: null }),
      threadTab: 'ask',
    })

    expect(lane.threadId).toBeNull()
    expect(lane.policy).toEqual({
      kind: 'ask',
      canSubmit: false,
      disabledReason: 'No workflow thread is available for this lane.',
    })
  })

  it('blocks execution submit when workflow cannot send execution messages', () => {
    const lane = resolveWorkflowThreadLane({
      workflowState: makeWorkflowState({ canSendExecutionMessage: false }),
      threadTab: 'execution',
    })

    expect(lane.threadId).toBe('exec-thread-1')
    expect(lane.policy).toEqual({
      kind: 'execution',
      canSubmit: false,
      disabledReason: 'Execution follow-up messages are not enabled for this workflow state.',
    })
  })

  it('marks review nodes as read-only even when an audit thread exists', () => {
    const lane = resolveWorkflowThreadLane({
      workflowState: makeWorkflowState({ reviewThreadId: 'audit-thread-1' }),
      threadTab: 'audit',
      isReviewNode: true,
    })

    expect(lane.threadId).toBe('audit-thread-1')
    expect(lane.policy).toEqual({
      kind: 'review-readonly',
      canSubmit: false,
      disabledReason: 'Review nodes are read-only.',
    })
  })

  it('returns workflow action intents with required mutation payloads', () => {
    const lane = resolveWorkflowThreadLane({
      workflowState: makeWorkflowState({
        canReviewInAudit: true,
        canMarkDoneFromExecution: true,
        currentExecutionDecision: {
          status: 'ready',
          sourceExecutionRunId: 'run-1',
          executionTurnId: 'turn-1',
          candidateWorkspaceHash: 'hash-1',
          summaryText: null,
          createdAt: '2026-04-01T00:00:00Z',
        },
      }),
      threadTab: 'execution',
    })

    expect(lane.actions).toEqual([
      expect.objectContaining({
        kind: 'reviewInAudit',
        testId: 'workflow-review-in-audit',
        candidateWorkspaceHash: 'hash-1',
      }),
      expect.objectContaining({
        kind: 'markDoneFromExecution',
        testId: 'workflow-mark-done-execution',
        candidateWorkspaceHash: 'hash-1',
      }),
    ])
  })

  it('merges lane config, composer config, and full-access policy overlay', () => {
    const lane = resolveWorkflowThreadLane({
      workflowState: makeWorkflowState({ canSendExecutionMessage: true }),
      threadTab: 'execution',
      selectedModel: 'gpt-5.4',
      selectedModelProvider: 'openai',
      projectPath: 'C:/repo',
    })

    expect(
      resolveWorkflowSubmitSessionConfig({
        lane,
        accessMode: 'full-access',
        sessionConfig: {
          reasoning: { effort: 'xhigh', summary: null },
          config: {
            composer: {
              workMode: 'locally',
              streamMode: 'streaming',
            },
          },
        },
      }),
    ).toEqual({
      model: 'gpt-5.4',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      reasoning: { effort: 'xhigh', summary: null },
      config: {
        composer: {
          workMode: 'locally',
          streamMode: 'streaming',
        },
      },
      approvalPolicy: 'never',
      sandboxPolicy: { type: 'dangerFullAccess' },
    })
  })

  it('merges nested reasoning and config without losing base values', () => {
    expect(
      mergeSessionConfig(
        {
          reasoning: { effort: 'high', summary: 'auto' },
          config: { source: 'lane' },
        },
        {
          reasoning: { effort: 'xhigh' },
          config: { composer: { streamMode: 'batch' } },
        },
      ),
    ).toEqual({
      reasoning: { effort: 'xhigh', summary: 'auto' },
      config: {
        source: 'lane',
        composer: { streamMode: 'batch' },
      },
    })
  })
})
