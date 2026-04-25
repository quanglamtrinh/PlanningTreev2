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
  LocalUsageSnapshot,
  NodeDocument,
  NodeDocumentKind,
  ResetThreadV3Response,
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
  ConversationItemV3,
  ResolveUserInputV3Response,
  ThreadSnapshotV3,
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

interface ThreadHistoryPageByIdV3Response {
  items: ConversationItemV3[]
  has_more: boolean
  next_before_sequence: number | null
  total_item_count: number
}

const DEFAULT_TIMEOUT_MS = 300_000

function buildWorkflowStatePathV3(projectId: string, nodeId: string): string {
  return `/v3/projects/${projectId}/nodes/${nodeId}/workflow-state`
}

function buildWorkflowActionPathV3(
  projectId: string,
  nodeId: string,
  action:
    | 'finish-task'
    | 'mark-done-from-execution'
    | 'review-in-audit'
    | 'mark-done-from-audit'
    | 'improve-in-execution',
): string {
  return `/v3/projects/${projectId}/nodes/${nodeId}/workflow/${action}`
}

function buildThreadByIdBasePathV3(projectId: string, threadId: string): string {
  return `/v3/projects/${projectId}/threads/by-id/${threadId}`
}

function buildThreadByIdPathV3(
  projectId: string,
  threadId: string,
  nodeId: string,
  options?: { liveLimit?: number | null },
): string {
  const queryParts = [`node_id=${encodeURIComponent(nodeId)}`]
  const liveLimit = options?.liveLimit
  if (liveLimit != null && Number.isFinite(liveLimit) && liveLimit > 0) {
    queryParts.push(`live_limit=${encodeURIComponent(String(Math.floor(liveLimit)))}`)
  }
  return `${buildThreadByIdBasePathV3(projectId, threadId)}?${queryParts.join('&')}`
}

function buildThreadByIdHistoryPathV3(
  projectId: string,
  threadId: string,
  nodeId: string,
  options?: { beforeSequence?: number | null; limit?: number | null },
): string {
  const queryParts = [`node_id=${encodeURIComponent(nodeId)}`]
  if (options?.beforeSequence != null && Number.isFinite(options.beforeSequence)) {
    queryParts.push(`before_sequence=${encodeURIComponent(String(Math.floor(options.beforeSequence)))}`)
  }
  if (options?.limit != null && Number.isFinite(options.limit) && options.limit > 0) {
    queryParts.push(`limit=${encodeURIComponent(String(Math.floor(options.limit)))}`)
  }
  return `${buildThreadByIdBasePathV3(projectId, threadId)}/history?${queryParts.join('&')}`
}

function buildThreadByIdTurnPathV3(projectId: string, threadId: string, nodeId: string): string {
  return `${buildThreadByIdBasePathV3(projectId, threadId)}/turns?node_id=${encodeURIComponent(nodeId)}`
}

function artifactNodePathV4(projectId: string, nodeId: string): string {
  return `/v4/projects/${encodeURIComponent(projectId)}/nodes/${encodeURIComponent(nodeId)}/artifacts`
}

function artifactProjectPathV4(projectId: string): string {
  return `/v4/projects/${encodeURIComponent(projectId)}`
}

function newIdempotencyKey(prefix: string): string {
  const random =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}:${random}`
}

type ArtifactConfirmResponse = {
  detailState: DetailState
}

type ClarifyUpdateV4Response = {
  clarify: ClarifyState
}

export function buildThreadByIdEventsUrlV3(
  projectId: string,
  nodeId: string,
  threadId: string,
  afterSnapshotVersion?: number | null,
  lastEventId?: string | null,
): string {
  const queryParts = [`node_id=${encodeURIComponent(nodeId)}`]
  if (afterSnapshotVersion != null) {
    queryParts.push(`after_snapshot_version=${encodeURIComponent(String(afterSnapshotVersion))}`)
  }
  const normalizedLastEventId =
    typeof lastEventId === 'string' && lastEventId.trim().length > 0 ? lastEventId.trim() : null
  if (normalizedLastEventId != null) {
    queryParts.push(`last_event_id=${encodeURIComponent(normalizedLastEventId)}`)
  }
  return `${buildThreadByIdBasePathV3(projectId, threadId)}/events?${queryParts.join('&')}`
}

export function buildProjectEventsUrlV3(projectId: string): string {
  return `/v3/projects/${projectId}/events`
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
    return jsonFetch('/v3/bootstrap/status')
  },
  getCodexSnapshot(): Promise<CodexSnapshot> {
    return jsonFetch('/v3/codex/account')
  },
  getLocalUsageSnapshot(days?: number): Promise<LocalUsageSnapshot> {
    const query = days == null ? '' : `?days=${encodeURIComponent(String(days))}`
    return jsonFetch<LocalUsageSnapshot>(`/v3/codex/usage/local${query}`)
  },
  listProjects(): Promise<ProjectSummary[]> {
    return jsonFetch('/v3/projects')
  },
  attachProjectFolder(folderPath: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>('/v3/projects/attach', { method: 'POST' }, {
      folder_path: folderPath,
    })
  },
  deleteProject(projectId: string): Promise<void> {
    return jsonFetch<void>(`/v3/projects/${projectId}`, { method: 'DELETE' })
  },
  getSnapshot(projectId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v3/projects/${projectId}/snapshot`)
  },
  resetProjectToRoot(projectId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v3/projects/${projectId}/reset-to-root`, { method: 'POST' })
  },
  setActiveNode(projectId: string, activeNodeId: string | null): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v3/projects/${projectId}/active-node`, { method: 'PATCH' }, {
      active_node_id: activeNodeId,
    })
  },
  createChild(projectId: string, parentId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v3/projects/${projectId}/nodes`, { method: 'POST' }, {
      parent_id: parentId,
    })
  },
  createTask(projectId: string, parentId: string, description: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v3/projects/${projectId}/nodes/create-task`, { method: 'POST' }, {
      parent_id: parentId,
      description,
    })
  },
  splitNode(projectId: string, nodeId: string, mode: SplitMode): Promise<SplitAcceptedResponse> {
    return jsonFetch<SplitAcceptedResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/split/start`,
      { method: 'POST' },
      { idempotencyKey: newIdempotencyKey('split_start'), mode },
    )
  },
  getSplitStatus(projectId: string): Promise<SplitStatusResponse> {
    return jsonFetch<SplitStatusResponse>(`${artifactProjectPathV4(projectId)}/artifact-jobs/split/status`)
  },
  updateNode(
    projectId: string,
    nodeId: string,
    payload: { title?: string; description?: string },
  ): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v3/projects/${projectId}/nodes/${nodeId}`, { method: 'PATCH' }, payload)
  },
  getNodeDocument(
    projectId: string,
    nodeId: string,
    kind: NodeDocumentKind,
  ): Promise<NodeDocument> {
    return jsonFetch<NodeDocument>(`/v3/projects/${projectId}/nodes/${nodeId}/documents/${kind}`)
  },
  putNodeDocument(
    projectId: string,
    nodeId: string,
    kind: NodeDocumentKind,
    content: string,
  ): Promise<NodeDocument> {
    return jsonFetch<NodeDocument>(
      `/v3/projects/${projectId}/nodes/${nodeId}/documents/${kind}`,
      { method: 'PUT' },
      { content },
    )
  },
  getWorkspaceTextFile(projectId: string, relativePath: string): Promise<WorkspaceTextFile> {
    const q = new URLSearchParams({ relative_path: relativePath })
    return jsonFetch<WorkspaceTextFile>(`/v3/projects/${projectId}/workspace-text-file?${q}`)
  },
  putWorkspaceTextFile(
    projectId: string,
    relativePath: string,
    content: string,
  ): Promise<WorkspaceTextFile> {
    const q = new URLSearchParams({ relative_path: relativePath })
    return jsonFetch<WorkspaceTextFile>(
      `/v3/projects/${projectId}/workspace-text-file?${q}`,
      { method: 'PUT' },
      { content },
    )
  },
  getDetailState(projectId: string, nodeId: string): Promise<DetailState> {
    return jsonFetch<DetailState>(`/v3/projects/${projectId}/nodes/${nodeId}/detail-state`)
  },
  getWorkflowStateV3(projectId: string, nodeId: string): Promise<NodeWorkflowView> {
    return jsonFetchV2<NodeWorkflowView>(buildWorkflowStatePathV3(projectId, nodeId))
  },
  getReviewState(projectId: string, nodeId: string): Promise<ReviewState> {
    return jsonFetch<ReviewState>(`/v3/projects/${projectId}/nodes/${nodeId}/review-state`)
  },
  async confirmFrame(projectId: string, nodeId: string): Promise<DetailState> {
    const response = await jsonFetch<ArtifactConfirmResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/frame/confirm`,
      { method: 'POST' },
      { idempotencyKey: newIdempotencyKey('frame_confirm') },
    )
    return response.detailState
  },
  getClarify(projectId: string, nodeId: string): Promise<ClarifyState> {
    return jsonFetch<ClarifyState>(`${artifactNodePathV4(projectId, nodeId)}/clarify`)
  },
  async updateClarify(
    projectId: string,
    nodeId: string,
    answers: { field_name: string; selected_option_id?: string | null; custom_answer?: string }[],
  ): Promise<ClarifyState> {
    const response = await jsonFetch<ClarifyUpdateV4Response>(
      `${artifactNodePathV4(projectId, nodeId)}/clarify`,
      { method: 'PUT' },
      { answers, idempotencyKey: newIdempotencyKey('clarify_update') },
    )
    return response.clarify
  },
  async confirmClarify(projectId: string, nodeId: string): Promise<DetailState> {
    const response = await jsonFetch<ArtifactConfirmResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/clarify/confirm`,
      { method: 'POST' },
      { idempotencyKey: newIdempotencyKey('clarify_confirm') },
    )
    return response.detailState
  },
  async confirmSpec(projectId: string, nodeId: string): Promise<DetailState> {
    const response = await jsonFetch<ArtifactConfirmResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/spec/confirm`,
      { method: 'POST' },
      { idempotencyKey: newIdempotencyKey('spec_confirm') },
    )
    return response.detailState
  },
  generateFrame(projectId: string, nodeId: string): Promise<FrameGenAcceptedResponse> {
    return jsonFetch<FrameGenAcceptedResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/frame/generate`,
      { method: 'POST' },
      { idempotencyKey: newIdempotencyKey('frame_generate') },
    )
  },
  getFrameGenStatus(projectId: string, nodeId: string): Promise<FrameGenStatusResponse> {
    return jsonFetch<FrameGenStatusResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/frame/generation-status`,
    )
  },
  generateClarify(projectId: string, nodeId: string): Promise<ClarifyGenAcceptedResponse> {
    return jsonFetch<ClarifyGenAcceptedResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/clarify/generate`,
      { method: 'POST' },
      { idempotencyKey: newIdempotencyKey('clarify_generate') },
    )
  },
  getClarifyGenStatus(projectId: string, nodeId: string): Promise<ClarifyGenStatusResponse> {
    return jsonFetch<ClarifyGenStatusResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/clarify/generation-status`,
    )
  },
  generateSpec(projectId: string, nodeId: string): Promise<SpecGenAcceptedResponse> {
    return jsonFetch<SpecGenAcceptedResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/spec/generate`,
      { method: 'POST' },
      { idempotencyKey: newIdempotencyKey('spec_generate') },
    )
  },
  getSpecGenStatus(projectId: string, nodeId: string): Promise<SpecGenStatusResponse> {
    return jsonFetch<SpecGenStatusResponse>(
      `${artifactNodePathV4(projectId, nodeId)}/spec/generation-status`,
    )
  },
  getAskRolloutMetrics(): Promise<AskRolloutMetricsSnapshot> {
    return jsonFetch<AskRolloutMetricsSnapshot>(`/v3/ask-rollout/metrics`)
  },
  reportAskRolloutMetricEvent(event: 'stream_reconnect' | 'stream_error'): Promise<{ ok: boolean }> {
    return jsonFetch<{ ok: boolean }>(
      `/v3/ask-rollout/metrics/events`,
      { method: 'POST' },
      { event },
    )
  },
  finishTask(projectId: string, nodeId: string): Promise<DetailState> {
    return jsonFetch<DetailState>(`/v3/projects/${projectId}/nodes/${nodeId}/finish-task`, {
      method: 'POST',
    })
  },
  acceptLocalReview(
    projectId: string,
    nodeId: string,
    summary: string,
  ): Promise<AcceptLocalReviewResponse> {
    return jsonFetch<AcceptLocalReviewResponse>(
      `/v3/projects/${projectId}/nodes/${nodeId}/accept-local-review`,
      { method: 'POST' },
      { summary },
    )
  },
  acceptRollupReview(
    projectId: string,
    reviewNodeId: string,
  ): Promise<AcceptRollupReviewResponse> {
    return jsonFetch<AcceptRollupReviewResponse>(
      `/v3/projects/${projectId}/nodes/${reviewNodeId}/accept-rollup-review`,
      { method: 'POST' },
    )
  },
  initGit(projectId: string): Promise<{ status: string; head_sha: string; message: string }> {
    return jsonFetch(`/v3/projects/${projectId}/git/init`, { method: 'POST' })
  },
  resetWorkspace(
    projectId: string,
    nodeId: string,
    target: 'initial' | 'head',
  ): Promise<{ status: string; target_sha: string; current_head_sha: string; task_present_in_current_workspace: boolean; detail_state: DetailState }> {
    return jsonFetch(`/v3/projects/${projectId}/nodes/${nodeId}/reset-workspace`, { method: 'POST' }, { target })
  },
  async getThreadSnapshotByIdV3(
    projectId: string,
    nodeId: string,
    threadId: string,
    liveLimit?: number | null,
  ): Promise<ThreadSnapshotV3> {
    const response = await jsonFetchV2<{ snapshot: ThreadSnapshotV3 }>(
      buildThreadByIdPathV3(projectId, threadId, nodeId, { liveLimit }),
    )
    return response.snapshot
  },
  getThreadHistoryPageByIdV3(
    projectId: string,
    nodeId: string,
    threadId: string,
    options?: { beforeSequence?: number | null; limit?: number | null },
  ): Promise<ThreadHistoryPageByIdV3Response> {
    return jsonFetchV2<ThreadHistoryPageByIdV3Response>(
      buildThreadByIdHistoryPathV3(projectId, threadId, nodeId, options),
    )
  },
  async probeThreadByIdEventsCursorV3(
    projectId: string,
    nodeId: string,
    threadId: string,
    lastEventId: string,
  ): Promise<'ok' | 'mismatch'> {
    const authHeaders = await getElectronAuthHeaders()
    const response = await withRequestTimeout(
      fetch(buildThreadByIdEventsUrlV3(projectId, nodeId, threadId, null, lastEventId), {
        method: 'GET',
        headers: {
          ...authHeaders,
        },
      }),
    )

    if (response.status === 409) {
      let payload: V2FailureEnvelope | ErrorPayload | null = null
      try {
        payload = (await response.json()) as V2FailureEnvelope | ErrorPayload
      } catch {
        payload = null
      }
      const envelopeErrorCode =
        payload && 'ok' in payload && payload.ok === false ? payload.error?.code ?? null : null
      const bareErrorCode = payload && 'code' in payload ? (payload.code ?? null) : null
      const code = envelopeErrorCode ?? bareErrorCode
      if (code === 'conversation_stream_mismatch') {
        return 'mismatch'
      }
      throw new ApiError(
        response.status,
        payload && 'ok' in payload && payload.ok === false ? payload.error ?? null : (payload as ErrorPayload),
      )
    }

    if (!response.ok) {
      let payload: ErrorPayload | null = null
      try {
        payload = (await response.json()) as ErrorPayload
      } catch {
        payload = null
      }
      throw new ApiError(response.status, payload)
    }

    try {
      await response.body?.cancel()
    } catch {
      // no-op
    }
    return 'ok'
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
  finishTaskWorkflowV3(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
  ): Promise<WorkflowActionAcceptedResponse> {
    return jsonFetchV2<WorkflowActionAcceptedResponse>(
      buildWorkflowActionPathV3(projectId, nodeId, 'finish-task'),
      { method: 'POST' },
      { idempotencyKey },
    )
  },
  markDoneFromExecutionV3(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
    expectedWorkspaceHash: string,
  ): Promise<NodeWorkflowView> {
    return jsonFetchV2<NodeWorkflowView>(
      buildWorkflowActionPathV3(projectId, nodeId, 'mark-done-from-execution'),
      { method: 'POST' },
      { idempotencyKey, expectedWorkspaceHash },
    )
  },
  reviewInAuditV3(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
    expectedWorkspaceHash: string,
  ): Promise<WorkflowActionAcceptedResponse> {
    return jsonFetchV2<WorkflowActionAcceptedResponse>(
      buildWorkflowActionPathV3(projectId, nodeId, 'review-in-audit'),
      { method: 'POST' },
      { idempotencyKey, expectedWorkspaceHash },
    )
  },
  markDoneFromAuditV3(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
    expectedReviewCommitSha: string,
  ): Promise<NodeWorkflowView> {
    return jsonFetchV2<NodeWorkflowView>(
      buildWorkflowActionPathV3(projectId, nodeId, 'mark-done-from-audit'),
      { method: 'POST' },
      { idempotencyKey, expectedReviewCommitSha },
    )
  },
  improveInExecutionV3(
    projectId: string,
    nodeId: string,
    idempotencyKey: string,
    expectedReviewCommitSha: string,
  ): Promise<WorkflowActionAcceptedResponse> {
    return jsonFetchV2<WorkflowActionAcceptedResponse>(
      buildWorkflowActionPathV3(projectId, nodeId, 'improve-in-execution'),
      { method: 'POST' },
      { idempotencyKey, expectedReviewCommitSha },
    )
  },
}
