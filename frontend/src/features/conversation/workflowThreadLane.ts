import type { NodeWorkflowView } from '../../api/types'
import { toTurnExecutionPolicy, type SessionConfig, type TurnExecutionPolicy } from '../session_v2/contracts'
import type { ComposerRequestedPolicy } from '../session_v2/components/ComposerPane'
import type { ThreadTab } from './surfaceRouting'

export type WorkflowPolicyKind =
  | 'ask'
  | 'execution'
  | 'audit'
  | 'package'
  | 'review-readonly'
  | 'default'

export type WorkflowPolicy = {
  kind: WorkflowPolicyKind
  canSubmit: boolean
  disabledReason?: string | null
}

export type WorkflowLaneActionKind =
  | 'reviewInAudit'
  | 'markDoneFromExecution'
  | 'improveInExecution'
  | 'markDoneFromAudit'

export type WorkflowLaneAction = {
  kind: WorkflowLaneActionKind
  variant: 'default' | 'primary'
  testId: string
  idleLabel: string
  busyLabel: string
  candidateWorkspaceHash?: string | null
  reviewCommitSha?: string | null
}

export type WorkflowThreadLane = {
  lane: ThreadTab
  threadId: string | null
  policy: WorkflowPolicy
  sessionConfig: SessionConfig
  actions: WorkflowLaneAction[]
}

export type WorkflowProjection = {
  lanes: Record<ThreadTab, WorkflowThreadLane>
  activeLane: ThreadTab
  active: WorkflowThreadLane
  isLoaded: boolean
}

export type ResolveWorkflowThreadLaneInput = {
  workflowState: NodeWorkflowView | null | undefined
  threadTab: ThreadTab
  selectedModel?: string | null
  selectedModelProvider?: string | null
  projectPath?: string | null
  isReviewNode?: boolean
}

export type ResolveWorkflowProjectionInput = Omit<ResolveWorkflowThreadLaneInput, 'threadTab'> & {
  activeLane: ThreadTab
}

export type ResolveWorkflowSubmitTurnPolicyInput = {
  lane: WorkflowThreadLane
  requestedPolicy?: ComposerRequestedPolicy | null
}

function resolveWorkflowThreadId(
  workflowState: NodeWorkflowView | null | undefined,
  lane: ThreadTab,
): string | null {
  if (!workflowState) {
    return null
  }
  if (lane === 'ask') {
    return workflowState.askThreadId ?? null
  }
  if (lane === 'execution') {
    return workflowState.executionThreadId
  }
  if (lane === 'audit') {
    return workflowState.reviewThreadId
  }
  return null
}

function resolveWorkflowPolicy(input: {
  workflowState: NodeWorkflowView | null | undefined
  lane: ThreadTab
  threadId: string | null
  isReviewNode?: boolean
}): WorkflowPolicy {
  const { workflowState, lane, threadId, isReviewNode } = input
  if (!workflowState) {
    return {
      kind: 'default',
      canSubmit: false,
      disabledReason: 'Workflow state is not loaded.',
    }
  }
  if (!threadId) {
    return {
      kind: lane,
      canSubmit: false,
      disabledReason: 'No workflow thread is available for this lane.',
    }
  }
  if (isReviewNode) {
    return {
      kind: 'review-readonly',
      canSubmit: false,
      disabledReason: 'Review nodes are read-only.',
    }
  }
  if (lane === 'execution' && !workflowState.canSendExecutionMessage) {
    return {
      kind: 'execution',
      canSubmit: false,
      disabledReason: 'Execution follow-up messages are not enabled for this workflow state.',
    }
  }
  return {
    kind: lane,
    canSubmit: true,
    disabledReason: null,
  }
}

function resolveWorkflowActions(
  workflowState: NodeWorkflowView | null | undefined,
  lane: ThreadTab,
): WorkflowLaneAction[] {
  if (!workflowState) {
    return []
  }
  if (lane === 'execution') {
    const actions: WorkflowLaneAction[] = []
    if (workflowState.canReviewInAudit) {
      actions.push({
        kind: 'reviewInAudit',
        variant: 'default',
        testId: 'workflow-review-in-audit',
        idleLabel: 'Review in Audit',
        busyLabel: 'Starting Review...',
        candidateWorkspaceHash: workflowState.currentExecutionDecision?.candidateWorkspaceHash ?? null,
      })
    }
    if (workflowState.canMarkDoneFromExecution) {
      actions.push({
        kind: 'markDoneFromExecution',
        variant: 'primary',
        testId: 'workflow-mark-done-execution',
        idleLabel: 'Mark Done',
        busyLabel: 'Marking Done...',
        candidateWorkspaceHash: workflowState.currentExecutionDecision?.candidateWorkspaceHash ?? null,
      })
    }
    return actions
  }
  if (lane === 'audit') {
    const actions: WorkflowLaneAction[] = []
    if (workflowState.canImproveInExecution) {
      actions.push({
        kind: 'improveInExecution',
        variant: 'default',
        testId: 'workflow-improve-in-execution',
        idleLabel: 'Improve in Execution',
        busyLabel: 'Starting Improve...',
        reviewCommitSha: workflowState.currentAuditDecision?.reviewCommitSha ?? null,
      })
    }
    if (workflowState.canMarkDoneFromAudit) {
      actions.push({
        kind: 'markDoneFromAudit',
        variant: 'primary',
        testId: 'workflow-mark-done-audit',
        idleLabel: 'Mark Done',
        busyLabel: 'Marking Done...',
        reviewCommitSha: workflowState.currentAuditDecision?.reviewCommitSha ?? null,
      })
    }
    return actions
  }
  return []
}

function mergeRecordConfig(
  base: Record<string, unknown> | null | undefined,
  next: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null | undefined {
  if (next === undefined) {
    return base
  }
  if (next === null) {
    return null
  }
  return {
    ...(base ?? {}),
    ...next,
  }
}

export function mergeSessionConfig(
  base: SessionConfig | null | undefined,
  next: SessionConfig | null | undefined,
): SessionConfig {
  if (!base && !next) {
    return {}
  }
  const merged: SessionConfig = {
    ...(base ?? {}),
    ...(next ?? {}),
  }
  if (next?.reasoning === undefined) {
    merged.reasoning = base?.reasoning
  } else if (next.reasoning === null) {
    merged.reasoning = null
  } else {
    merged.reasoning = {
      ...(base?.reasoning ?? {}),
      ...next.reasoning,
    }
  }
  merged.config = mergeRecordConfig(base?.config, next?.config)
  return merged
}

export function resolveWorkflowThreadLane(
  input: ResolveWorkflowThreadLaneInput,
): WorkflowThreadLane {
  const threadId = resolveWorkflowThreadId(input.workflowState, input.threadTab)
  const policy = resolveWorkflowPolicy({
    workflowState: input.workflowState,
    lane: input.threadTab,
    threadId,
    isReviewNode: input.isReviewNode,
  })

  return {
    lane: input.threadTab,
    threadId,
    policy,
    sessionConfig: {
      model: input.selectedModel ?? null,
      modelProvider: input.selectedModelProvider ?? null,
      cwd: input.projectPath ?? null,
    },
    actions: resolveWorkflowActions(input.workflowState, input.threadTab),
  }
}

export function resolveWorkflowProjection(
  input: ResolveWorkflowProjectionInput,
): WorkflowProjection {
  const { activeLane, ...laneInput } = input
  const resolveLane = (threadTab: ThreadTab): WorkflowThreadLane =>
    resolveWorkflowThreadLane({
      ...laneInput,
      threadTab,
    })
  const lanes: Record<ThreadTab, WorkflowThreadLane> = {
    ask: resolveLane('ask'),
    execution: resolveLane('execution'),
    audit: resolveLane('audit'),
    package: resolveLane('package'),
  }

  return {
    lanes,
    activeLane,
    active: lanes[activeLane],
    isLoaded: Boolean(input.workflowState),
  }
}

function sessionConfigFromRequestedPolicy(
  requestedPolicy: ComposerRequestedPolicy | null | undefined,
): SessionConfig {
  if (!requestedPolicy) {
    return {}
  }
  return {
    ...(requestedPolicy.model === undefined ? {} : { model: requestedPolicy.model }),
    ...(requestedPolicy.effort === undefined
      ? {}
      : {
          reasoning: {
            effort: requestedPolicy.effort === 'extra-high' ? 'xhigh' : requestedPolicy.effort,
            summary: null,
          },
        }),
  }
}

function withAccessPolicy(
  basePolicy: TurnExecutionPolicy,
  requestedPolicy: ComposerRequestedPolicy | null | undefined,
): TurnExecutionPolicy {
  if (requestedPolicy?.accessMode === 'full-access') {
    return {
      ...basePolicy,
      approvalPolicy: 'never',
      sandboxPolicy: { type: 'dangerFullAccess' },
    }
  }
  if (requestedPolicy?.accessMode === 'default-permissions') {
    return {
      ...basePolicy,
      approvalPolicy: 'on-request',
      sandboxPolicy: { type: 'workspaceWrite' },
    }
  }
  if (requestedPolicy?.accessMode === 'read-only') {
    return {
      ...basePolicy,
      approvalPolicy: 'on-request',
      sandboxPolicy: { type: 'readOnly' },
    }
  }
  return basePolicy
}

export function resolveWorkflowSubmitTurnPolicy(
  input: ResolveWorkflowSubmitTurnPolicyInput,
): TurnExecutionPolicy {
  const requestedConfig = sessionConfigFromRequestedPolicy(input.requestedPolicy)
  const merged = mergeSessionConfig(input.lane.sessionConfig, requestedConfig)
  return withAccessPolicy(toTurnExecutionPolicy(merged), input.requestedPolicy)
}
