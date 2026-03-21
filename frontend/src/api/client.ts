import type {
  BootstrapStatus,
  ChatSession,
  CodexSnapshot,
  ProjectSummary,
  SendMessageResponse,
  Snapshot,
  SplitAcceptedResponse,
  SplitMode,
  SplitStatusResponse,
  WorkspaceSettings,
} from './types'

type JsonBody = Record<string, unknown> | undefined

interface ErrorPayload {
  code?: string
  message?: string
}

const DEFAULT_TIMEOUT_MS = 300_000

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

export const api = {
  getBootstrapStatus(): Promise<BootstrapStatus> {
    return jsonFetch('/v1/bootstrap/status')
  },
  getCodexSnapshot(): Promise<CodexSnapshot> {
    return jsonFetch('/v1/codex/account')
  },
  getWorkspaceSettings(): Promise<WorkspaceSettings> {
    return jsonFetch('/v1/settings/workspace')
  },
  setWorkspaceRoot(baseWorkspaceRoot: string): Promise<WorkspaceSettings> {
    return jsonFetch('/v1/settings/workspace', { method: 'PATCH' }, {
      base_workspace_root: baseWorkspaceRoot,
    })
  },
  listProjects(): Promise<ProjectSummary[]> {
    return jsonFetch('/v1/projects')
  },
  createProject(name: string, rootGoal: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>('/v1/projects', { method: 'POST' }, {
      name,
      root_goal: rootGoal,
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
  getChatSession(projectId: string, nodeId: string): Promise<ChatSession> {
    return jsonFetch<ChatSession>(`/v1/projects/${projectId}/nodes/${nodeId}/chat/session`)
  },
  sendChatMessage(projectId: string, nodeId: string, content: string): Promise<SendMessageResponse> {
    return jsonFetch<SendMessageResponse>(
      `/v1/projects/${projectId}/nodes/${nodeId}/chat/message`,
      { method: 'POST' },
      { content },
    )
  },
  resetChatSession(projectId: string, nodeId: string): Promise<ChatSession> {
    return jsonFetch<ChatSession>(
      `/v1/projects/${projectId}/nodes/${nodeId}/chat/reset`,
      { method: 'POST' },
    )
  },
}
