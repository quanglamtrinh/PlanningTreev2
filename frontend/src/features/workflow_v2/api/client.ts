import { appendAuthToken, initAuthToken } from '../../../api/client'
import type { WorkflowEventV2, WorkflowStateV2, WorkflowThreadRoleV2 } from '../types'

type ErrorPayload = {
  code?: string
  message?: string
  details?: Record<string, unknown>
}

export class WorkflowV2ApiError extends Error {
  status: number
  code: string | null
  details: Record<string, unknown>

  constructor(status: number, payload: ErrorPayload | null) {
    super(payload?.message ?? `Workflow V2 request failed with status ${status}`)
    this.name = 'WorkflowV2ApiError'
    this.status = status
    this.code = payload?.code ?? null
    this.details = payload?.details ?? {}
  }
}

async function getElectronAuthHeaders(): Promise<Record<string, string>> {
  if (!window.electronAPI) {
    return {}
  }
  const token = await window.electronAPI.getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function jsonFetchDirect<T>(path: string, init?: RequestInit): Promise<T> {
  const authHeaders = await getElectronAuthHeaders()
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    let payload: ErrorPayload | null = null
    try {
      payload = (await response.json()) as ErrorPayload
    } catch {
      payload = null
    }
    throw new WorkflowV2ApiError(response.status, payload)
  }

  return (await response.json()) as T
}

function workflowNodePath(projectId: string, nodeId: string): string {
  return `/v4/projects/${encodeURIComponent(projectId)}/nodes/${encodeURIComponent(nodeId)}`
}

async function jsonPostDirect<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  return jsonFetchDirect<T>(path, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export type WorkflowModelPolicyV2 = {
  model?: string | null
  modelProvider?: string | null
}

export type WorkflowMutationResponseV2 = {
  workflowState?: WorkflowStateV2
  accepted?: boolean
  threadId?: string | null
  turnId?: string | null
  executionRunId?: string | null
  auditRunId?: string | null
  reviewCycleId?: string | null
  reviewThreadId?: string | null
  reviewCommitSha?: string | null
}

export type EnsureWorkflowThreadResponseV2 = WorkflowMutationResponseV2 & {
  binding?: {
    projectId: string
    nodeId: string
    role: WorkflowThreadRoleV2
    threadId: string
    createdFrom?: string | null
    contextPacketHash?: string | null
    sourceVersions?: Record<string, unknown>
  }
}

export async function getWorkflowStateV2(projectId: string, nodeId: string): Promise<WorkflowStateV2> {
  await initAuthToken()
  return jsonFetchDirect<WorkflowStateV2>(
    `${workflowNodePath(projectId, nodeId)}/workflow-state`,
  )
}

export async function ensureWorkflowThreadV2(
  projectId: string,
  nodeId: string,
  role: WorkflowThreadRoleV2,
  payload: WorkflowModelPolicyV2 & {
    idempotencyKey: string
  },
): Promise<EnsureWorkflowThreadResponseV2> {
  await initAuthToken()
  return jsonPostDirect<EnsureWorkflowThreadResponseV2>(
    `${workflowNodePath(projectId, nodeId)}/threads/${encodeURIComponent(role)}/ensure`,
    {
      idempotencyKey: payload.idempotencyKey,
      model: payload.model ?? null,
      modelProvider: payload.modelProvider ?? null,
    },
  )
}

export async function startExecutionV2(
  projectId: string,
  nodeId: string,
  payload: WorkflowModelPolicyV2 & { idempotencyKey: string },
): Promise<WorkflowMutationResponseV2> {
  await initAuthToken()
  return jsonPostDirect<WorkflowMutationResponseV2>(
    `${workflowNodePath(projectId, nodeId)}/execution/start`,
    {
      idempotencyKey: payload.idempotencyKey,
      model: payload.model ?? null,
      modelProvider: payload.modelProvider ?? null,
    },
  )
}

export async function markDoneFromExecutionV2(
  projectId: string,
  nodeId: string,
  payload: { idempotencyKey: string; expectedWorkspaceHash: string },
): Promise<WorkflowMutationResponseV2> {
  await initAuthToken()
  return jsonPostDirect<WorkflowMutationResponseV2>(
    `${workflowNodePath(projectId, nodeId)}/execution/mark-done`,
    payload,
  )
}

export async function startAuditV2(
  projectId: string,
  nodeId: string,
  payload: WorkflowModelPolicyV2 & {
    idempotencyKey: string
    expectedWorkspaceHash: string
  },
): Promise<WorkflowMutationResponseV2> {
  await initAuthToken()
  return jsonPostDirect<WorkflowMutationResponseV2>(
    `${workflowNodePath(projectId, nodeId)}/audit/start`,
    {
      idempotencyKey: payload.idempotencyKey,
      expectedWorkspaceHash: payload.expectedWorkspaceHash,
      model: payload.model ?? null,
      modelProvider: payload.modelProvider ?? null,
    },
  )
}

export async function improveExecutionV2(
  projectId: string,
  nodeId: string,
  payload: WorkflowModelPolicyV2 & {
    idempotencyKey: string
    expectedReviewCommitSha: string
  },
): Promise<WorkflowMutationResponseV2> {
  await initAuthToken()
  return jsonPostDirect<WorkflowMutationResponseV2>(
    `${workflowNodePath(projectId, nodeId)}/execution/improve`,
    {
      idempotencyKey: payload.idempotencyKey,
      expectedReviewCommitSha: payload.expectedReviewCommitSha,
      model: payload.model ?? null,
      modelProvider: payload.modelProvider ?? null,
    },
  )
}

export async function acceptAuditV2(
  projectId: string,
  nodeId: string,
  payload: { idempotencyKey: string; expectedReviewCommitSha: string },
): Promise<WorkflowMutationResponseV2> {
  await initAuthToken()
  return jsonPostDirect<WorkflowMutationResponseV2>(
    `${workflowNodePath(projectId, nodeId)}/audit/accept`,
    payload,
  )
}

export async function startPackageReviewV2(
  projectId: string,
  nodeId: string,
  payload: WorkflowModelPolicyV2 & { idempotencyKey: string },
): Promise<WorkflowMutationResponseV2> {
  await initAuthToken()
  return jsonPostDirect<WorkflowMutationResponseV2>(
    `${workflowNodePath(projectId, nodeId)}/package-review/start`,
    {
      idempotencyKey: payload.idempotencyKey,
      model: payload.model ?? null,
      modelProvider: payload.modelProvider ?? null,
    },
  )
}

export function buildProjectEventsUrlV2(projectId: string): string {
  return `/v4/projects/${encodeURIComponent(projectId)}/events`
}

export function openWorkflowEventsStreamV2(projectId: string): EventSource {
  return new EventSource(appendAuthToken(buildProjectEventsUrlV2(projectId)))
}

export function parseWorkflowEventV2(raw: string): WorkflowEventV2 {
  const parsed = JSON.parse(raw) as unknown
  if (!parsed || typeof parsed !== 'object') {
    throw new Error('Expected a Workflow V2 event object.')
  }
  const event = parsed as Partial<WorkflowEventV2>
  if (
    typeof event.type !== 'string' ||
    typeof event.projectId !== 'string' ||
    typeof event.nodeId !== 'string' ||
    typeof event.eventId !== 'string' ||
    typeof event.occurredAt !== 'string'
  ) {
    throw new Error('Workflow V2 event is missing required fields.')
  }
  if (
    event.type !== 'workflow/state_changed' &&
    event.type !== 'workflow/action_completed' &&
    event.type !== 'workflow/action_failed' &&
    event.type !== 'workflow/artifact_job_started' &&
    event.type !== 'workflow/artifact_job_completed' &&
    event.type !== 'workflow/artifact_job_failed' &&
    event.type !== 'workflow/artifact_confirmed' &&
    event.type !== 'workflow/artifact_state_changed'
  ) {
    throw new Error(`Unsupported Workflow V2 event type: ${event.type}`)
  }
  return event as WorkflowEventV2
}
