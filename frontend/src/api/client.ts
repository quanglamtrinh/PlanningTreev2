import type {
  AcceptLocalReviewResponse,
  AcceptRollupReviewResponse,
  AskRolloutMetricsSnapshot,
  BootstrapStatus,
  ClarifyGenAcceptedResponse,
  ClarifyGenStatusResponse,
  ClarifyState,
  CodexSnapshot,
  DetailState,
  FrameGenAcceptedResponse,
  FrameGenStatusResponse,
  NodeDocument,
  NodeDocumentKind,
  ResetThreadV2Response,
  ResetThreadV3Response,
  ResolveUserInputV2Response,
  ProjectSummary,
  ReviewState,
  Snapshot,
  StartTurnV2Response,
  NodeWorkflowView,
  PlanActionV3,
  PlanActionV3Response,
  SpecGenAcceptedResponse,
  SpecGenStatusResponse,
  SplitAcceptedResponse,
  SplitMode,
  SplitStatusResponse,
  ResolveUserInputV3Response,
  ThreadSnapshotV2,
  ThreadSnapshotV3,
  ThreadRole,
  WorkflowActionAcceptedResponse,
  WorkspaceTextFile,
} from './types'

type JsonBody = Record<string, unknown> | undefined

interface ErrorPayload {
  code?: string
  message?: string
}

interface V2SuccessEnvelope<T> {
  ok: true
  data: T
}

interface V2FailureEnvelope {
  ok: false
  error?: ErrorPayload
}

const DEFAULT_TIMEOUT_MS = 300_000

function buildThreadPathV2(projectId: string, nodeId: string, threadRole: ThreadRole): string {
  return `/v2/projects/${projectId}/nodes/${nodeId}/threads/${threadRole}`
}

function buildWorkflowStatePathV2(projectId: string, nodeId: string): string {
  return `/v2/projects/${projectId}/nodes/${nodeId}/workflow-state`
}

function buildWorkflowActionPathV2(
  projectId: string,
  nodeId: string,
  action:
    | 'finish-task'
    | 'mark-done-from-execution'
    | 'review-in-audit'
    | 'mark-done-from-audit'
    | 'improve-in-execution',
): string {
  return `/v2/projects/${projectId}/nodes/${nodeId}/workflow/${action}`
}

function buildThreadByIdBasePathV2(projectId: string, threadId: string): string {
  return `/v2/projects/${projectId}/threads/by-id/${threadId}`
}

function buildThreadByIdPathV2(projectId: string, threadId: string, nodeId: string): string {
  return `${buildThreadByIdBasePathV2(projectId, threadId)}?node_id=${encodeURIComponent(nodeId)}`
}

function buildThreadByIdBasePathV3(projectId: string, threadId: string): string {
  return `/v3/projects/${projectId}/threads/by-id/${threadId}`
}

function buildThreadByIdPathV3(projectId: string, threadId: string, nodeId: string): string {
  return `${buildThreadByIdBasePathV3(projectId, threadId)}?node_id=${encodeURIComponent(nodeId)}`
}

function buildThreadByIdTurnPathV3(projectId: string, threadId: string, nodeId: string): string {
  return `${buildThreadByIdBasePathV3(projectId, threadId)}/turns?node_id=${encodeURIComponent(nodeId)}`
}

export function buildThreadEventsUrlV2(
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
  afterSnapshotVersion?: number | null,
): string {
  const base = `${buildThreadPathV2(projectId, nodeId, threadRole)}/events`
  if (afterSnapshotVersion == null) {
    return base
  }
  return `${base}?after_snapshot_version=${encodeURIComponent(String(afterSnapshotVersion))}`
}

export function buildThreadByIdEventsUrlV2(
  projectId: string,
  nodeId: string,
  threadId: string,
  afterSnapshotVersion?: number | null,
): string {
  const base = `${buildThreadByIdBasePathV2(projectId, threadId)}/events?node_id=${encodeURIComponent(nodeId)}`
  if (afterSnapshotVersion == null) {
    return base
  }
  return `${base}&after_snapshot_version=${encodeURIComponent(String(afterSnapshotVersion))}`
}

export function buildThreadByIdEventsUrlV3(
  projectId: string,
  nodeId: string,
  threadId: string,
  afterSnapshotVersion?: number | null,
): string {
  const base = `${buildThreadByIdBasePathV3(projectId, threadId)}/events?node_id=${encodeURIComponent(nodeId)}`
  if (afterSnapshotVersion == null) {
    return base
  }
  return `${base}&after_snapshot_version=${encodeURIComponent(String(afterSnapshotVersion))}`
}

export function buildProjectEventsUrlV2(projectId: string): string {
  return `/v2/projects/${projectId}/events`
}

let _cachedAuthToken: string | null = null

/**
 * Eagerly fetch and cache the auth token before any API calls.
 * No-op when not running inside Electron.
 */
export async function initAuthToken(): Promise<void> {
  if (!window.electronAPI) return
  if (_cachedAuthToken === null) {
    _cachedAuthToken = await window.electronAPI.getAuthToken()
  }
}

async function getElectronAuthHeaders(): Promise<Record<string, string>> {
  if (!window.electronAPI) return {}
  if (_cachedAuthToken === null) {
    _cachedAuthToken = await window.electronAPI.getAuthToken()
  }
  return { Authorization: `Bearer ${_cachedAuthToken}` }
}

/** Append ?token= for SSE EventSource (which cannot send headers). */
export function appendAuthToken(url: string): string {
  if (!window.electronAPI || !_cachedAuthToken) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}token=${_cachedAuthToken}`
}

function requestTimeoutMs() {
  const raw = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS)
  if (Number.isFinite(raw) && raw >= 1_000) {
    return raw
  }
  return DEFAULT_TIMEOUT_MS
}

async function withRequestTimeout<T>(request: Promise<T>): Promise<T> {
  let timeoutId: ReturnType<typeof globalThis.setTimeout> | undefined
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = globalThis.setTimeout(() => {
      reject(new Error(`Request timed out after ${Math.round(requestTimeoutMs() / 1000)}s`))
    }, requestTimeoutMs())
  })

  try {
    return await Promise.race([request, timeout])
  } finally {
    if (timeoutId !== undefined) {
      globalThis.clearTimeout(timeoutId)
    }
  }
}

export class ApiError extends Error {
  status: number
  code: string | null

  constructor(status: number, payload: ErrorPayload | null) {
    super(payload?.message ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = payload?.code ?? null
  }
}

async function jsonFetch<T>(path: string, init?: RequestInit, body?: JsonBody): Promise<T> {
  const authHeaders = await getElectronAuthHeaders()
  const response = await withRequestTimeout(
    fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...(init?.headers ?? {}),
      },
      body: body === undefined ? init?.body : JSON.stringify(body),
    }),
  )

  if (!response.ok) {
    let payload: ErrorPayload | null = null
    try {
      payload = (await response.json()) as ErrorPayload
    } catch {
      payload = null
    }
    throw new ApiError(response.status, payload)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

async function jsonFetchV2<T>(path: string, init?: RequestInit, body?: JsonBody): Promise<T> {
  const authHeaders = await getElectronAuthHeaders()
  const response = await withRequestTimeout(
    fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...(init?.headers ?? {}),
      },
      body: body === undefined ? init?.body : JSON.stringify(body),
    }),
  )

  let payload: V2SuccessEnvelope<T> | V2FailureEnvelope | null = null
  if (response.status !== 204) {
    try {
      payload = (await response.json()) as V2SuccessEnvelope<T> | V2FailureEnvelope
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    const errorPayload = payload && 'ok' in payload && payload.ok === false ? payload.error ?? null : null
    throw new ApiError(response.status, errorPayload)
  }

  if (response.status === 204) {
    return undefined as T
  }

  if (!payload || !('ok' in payload) || payload.ok !== true) {
    throw new ApiError(response.status, {
      code: 'invalid_v2_response',
      message: 'The V2 API returned an unexpected response envelope.',
    })
  }

  return payload.data
}

export const api = {
  getBootstrapStatus(): Promise<BootstrapStatus> {
    return jsonFetch('/v1/bootstrap/status')
  },
  getCodexSnapshot(): Promise<CodexSnapshot> {
    return jsonFetch('/v1/codex/account')
  },
  listProjects(): Promise<ProjectSummary[]> {
    return jsonFetch('/v1/projects')
  },
  attachProjectFolder(folderPath: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>('/v1/projects/attach', { method: 'POST' }, {
      folder_path: folderPath,
    })
  },
  deleteProject(projectId: string): Promise<void> {
    return jsonFetch<void>(`/v1/projects/${projectId}`, { method: 'DELETE' })
  },
  getSnapshot(projectId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/snapshot`)
  },
  resetProjectToRoot(projectId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/reset-to-root`, { method: 'POST' })
  },
  setActiveNode(projectId: string, activeNodeId: string | null): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/active-node`, { method: 'PATCH' }, {
      active_node_id: activeNodeId,
    })
  },
  createChild(projectId: string, parentId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/nodes`, { method: 'POST' }, {
      parent_id: parentId,
    })
  },
  createTask(projectId: string, parentId: string, description: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/nodes/create-task`, { method: 'POST' }, {
      parent_id: parentId,
      description,
    })
  },
  splitNode(projectId: string, nodeId: string, mode: SplitMode): Promise<SplitAcceptedResponse> {
    return jsonFetch<SplitAcceptedResponse>(
      `/v1/projects/${projectId}/nodes/${nodeId}/split`,
      { method: 'POST' },
      { mode },
    )
  },
  getSplitStatus(projectId: string): Promise<SplitStatusResponse> {
    return jsonFetch<SplitStatusResponse>(`/v1/projects/${projectId}/split-status`)
  },
  updateNode(
    projectId: string,
    nodeId: string,
    payload: { title?: string; description?: string },
  ): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/nodes/${nodeId}`, { method: 'PATCH' }, payload)
  },
  getNodeDocument(
    projectId: string,
    nodeId: string,
    kind: NodeDocumentKind,
  ): Promise<NodeDocument> {
    return jsonFetch<NodeDocument>(`/v1/projects/${projectId}/nodes/${nodeId}/documents/${kind}`)
  },
  putNodeDocument(
    projectId: string,
    nodeId: string,
    kind: NodeDocumentKind,
    content: string,
  ): Promise<NodeDocument> {
    return jsonFetch<NodeDocument>(
      `/v1/projects/${projectId}/nodes/${nodeId}/documents/${kind}`,
      { method: 'PUT' },
      { content },
    )
  },
  getWorkspaceTextFile(projectId: string, relativePath: string): Promise<WorkspaceTextFile> {
    const q = new URLSearchParams({ relative_path: relativePath })
    return jsonFetch<WorkspaceTextFile>(`/v1/projects/${projectId}/workspace-text-file?${q}`)
  },
  putWorkspaceTextFile(
    projectId: string,
    relativePath: string,
    content: string,
  ): Promise<WorkspaceTextFile> {
    const q = new URLSearchParams({ relative_path: relativePath })
    return jsonFetch<WorkspaceTextFile>(
      `/v1/projects/${projectId}/workspace-text-file?${q}`,
      { method: 'PUT' },
      { content },
    )
  },
  getDetailState(projectId: string, nodeId: string): Promise<DetailState> {
    return jsonFetch<DetailState>(`/v1/projects/${projectId}/nodes/${nodeId}/detail-state`)
  },
  getWorkflowStateV2(projectId: string, nodeId: string): Promise<NodeWorkflowView> {
    return jsonFetchV2<NodeWorkflowView>(buildWorkflowStatePathV2(projectId, nodeId))
  },
  getReviewState(projectId: string, nodeId: string): Promise<ReviewState> {
    return jsonFetch<ReviewState>(`/v1/projects/${projectId}/nodes/${nodeId}/review-state`)
  },
  confirmFrame(projectId: string, nodeId: string): Promise<DetailState> {
    return jsonFetch<DetailState>(
      `/v1/projects/${projectId}/nodes/${nodeId}/confirm-frame`,
      { method: 'POST' },
    )
  },
  getClarify(projectId: string, nodeId: string): Promise<ClarifyState> {
    return jsonFetch<ClarifyState>(`/v1/projects/${projectId}/nodes/${nodeId}/clarify`)
  },
  updateClarify(
    projectId: string,
    nodeId: string,
    answers: { field_name: string; selected_option_id?: string | null; custom_answer?: string }[],
  ): Promise<ClarifyState> {
    return jsonFetch<ClarifyState>(
      `/v1/projects/${projectId}/nodes/${nodeId}/clarify`,
      { method: 'PUT' },
      { answers },
    )
  },
  confirmClarify(projectId: string, nodeId: string): Promise<DetailState> {
    return jsonFetch<DetailState>(
      `/v1/projects/${projectId}/nodes/${nodeId}/confirm-clarify`,
      { method: 'POST' },
    )
  },
  confirmSpec(projectId: string, nodeId: string): Promise<DetailState> {
    return jsonFetch<DetailState>(
      `/v1/projects/${projectId}/nodes/${nodeId}/confirm-spec`,
      { method: 'POST' },
    )
  },
  generateFrame(projectId: string, nodeId: string): Promise<FrameGenAcceptedResponse> {
    return jsonFetch<FrameGenAcceptedResponse>(
      `/v1/projects/${projectId}/nodes/${nodeId}/generate-frame`,
      { method: 'POST' },
    )
  },
  getFrameGenStatus(projectId: string, nodeId: string): Promise<FrameGenStatusResponse> {
    return jsonFetch<FrameGenStatusResponse>(
      `/v1/projects/${projectId}/nodes/${nodeId}/frame-generation-status`,
    )
  },
  generateClarify(projectId: string, nodeId: string): Promise<ClarifyGenAcceptedResponse> {
    return jsonFetch<ClarifyGenAcceptedResponse>(
      `/v1/projects/${projectId}/nodes/${nodeId}/generate-clarify`,
      { method: 'POST' },
    )
  },
  getClarifyGenStatus(projectId: string, nodeId: string): Promise<ClarifyGenStatusResponse> {
    return jsonFetch<ClarifyGenStatusResponse>(
      `/v1/projects/${projectId}/nodes/${nodeId}/clarify-generation-status`,
    )
  },
  generateSpec(projectId: string, nodeId: string): Promise<SpecGenAcceptedResponse> {
    return jsonFetch<SpecGenAcceptedResponse>(
      `/v1/projects/${projectId}/nodes/${nodeId}/generate-spec`,
      { method: 'POST' },
    )
  },
  getSpecGenStatus(projectId: string, nodeId: string): Promise<SpecGenStatusResponse> {
    return jsonFetch<SpecGenStatusResponse>(
      `/v1/projects/${projectId}/nodes/${nodeId}/spec-generation-status`,
    )
  },
  getAskRolloutMetrics(): Promise<AskRolloutMetricsSnapshot> {
    return jsonFetch<AskRolloutMetricsSnapshot>(`/v1/ask-rollout/metrics`)
  },
  reportAskRolloutMetricEvent(event: 'stream_reconnect' | 'stream_error'): Promise<{ ok: boolean }> {
    return jsonFetch<{ ok: boolean }>(
      `/v1/ask-rollout/metrics/events`,
      { method: 'POST' },
      { event },
    )
  },
  finishTask(projectId: string, nodeId: string): Promise<DetailState> {
    return jsonFetch<DetailState>(`/v1/projects/${projectId}/nodes/${nodeId}/finish-task`, {
      method: 'POST',
    })
  },
  acceptLocalReview(
    projectId: string,
    nodeId: string,
    summary: string,
  ): Promise<AcceptLocalReviewResponse> {
    return jsonFetch<AcceptLocalReviewResponse>(
      `/v1/projects/${projectId}/nodes/${nodeId}/accept-local-review`,
      { method: 'POST' },
      { summary },
    )
  },
  acceptRollupReview(
    projectId: string,
    reviewNodeId: string,
  ): Promise<AcceptRollupReviewResponse> {
    return jsonFetch<AcceptRollupReviewResponse>(
      `/v1/projects/${projectId}/nodes/${reviewNodeId}/accept-rollup-review`,
      { method: 'POST' },
    )
  },
  initGit(projectId: string): Promise<{ status: string; head_sha: string; message: string }> {
    return jsonFetch(`/v1/projects/${projectId}/git/init`, { method: 'POST' })
  },
  resetWorkspace(
    projectId: string,
    nodeId: string,
    target: 'initial' | 'head',
  ): Promise<{ status: string; target_sha: string; current_head_sha: string; task_present_in_current_workspace: boolean; detail_state: DetailState }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/reset-workspace`, { method: 'POST' }, { target })
  },
  async getThreadSnapshotV2(
    projectId: string,
    nodeId: string,
    threadRole: ThreadRole,
  ): Promise<ThreadSnapshotV2> {
    const response = await jsonFetchV2<{ snapshot: ThreadSnapshotV2 }>(
      buildThreadPathV2(projectId, nodeId, threadRole),
    )
    return response.snapshot
  },
  async getThreadSnapshotByIdV2(
    projectId: string,
    nodeId: string,
    threadId: string,
  ): Promise<ThreadSnapshotV2> {
    const response = await jsonFetchV2<{ snapshot: ThreadSnapshotV2 }>(
      buildThreadByIdPathV2(projectId, threadId, nodeId),
    )
    return response.snapshot
  },
  async getThreadSnapshotByIdV3(
    projectId: string,
    nodeId: string,
    threadId: string,
  ): Promise<ThreadSnapshotV3> {
    const response = await jsonFetchV2<{ snapshot: ThreadSnapshotV3 }>(
      buildThreadByIdPathV3(projectId, threadId, nodeId),
    )
    return response.snapshot
  },
  resolveThreadUserInputByIdV3(
    projectId: string,
    nodeId: string,
    threadId: string,
    requestId: string,
    answers: ResolveUserInputV3Response['answers'],
  ): Promise<ResolveUserInputV3Response> {
    return jsonFetchV2<ResolveUserInputV3Response>(
      `${buildThreadByIdBasePathV3(projectId, threadId)}/requests/${requestId}/resolve?node_id=${encodeURIComponent(nodeId)}`,
      { method: 'POST' },
      { answers },
    )
  },
  planActionByIdV3(
    projectId: string,
    nodeId: string,
    threadId: string,
    payload: {
      action: PlanActionV3
      planItemId: string
      revision: number
      text?: string
      idempotencyKey?: string
    },
  ): Promise<PlanActionV3Response> {
    return jsonFetchV2<PlanActionV3Response>(
      `${buildThreadByIdBasePathV3(projectId, threadId)}/plan-actions?node_id=${encodeURIComponent(nodeId)}`,
      { method: 'POST' },
      payload,
    )
  },
  startThreadTurnByIdV3(
    projectId: string,
    nodeId: string,
    threadId: string,
    text: string,
    metadata: Record<string, unknown> = {},
  ): Promise<StartTurnV2Response> {
    return jsonFetchV2<StartTurnV2Response>(
      buildThreadByIdTurnPathV3(projectId, threadId, nodeId),
      { method: 'POST' },
      { text, metadata },
    )
  },
  resetThreadByIdV3(
    projectId: string,
    nodeId: string,
    threadId: string,
  ): Promise<ResetThreadV3Response> {
    return jsonFetchV2<ResetThreadV3Response>(
      `${buildThreadByIdBasePathV3(projectId, threadId)}/reset?node_id=${encodeURIComponent(nodeId)}`,
      { method: 'POST' },
    )
  },
  startThreadTurnV2(
    projectId: string,
    nodeId: string,
    threadRole: ThreadRole,
    text: string,
    metadata: Record<string, unknown> = {},
  ): Promise<StartTurnV2Response> {
    return jsonFetchV2<StartTurnV2Response>(
      `${buildThreadPathV2(projectId, nodeId, threadRole)}/turns`,
      { method: 'POST' },
      { text, metadata },
    )
  },
  resolveThreadUserInputV2(
    projectId: string,
    nodeId: string,
    threadRole: ThreadRole,
    requestId: string,
    answers: ResolveUserInputV2Response['answers'],
  ): Promise<ResolveUserInputV2Response> {
    return jsonFetchV2<ResolveUserInputV2Response>(
      `${buildThreadPathV2(projectId, nodeId, threadRole)}/requests/${requestId}/resolve`,
      { method: 'POST' },
      { answers },
    )
  },
  resetThreadV2(
    projectId: string,
    nodeId: string,
    threadRole: ThreadRole,
  ): Promise<ResetThreadV2Response> {
    return jsonFetchV2<ResetThreadV2Response>(
      `${buildThreadPathV2(projectId, nodeId, threadRole)}/reset`,
      { method: 'POST' },
    )
  },
  finishTaskWorkflowV2(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
  ): Promise<WorkflowActionAcceptedResponse> {
    return jsonFetchV2<WorkflowActionAcceptedResponse>(
      buildWorkflowActionPathV2(projectId, nodeId, 'finish-task'),
      { method: 'POST' },
      { idempotencyKey },
    )
  },
  markDoneFromExecutionV2(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
    expectedWorkspaceHash: string,
  ): Promise<NodeWorkflowView> {
    return jsonFetchV2<NodeWorkflowView>(
      buildWorkflowActionPathV2(projectId, nodeId, 'mark-done-from-execution'),
      { method: 'POST' },
      { idempotencyKey, expectedWorkspaceHash },
    )
  },
  reviewInAuditV2(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
    expectedWorkspaceHash: string,
  ): Promise<WorkflowActionAcceptedResponse> {
    return jsonFetchV2<WorkflowActionAcceptedResponse>(
      buildWorkflowActionPathV2(projectId, nodeId, 'review-in-audit'),
      { method: 'POST' },
      { idempotencyKey, expectedWorkspaceHash },
    )
  },
  markDoneFromAuditV2(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
    expectedReviewCommitSha: string,
  ): Promise<NodeWorkflowView> {
    return jsonFetchV2<NodeWorkflowView>(
      buildWorkflowActionPathV2(projectId, nodeId, 'mark-done-from-audit'),
      { method: 'POST' },
      { idempotencyKey, expectedReviewCommitSha },
    )
  },
  improveInExecutionV2(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
    expectedReviewCommitSha: string,
  ): Promise<WorkflowActionAcceptedResponse> {
    return jsonFetchV2<WorkflowActionAcceptedResponse>(
      buildWorkflowActionPathV2(projectId, nodeId, 'improve-in-execution'),
      { method: 'POST' },
      { idempotencyKey, expectedReviewCommitSha },
    )
  },
}
