export type WorkflowPhaseV2 =
  | 'planning'
  | 'ready_for_execution'
  | 'executing'
  | 'execution_completed'
  | 'review_pending'
  | 'audit_running'
  | 'audit_needs_changes'
  | 'audit_accepted'
  | 'done'
  | 'blocked'

export type WorkflowActionV2 =
  | 'start_execution'
  | 'review_in_audit'
  | 'mark_done_from_execution'
  | 'improve_in_execution'
  | 'mark_done_from_audit'
  | 'start_package_review'

export type WorkflowThreadRoleV2 = 'ask_planning' | 'execution' | 'audit' | 'package_review'

export type WorkflowStateThreadsV2 = {
  askPlanning: string | null
  execution: string | null
  audit: string | null
  packageReview: string | null
}

export type WorkflowExecutionDecisionV2 = {
  status: string
  sourceExecutionRunId?: string | null
  executionTurnId?: string | null
  candidateWorkspaceHash?: string | null
  summaryText?: string | null
  createdAt?: string | null
}

export type WorkflowAuditDecisionV2 = {
  status: string
  sourceAuditRunId?: string | null
  reviewCommitSha?: string | null
  finalReviewText?: string | null
  reviewDisposition?: string | null
  createdAt?: string | null
}

export type WorkflowStateDecisionsV2 = {
  execution: WorkflowExecutionDecisionV2 | null
  audit: WorkflowAuditDecisionV2 | null
}

export type WorkflowStateContextV2 = {
  frameVersion: number | null
  specVersion: number | null
  splitManifestVersion: number | null
}

export type WorkflowStateV2 = {
  schemaVersion: number
  projectId: string
  nodeId: string
  phase: WorkflowPhaseV2
  version: number
  threads: WorkflowStateThreadsV2
  decisions: WorkflowStateDecisionsV2
  context: WorkflowStateContextV2
  allowedActions: WorkflowActionV2[]
  activeExecutionRunId?: string | null
  activeAuditRunId?: string | null
  activeExecutionRun?: {
    runId?: string | null
    threadId?: string | null
    turnId?: string | null
    status?: string | null
  } | null
  activeAuditRun?: {
    runId?: string | null
    threadId?: string | null
    turnId?: string | null
    status?: string | null
  } | null
}

export type WorkflowEventTypeV2 =
  | 'workflow/state_changed'
  | 'workflow/action_completed'
  | 'workflow/action_failed'
  | 'workflow/artifact_job_started'
  | 'workflow/artifact_job_completed'
  | 'workflow/artifact_job_failed'
  | 'workflow/artifact_confirmed'
  | 'workflow/artifact_state_changed'

export type WorkflowEventV2 = {
  type: WorkflowEventTypeV2
  projectId: string
  nodeId: string
  phase?: WorkflowPhaseV2 | null
  version?: number | null
  action?: WorkflowActionV2 | null
  eventId: string
  occurredAt: string
  details?: Record<string, unknown>
}
