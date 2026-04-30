import type {
  AcceptLocalReviewResponse,
  AcceptRollupReviewResponse,
  BootstrapStatus,
  ClarifyGenAcceptedResponse,
  ClarifyGenStatusResponse,
  ClarifyState,
  DetailState,
  FrameGenAcceptedResponse,
  FrameGenStatusResponse,
  LocalUsageSnapshot,
  McpEffectiveConfigResponse,
  McpRegistryResponse,
  McpRegistryServer,
  McpThreadProfile,
  McpThreadRole,
  NodeDocument,
  NodeDocumentKind,
  ProjectSummary,
  ReviewState,
  Snapshot,
  SpecGenAcceptedResponse,
  SpecGenStatusResponse,
  SplitAcceptedResponse,
  SplitMode,
  SplitStatusResponse,
  WorkspaceTextFile,
} from './types'

type JsonBody = Record<string, unknown> | undefined
type WorkspaceTextFileScope = 'workspace' | 'root_node' | 'node'
type WorkspaceTextFileOptions = { scope?: WorkspaceTextFileScope; nodeId?: string | null }

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

  ensureRootThread(
    projectId: string,
    nodeId: string,
    payload?: { model?: string | null; modelProvider?: string | null },
  ): Promise<{ threadId: string; role: 'root' }> {
    return jsonFetchV2<{ threadId: string; role: 'root' }>(
      `/v4/projects/${encodeURIComponent(projectId)}/nodes/${encodeURIComponent(nodeId)}/root-thread/ensure`,
      { method: 'POST' },
      {
        model: payload?.model ?? null,
        modelProvider: payload?.modelProvider ?? null,
      },
    )
  },

  listMcpRegistry(): Promise<McpRegistryResponse> {
    return jsonFetchV2<McpRegistryResponse>('/v4/extensions/mcp/registry')
  },
  upsertMcpRegistryServer(server: Partial<McpRegistryServer> & { serverId: string }): Promise<{ server: McpRegistryServer }> {
    return jsonFetchV2<{ server: McpRegistryServer }>(
      `/v4/extensions/mcp/registry/servers/${encodeURIComponent(server.serverId)}`,
      { method: 'PUT' },
      server as Record<string, unknown>,
    )
  },
  deleteMcpRegistryServer(serverId: string): Promise<{ deleted: boolean; serverId: string }> {
    return jsonFetchV2<{ deleted: boolean; serverId: string }>(
      `/v4/extensions/mcp/registry/servers/${encodeURIComponent(serverId)}`,
      { method: 'DELETE' },
    )
  },
  readMcpThreadProfile(projectId: string, nodeId: string, role: McpThreadRole): Promise<{ profile: McpThreadProfile }> {
    return jsonFetchV2<{ profile: McpThreadProfile }>(
      `/v4/projects/${encodeURIComponent(projectId)}/nodes/${encodeURIComponent(nodeId)}/threads/${encodeURIComponent(role)}/mcp-profile`,
    )
  },
  updateMcpThreadProfile(
    projectId: string,
    nodeId: string,
    role: McpThreadRole,
    patch: Partial<McpThreadProfile>,
  ): Promise<{ profile: McpThreadProfile }> {
    return jsonFetchV2<{ profile: McpThreadProfile }>(
      `/v4/projects/${encodeURIComponent(projectId)}/nodes/${encodeURIComponent(nodeId)}/threads/${encodeURIComponent(role)}/mcp-profile`,
      { method: 'PATCH' },
      patch as Record<string, unknown>,
    )
  },
  resetMcpThreadProfile(projectId: string, nodeId: string, role: McpThreadRole): Promise<{ profile: McpThreadProfile }> {
    return jsonFetchV2<{ profile: McpThreadProfile }>(
      `/v4/projects/${encodeURIComponent(projectId)}/nodes/${encodeURIComponent(nodeId)}/threads/${encodeURIComponent(role)}/mcp-profile/reset`,
      { method: 'POST' },
    )
  },
  previewMcpEffectiveConfig(
    projectId: string,
    nodeId: string,
    role: McpThreadRole,
    threadId?: string | null,
  ): Promise<McpEffectiveConfigResponse> {
    const query = threadId ? `?threadId=${encodeURIComponent(threadId)}` : ''
    return jsonFetchV2<McpEffectiveConfigResponse>(
      `/v4/projects/${encodeURIComponent(projectId)}/nodes/${encodeURIComponent(nodeId)}/threads/${encodeURIComponent(role)}/mcp-effective-config${query}`,
    )
  },
  getBootstrapStatus(): Promise<BootstrapStatus> {
    return jsonFetch('/v4/bootstrap/status')
  },
  getLocalUsageSnapshot(days?: number): Promise<LocalUsageSnapshot> {
    const query = days == null ? '' : `?days=${encodeURIComponent(String(days))}`
    return jsonFetch<LocalUsageSnapshot>(`/v4/usage/local${query}`)
  },
  listProjects(): Promise<ProjectSummary[]> {
    return jsonFetch('/v4/projects')
  },
  attachProjectFolder(folderPath: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>('/v4/projects/attach', { method: 'POST' }, {
      folder_path: folderPath,
    })
  },
  deleteProject(projectId: string): Promise<void> {
    return jsonFetch<void>(`/v4/projects/${projectId}`, { method: 'DELETE' })
  },
  getSnapshot(projectId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v4/projects/${projectId}/snapshot`)
  },
  resetProjectToRoot(projectId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v4/projects/${projectId}/reset-to-root`, { method: 'POST' })
  },
  setActiveNode(projectId: string, activeNodeId: string | null): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v4/projects/${projectId}/active-node`, { method: 'PATCH' }, {
      active_node_id: activeNodeId,
    })
  },
  createChild(projectId: string, parentId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v4/projects/${projectId}/nodes`, { method: 'POST' }, {
      parent_id: parentId,
    })
  },
  createTask(projectId: string, parentId: string, description: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v4/projects/${projectId}/nodes/create-task`, { method: 'POST' }, {
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
    return jsonFetch<Snapshot>(`/v4/projects/${projectId}/nodes/${nodeId}`, { method: 'PATCH' }, payload)
  },
  getNodeDocument(
    projectId: string,
    nodeId: string,
    kind: NodeDocumentKind,
  ): Promise<NodeDocument> {
    return jsonFetch<NodeDocument>(`/v4/projects/${projectId}/nodes/${nodeId}/documents/${kind}`)
  },
  putNodeDocument(
    projectId: string,
    nodeId: string,
    kind: NodeDocumentKind,
    content: string,
  ): Promise<NodeDocument> {
    return jsonFetch<NodeDocument>(
      `/v4/projects/${projectId}/nodes/${nodeId}/documents/${kind}`,
      { method: 'PUT' },
      { content },
    )
  },
  getWorkspaceTextFile(
    projectId: string,
    relativePath: string,
    options?: WorkspaceTextFileOptions,
  ): Promise<WorkspaceTextFile> {
    const q = new URLSearchParams({ relative_path: relativePath })
    if (options?.scope) {
      q.set('scope', options.scope)
    }
    if (options?.nodeId) {
      q.set('node_id', options.nodeId)
    }
    return jsonFetch<WorkspaceTextFile>(`/v4/projects/${projectId}/workspace-text-file?${q}`)
  },
  putWorkspaceTextFile(
    projectId: string,
    relativePath: string,
    content: string,
    options?: WorkspaceTextFileOptions,
  ): Promise<WorkspaceTextFile> {
    const q = new URLSearchParams({ relative_path: relativePath })
    if (options?.scope) {
      q.set('scope', options.scope)
    }
    if (options?.nodeId) {
      q.set('node_id', options.nodeId)
    }
    return jsonFetch<WorkspaceTextFile>(
      `/v4/projects/${projectId}/workspace-text-file?${q}`,
      { method: 'PUT' },
      { content },
    )
  },
  getDetailState(projectId: string, nodeId: string): Promise<DetailState> {
    return jsonFetch<DetailState>(`/v4/projects/${projectId}/nodes/${nodeId}/detail-state`)
  },
  getReviewState(projectId: string, nodeId: string): Promise<ReviewState> {
    return jsonFetch<ReviewState>(`/v4/projects/${projectId}/nodes/${nodeId}/review-state`)
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
  finishTask(projectId: string, nodeId: string): Promise<DetailState> {
    return jsonFetch<DetailState>(`/v4/projects/${projectId}/nodes/${nodeId}/finish-task`, {
      method: 'POST',
    })
  },
  acceptLocalReview(
    projectId: string,
    nodeId: string,
    summary: string,
  ): Promise<AcceptLocalReviewResponse> {
    return jsonFetch<AcceptLocalReviewResponse>(
      `/v4/projects/${projectId}/nodes/${nodeId}/accept-local-review`,
      { method: 'POST' },
      { summary },
    )
  },
  acceptRollupReview(
    projectId: string,
    reviewNodeId: string,
  ): Promise<AcceptRollupReviewResponse> {
    return jsonFetch<AcceptRollupReviewResponse>(
      `/v4/projects/${projectId}/nodes/${reviewNodeId}/accept-rollup-review`,
      { method: 'POST' },
    )
  },
  initGit(projectId: string): Promise<{ status: string; head_sha: string; message: string }> {
    return jsonFetch(`/v4/projects/${projectId}/git/init`, { method: 'POST' })
  },
  resetWorkspace(
    projectId: string,
    nodeId: string,
    target: 'initial' | 'head',
  ): Promise<{ status: string; target_sha: string; current_head_sha: string; task_present_in_current_workspace: boolean; detail_state: DetailState }> {
    return jsonFetch(`/v4/projects/${projectId}/nodes/${nodeId}/reset-workspace`, { method: 'POST' }, { target })
  }
}
