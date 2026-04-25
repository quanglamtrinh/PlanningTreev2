import type { WorkflowActionV2, WorkflowStateV2 } from '../workflow_v2/types'
import { toTurnExecutionPolicy, type SessionConfig, type TurnExecutionPolicy } from '../session_v2/contracts'
import type { ComposerRequestedPolicy } from '../session_v2/components/ComposerPane'
import type { ThreadTab } from './surfaceRouting'

export type WorkflowPolicyKindV2 =
  | 'ask'
  | 'execution'
  | 'audit'
  | 'package'
  | 'review-readonly'
  | 'default'

export type WorkflowPolicyV2 = {
  kind: WorkflowPolicyKindV2
  canSubmit: boolean
  disabledReason?: string | null
}

export type WorkflowLaneActionKindV2 = WorkflowActionV2

export type WorkflowLaneActionV2 = {
  kind: WorkflowLaneActionKindV2
  variant: 'default' | 'primary'
  testId: string
  idleLabel: string
  busyLabel: string
  candidateWorkspaceHash?: string | null
  reviewCommitSha?: string | null
}

export type WorkflowThreadLaneV2 = {
  lane: ThreadTab
  threadId: string | null
  policy: WorkflowPolicyV2
  sessionConfig: SessionConfig
  actions: WorkflowLaneActionV2[]
}

export type WorkflowProjectionV2 = {
  lanes: Record<ThreadTab, WorkflowThreadLaneV2>
  activeLane: ThreadTab
  active: WorkflowThreadLaneV2
  isLoaded: boolean
}

export type ResolveWorkflowThreadLaneV2Input = {
  workflowState: WorkflowStateV2 | null | undefined
  threadTab: ThreadTab
  selectedModel?: string | null
  selectedModelProvider?: string | null
  projectPath?: string | null
  isReviewNode?: boolean
}

export type ResolveWorkflowProjectionV2Input = Omit<ResolveWorkflowThreadLaneV2Input, 'threadTab'> & {
  activeLane: ThreadTab
}

export type ResolveWorkflowSubmitTurnPolicyV2Input = {
  lane: WorkflowThreadLaneV2
  requestedPolicy?: ComposerRequestedPolicy | null
}

function hasAction(workflowState: WorkflowStateV2, action: WorkflowActionV2): boolean {
  return workflowState.allowedActions.includes(action)
}

function resolveWorkflowThreadId(
  workflowState: WorkflowStateV2 | null | undefined,
  lane: ThreadTab,
): string | null {
  if (!workflowState) {
    return null
  }
  if (lane === 'ask') {
    return workflowState.threads.askPlanning ?? null
  }
  if (lane === 'execution') {
    return workflowState.threads.execution ?? null
  }
  if (lane === 'audit') {
    return workflowState.threads.audit ?? null
  }
  return workflowState.threads.packageReview ?? null
}

function resolveWorkflowPolicy(input: {
  workflowState: WorkflowStateV2 | null | undefined
  lane: ThreadTab
  threadId: string | null
  isReviewNode?: boolean
}): WorkflowPolicyV2 {
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
  if (lane === 'ask') {
    return {
      kind: 'ask',
      canSubmit: true,
      disabledReason: null,
    }
  }
  return {
    kind: lane,
    canSubmit: false,
    disabledReason: 'Workflow V2 business lanes are controlled by workflow actions.',
  }
}

function resolveWorkflowActions(
  workflowState: WorkflowStateV2 | null | undefined,
  lane: ThreadTab,
): WorkflowLaneActionV2[] {
  if (!workflowState) {
    return []
  }
  if (lane === 'ask') {
    return []
  }
  if (lane === 'execution') {
    const actions: WorkflowLaneActionV2[] = []
    if (hasAction(workflowState, 'start_execution')) {
      actions.push({
        kind: 'start_execution',
        variant: 'primary',
        testId: 'workflow-start-execution',
        idleLabel: 'Start Execution Run',
        busyLabel: 'Starting Execution Run...',
      })
    }
    if (hasAction(workflowState, 'review_in_audit')) {
      actions.push({
        kind: 'review_in_audit',
        variant: 'default',
        testId: 'workflow-review-in-audit',
        idleLabel: 'Review in Audit',
        busyLabel: 'Starting Review...',
        candidateWorkspaceHash: workflowState.decisions.execution?.candidateWorkspaceHash ?? null,
      })
    }
    if (hasAction(workflowState, 'mark_done_from_execution')) {
      actions.push({
        kind: 'mark_done_from_execution',
        variant: 'primary',
        testId: 'workflow-mark-done-execution',
        idleLabel: 'Mark Done',
        busyLabel: 'Marking Done...',
        candidateWorkspaceHash: workflowState.decisions.execution?.candidateWorkspaceHash ?? null,
      })
    }
    return actions
  }
  if (lane === 'audit') {
    const actions: WorkflowLaneActionV2[] = []
    if (hasAction(workflowState, 'improve_in_execution')) {
      actions.push({
        kind: 'improve_in_execution',
        variant: 'default',
        testId: 'workflow-improve-in-execution',
        idleLabel: 'Improve in Execution',
        busyLabel: 'Starting Improve...',
        reviewCommitSha: workflowState.decisions.audit?.reviewCommitSha ?? null,
      })
    }
    if (hasAction(workflowState, 'mark_done_from_audit')) {
      actions.push({
        kind: 'mark_done_from_audit',
        variant: 'primary',
        testId: 'workflow-mark-done-audit',
        idleLabel: 'Mark Done',
        busyLabel: 'Marking Done...',
        reviewCommitSha: workflowState.decisions.audit?.reviewCommitSha ?? null,
      })
    }
    return actions
  }
  if (lane === 'package') {
    const actions: WorkflowLaneActionV2[] = []
    if (hasAction(workflowState, 'start_package_review')) {
      actions.push({
        kind: 'start_package_review',
        variant: 'primary',
        testId: 'workflow-start-package-review',
        idleLabel: 'Start Package Review',
        busyLabel: 'Starting Package Review...',
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

export function mergeSessionConfigV2(
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

export function resolveWorkflowThreadLaneV2(
  input: ResolveWorkflowThreadLaneV2Input,
): WorkflowThreadLaneV2 {
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

export function buildWorkflowProjectionV2(
  input: ResolveWorkflowProjectionV2Input,
): WorkflowProjectionV2 {
  const { activeLane, ...laneInput } = input
  const resolveLane = (threadTab: ThreadTab): WorkflowThreadLaneV2 =>
    resolveWorkflowThreadLaneV2({
      ...laneInput,
      threadTab,
    })
  const lanes: Record<ThreadTab, WorkflowThreadLaneV2> = {
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
  return basePolicy
}

export function resolveWorkflowSubmitTurnPolicyV2(
  input: ResolveWorkflowSubmitTurnPolicyV2Input,
): TurnExecutionPolicy {
  const requestedConfig = sessionConfigFromRequestedPolicy(input.requestedPolicy)
  const merged = mergeSessionConfigV2(input.lane.sessionConfig, requestedConfig)
  return withAccessPolicy(toTurnExecutionPolicy(merged), input.requestedPolicy)
}
