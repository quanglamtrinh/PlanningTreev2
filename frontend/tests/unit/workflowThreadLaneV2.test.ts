import { describe, expect, it } from 'vitest'

import {
  buildWorkflowProjectionV2,
  mergeSessionConfigV2,
  resolveWorkflowSubmitTurnPolicyV2,
  resolveWorkflowThreadLaneV2,
} from '../../src/features/conversation/workflowThreadLaneV2'
import type { WorkflowStateV2 } from '../../src/features/workflow_v2/types'

type WorkflowStateOverrides = Partial<Omit<WorkflowStateV2, 'threads' | 'decisions' | 'context'>> & {
  threads?: Partial<WorkflowStateV2['threads']>
  decisions?: Partial<WorkflowStateV2['decisions']>
  context?: Partial<WorkflowStateV2['context']>
}

function makeWorkflowState(overrides: WorkflowStateOverrides = {}): WorkflowStateV2 {
  const base: WorkflowStateV2 = {
    schemaVersion: 1,
    projectId: 'project-1',
    nodeId: 'node-1',
    phase: 'execution_completed',
    version: 1,
    threads: {
      askPlanning: 'ask-thread-1',
      execution: 'exec-thread-1',
      audit: 'audit-thread-1',
      packageReview: null,
    },
    decisions: {
      execution: {
        status: 'current',
        sourceExecutionRunId: 'run-1',
        executionTurnId: 'turn-1',
        candidateWorkspaceHash: 'sha256:workspace',
        summaryText: null,
        createdAt: '2026-04-01T00:00:00Z',
      },
      audit: {
        status: 'current',
        sourceAuditRunId: 'audit-1',
        reviewCommitSha: 'review-sha',
        finalReviewText: 'Needs one pass',
        reviewDisposition: null,
        createdAt: '2026-04-01T00:00:00Z',
      },
    },
    context: {
      frameVersion: null,
      specVersion: null,
      splitManifestVersion: null,
    },
    allowedActions: ['review_in_audit', 'mark_done_from_execution'],
  }
  return {
    ...base,
    ...overrides,
    threads: {
      ...base.threads,
      ...(overrides.threads ?? {}),
    },
    decisions: {
      ...base.decisions,
      ...(overrides.decisions ?? {}),
    },
    context: {
      ...base.context,
      ...(overrides.context ?? {}),
    },
  }
}

describe('workflowThreadLaneV2', () => {
  it('resolves V2 lane thread id, policy, and session config', () => {
    const askLane = resolveWorkflowThreadLaneV2({
      workflowState: makeWorkflowState(),
      threadTab: 'ask',
      selectedModel: 'gpt-5.4',
      selectedModelProvider: 'openai',
      projectPath: 'C:/repo',
    })

    expect(askLane).toMatchObject({
      lane: 'ask',
      threadId: 'ask-thread-1',
      policy: {
        kind: 'ask',
        canSubmit: true,
        disabledReason: null,
      },
      sessionConfig: {
        model: 'gpt-5.4',
        modelProvider: 'openai',
        cwd: 'C:/repo',
      },
    })
  })

  it('builds a unified projection from V2 role bindings', () => {
    const projection = buildWorkflowProjectionV2({
      workflowState: makeWorkflowState(),
      activeLane: 'audit',
      selectedModel: 'gpt-5.4',
      selectedModelProvider: 'openai',
      projectPath: 'C:/repo',
    })

    expect(projection.isLoaded).toBe(true)
    expect(projection.active).toBe(projection.lanes.audit)
    expect(projection.lanes.ask.threadId).toBe('ask-thread-1')
    expect(projection.lanes.execution.threadId).toBe('exec-thread-1')
    expect(projection.lanes.audit.threadId).toBe('audit-thread-1')
    expect(projection.lanes.execution.policy).toEqual({
      kind: 'execution',
      canSubmit: false,
      disabledReason: 'Workflow V2 business lanes are controlled by workflow actions.',
    })
  })

  it('marks projection as unloaded before workflow state arrives', () => {
    const projection = buildWorkflowProjectionV2({
      workflowState: undefined,
      activeLane: 'execution',
    })

    expect(projection.isLoaded).toBe(false)
    expect(projection.active.threadId).toBeNull()
    expect(projection.active.policy).toEqual({
      kind: 'default',
      canSubmit: false,
      disabledReason: 'Workflow state is not loaded.',
    })
  })

  it('returns execution action intents with V2 action names and guard payloads', () => {
    const lane = resolveWorkflowThreadLaneV2({
      workflowState: makeWorkflowState({
        allowedActions: ['start_execution', 'review_in_audit', 'mark_done_from_execution'],
      }),
      threadTab: 'execution',
    })

    expect(lane.actions).toEqual([
      expect.objectContaining({
        kind: 'review_in_audit',
        testId: 'workflow-review-in-audit',
        candidateWorkspaceHash: 'sha256:workspace',
      }),
      expect.objectContaining({
        kind: 'mark_done_from_execution',
        testId: 'workflow-mark-done-execution',
        candidateWorkspaceHash: 'sha256:workspace',
      }),
    ])
  })

  it('keeps ask lane writable when ask planning thread is unbound', () => {
    const lane = resolveWorkflowThreadLaneV2({
      workflowState: makeWorkflowState({
        threads: {
          askPlanning: null,
        },
      }),
      threadTab: 'ask',
    })

    expect(lane.threadId).toBeNull()
    expect(lane.policy).toEqual({
      kind: 'ask',
      canSubmit: true,
      disabledReason: null,
    })
    expect(lane.actions).toEqual([])
  })

  it('returns audit action intents with review commit guard payloads', () => {
    const lane = resolveWorkflowThreadLaneV2({
      workflowState: makeWorkflowState({
        phase: 'review_pending',
        allowedActions: ['improve_in_execution', 'mark_done_from_audit'],
      }),
      threadTab: 'audit',
    })

    expect(lane.actions).toEqual([
      expect.objectContaining({
        kind: 'improve_in_execution',
        testId: 'workflow-improve-in-execution',
        reviewCommitSha: 'review-sha',
      }),
      expect.objectContaining({
        kind: 'mark_done_from_audit',
        testId: 'workflow-mark-done-audit',
        reviewCommitSha: 'review-sha',
      }),
    ])
  })

  it('does not expose package review as a Breadcrumb lane action', () => {
    const lane = resolveWorkflowThreadLaneV2({
      workflowState: makeWorkflowState({
        phase: 'done',
        allowedActions: ['start_package_review'],
      }),
      threadTab: 'execution',
    })

    expect(lane.actions).toEqual([])
  })

  it('marks review nodes as read-only even when a thread exists', () => {
    const lane = resolveWorkflowThreadLaneV2({
      workflowState: makeWorkflowState(),
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

  it('keeps ask lane writable on review nodes when ask thread exists', () => {
    const lane = resolveWorkflowThreadLaneV2({
      workflowState: makeWorkflowState(),
      threadTab: 'ask',
      isReviewNode: true,
    })

    expect(lane.threadId).toBe('ask-thread-1')
    expect(lane.policy).toEqual({
      kind: 'ask',
      canSubmit: true,
      disabledReason: null,
    })
  })

  it('maps composer intent through ask lane config into a full-access turn policy', () => {
    const lane = resolveWorkflowThreadLaneV2({
      workflowState: makeWorkflowState(),
      threadTab: 'ask',
      selectedModel: 'gpt-5.4',
      selectedModelProvider: 'openai',
      projectPath: 'C:/repo',
    })

    expect(
      resolveWorkflowSubmitTurnPolicyV2({
        lane,
        requestedPolicy: {
          accessMode: 'full-access',
          effort: 'extra-high',
          workMode: 'local',
          streamMode: 'streaming',
        },
      }),
    ).toEqual({
      model: 'gpt-5.4',
      cwd: 'C:/repo',
      approvalPolicy: 'never',
      approvalsReviewer: undefined,
      sandboxPolicy: { type: 'dangerFullAccess' },
      personality: undefined,
      effort: 'xhigh',
      summary: null,
      serviceTier: undefined,
      outputSchema: undefined,
    })
  })

  it('maps read-only composer intent to read-only turn policy', () => {
    const lane = resolveWorkflowThreadLaneV2({
      workflowState: makeWorkflowState(),
      threadTab: 'ask',
      selectedModel: 'gpt-5.4',
      selectedModelProvider: 'openai',
      projectPath: 'C:/repo',
    })

    expect(
      resolveWorkflowSubmitTurnPolicyV2({
        lane,
        requestedPolicy: {
          accessMode: 'read-only',
          effort: 'medium',
        },
      }),
    ).toMatchObject({
      model: 'gpt-5.4',
      cwd: 'C:/repo',
      approvalPolicy: 'on-request',
      sandboxPolicy: { type: 'readOnly' },
      effort: 'medium',
      summary: null,
    })
  })

  it('merges nested reasoning and config without losing base values', () => {
    expect(
      mergeSessionConfigV2(
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
