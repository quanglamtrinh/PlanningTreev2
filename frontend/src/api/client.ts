import type {
  BootstrapStatus,
  NodeRecord,
  PlanningHistory,
  ProjectSummary,
  SplitMode,
  SplitAcceptedResponse,
  Snapshot,
  WorkspaceSettings,
} from './types'

type JsonBody = Record<string, unknown> | undefined

interface ErrorPayload {
  code?: string
  message?: string
}

const DEFAULT_TIMEOUT_MS = 300_000
const CANONICAL_SPLIT_MODES = new Set<SplitMode>([
  'workflow',
  'simplify_workflow',
  'phase_breakdown',
  'agent_breakdown',
])
const CANONICAL_SPLIT_OUTPUT_FAMILIES = new Set(['flat_subtasks_v1'])

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
  const response = await withRequestTimeout(
    fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
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

function isCanonicalSplitMode(value: unknown): value is SplitMode {
  return typeof value === 'string' && CANONICAL_SPLIT_MODES.has(value as SplitMode)
}

function normalizeSplitMetadata(
  metadata: Record<string, unknown> | null,
): Record<string, unknown> | null {
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
    return null
  }
  const normalized = { ...metadata }
  if (!isCanonicalSplitMode(normalized.mode)) {
    delete normalized.mode
  }
  if (
    typeof normalized.output_family !== 'string' ||
    !CANONICAL_SPLIT_OUTPUT_FAMILIES.has(normalized.output_family)
  ) {
    delete normalized.output_family
  }
  return normalized
}

function normalizeNodeRecord(node: NodeRecord): NodeRecord {
  return {
    ...node,
    planning_mode: isCanonicalSplitMode(node.planning_mode) ? node.planning_mode : null,
    split_metadata: normalizeSplitMetadata(node.split_metadata),
  }
}

function normalizeSnapshot(snapshot: Snapshot): Snapshot {
  return {
    ...snapshot,
    tree_state: {
      ...snapshot.tree_state,
      node_registry: snapshot.tree_state.node_registry.map((node) => normalizeNodeRecord(node)),
    },
  }
}

export const api = {
  getBootstrapStatus(): Promise<BootstrapStatus> {
    return jsonFetch('/v1/bootstrap/status')
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
    }).then(normalizeSnapshot)
  },
  deleteProject(projectId: string): Promise<void> {
    return jsonFetch<void>(`/v1/projects/${projectId}`, { method: 'DELETE' })
  },
  getSnapshot(projectId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/snapshot`).then(normalizeSnapshot)
  },
  resetProjectToRoot(projectId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/reset-to-root`, { method: 'POST' }).then(
      normalizeSnapshot,
    )
  },
  setActiveNode(projectId: string, activeNodeId: string | null): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/active-node`, { method: 'PATCH' }, {
      active_node_id: activeNodeId,
    }).then(normalizeSnapshot)
  },
  createChild(projectId: string, parentId: string): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/nodes`, { method: 'POST' }, {
      parent_id: parentId,
    }).then(normalizeSnapshot)
  },
  splitNode(
    projectId: string,
    nodeId: string,
    mode: SplitMode,
    confirmReplace = false,
  ): Promise<SplitAcceptedResponse> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/split`, { method: 'POST' }, {
      mode,
      confirm_replace: confirmReplace,
    })
  },
  getPlanningHistory(projectId: string, nodeId: string): Promise<PlanningHistory> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/planning/history`)
  },
  planningEventsUrl(projectId: string, nodeId: string): string {
    return `/v1/projects/${projectId}/nodes/${nodeId}/planning/events`
  },
  updateNode(
    projectId: string,
    nodeId: string,
    payload: { title?: string; description?: string },
  ): Promise<Snapshot> {
    return jsonFetch<Snapshot>(`/v1/projects/${projectId}/nodes/${nodeId}`, { method: 'PATCH' }, payload).then(
      normalizeSnapshot,
    )
  },
}
