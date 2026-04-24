import { appendAuthToken, initAuthToken } from '../../../api/client'
import type { WorkflowEventV2, WorkflowStateV2 } from '../types'

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

export async function getWorkflowStateV2(projectId: string, nodeId: string): Promise<WorkflowStateV2> {
  await initAuthToken()
  return jsonFetchDirect<WorkflowStateV2>(
    `/v4/projects/${encodeURIComponent(projectId)}/nodes/${encodeURIComponent(nodeId)}/workflow-state`,
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
    event.type !== 'workflow/context_stale' &&
    event.type !== 'workflow/action_completed' &&
    event.type !== 'workflow/action_failed'
  ) {
    throw new Error(`Unsupported Workflow V2 event type: ${event.type}`)
  }
  return event as WorkflowEventV2
}
