import type {
  AcceptedAgentOperation,
  AskConversationResponse,
  AskConversationSendAcceptedResponse,
  PlanningConversationResponse,
  AskSession,
  BootstrapStatus,
  ChatSession,
  DeltaContextPacket,
  ExecutionConversationResponse,
  ExecutionConversationSendAcceptedResponse,
  NodeBrief,
  NodeBriefing,
  NodeDocuments,
  NodeState,
  NodeSpec,
  NodeTask,
  PlanningHistory,
  ProjectSummary,
  RuntimeInputAnswer,
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
    return jsonFetch('/v1/projects', { method: 'POST' }, {
      name,
      root_goal: rootGoal,
    })
  },
  getSnapshot(projectId: string): Promise<Snapshot> {
    return jsonFetch(`/v1/projects/${projectId}/snapshot`)
  },
  resetProjectToRoot(projectId: string): Promise<Snapshot> {
    return jsonFetch(`/v1/projects/${projectId}/reset-to-root`, { method: 'POST' })
  },
  setActiveNode(projectId: string, activeNodeId: string | null): Promise<Snapshot> {
    return jsonFetch(`/v1/projects/${projectId}/active-node`, { method: 'PATCH' }, {
      active_node_id: activeNodeId,
    })
  },
  createChild(projectId: string, parentId: string): Promise<Snapshot> {
    return jsonFetch(`/v1/projects/${projectId}/nodes`, { method: 'POST' }, {
      parent_id: parentId,
    })
  },
  splitNode(
    projectId: string,
    nodeId: string,
    mode: 'walking_skeleton' | 'slice',
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
  agentEventsUrl(projectId: string, nodeId: string): string {
    return `/v1/projects/${projectId}/nodes/${nodeId}/agent/events`
  },
  updateNode(
    projectId: string,
    nodeId: string,
    payload: { title?: string; description?: string },
  ): Promise<Snapshot> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}`, { method: 'PATCH' }, payload)
  },
  getNodeDocuments(projectId: string, nodeId: string): Promise<NodeDocuments> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/documents`)
  },
  getNodeTask(projectId: string, nodeId: string): Promise<{ task: NodeTask }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/documents/task`)
  },
  updateNodeTask(
    projectId: string,
    nodeId: string,
    payload: Partial<NodeTask>,
  ): Promise<{ task: NodeTask }> {
    return jsonFetch(
      `/v1/projects/${projectId}/nodes/${nodeId}/documents/task`,
      { method: 'PUT' },
      payload,
    )
  },
  getNodeBrief(projectId: string, nodeId: string): Promise<{ brief: NodeBrief }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/documents/brief`)
  },
  getNodeBriefing(projectId: string, nodeId: string): Promise<{ briefing: NodeBriefing }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/documents/briefing`)
  },
  getNodeSpec(projectId: string, nodeId: string): Promise<{ spec: NodeSpec }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/documents/spec`)
  },
  updateNodeSpec(
    projectId: string,
    nodeId: string,
    payload: Partial<NodeSpec>,
  ): Promise<{ spec: NodeSpec }> {
    return jsonFetch(
      `/v1/projects/${projectId}/nodes/${nodeId}/documents/spec`,
      { method: 'PUT' },
      payload,
    )
  },
  getNodeState(projectId: string, nodeId: string): Promise<{ state: NodeState }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/documents/state`)
  },
  confirmTask(projectId: string, nodeId: string): Promise<AcceptedAgentOperation> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/confirm-task`, {
      method: 'POST',
    })
  },
  confirmBriefing(projectId: string, nodeId: string): Promise<{ state: NodeState }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/confirm-briefing`, {
      method: 'POST',
    })
  },
  confirmSpec(projectId: string, nodeId: string): Promise<{ state: NodeState }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/confirm-spec`, {
      method: 'POST',
    })
  },
  generateNodeSpec(projectId: string, nodeId: string): Promise<AcceptedAgentOperation> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/generate-spec`, {
      method: 'POST',
    })
  },
  startPlan(projectId: string, nodeId: string): Promise<AcceptedAgentOperation> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/plan/start`, {
      method: 'POST',
    })
  },
  sendPlanMessage(
    projectId: string,
    nodeId: string,
    content: string,
  ): Promise<AcceptedAgentOperation> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/plan/messages`, {
      method: 'POST',
    }, {
      content,
    })
  },
  resolvePlanInput(
    projectId: string,
    nodeId: string,
    requestId: string,
    payload: {
      thread_id?: string | null
      turn_id?: string | null
      answers: Record<string, RuntimeInputAnswer>
    },
  ): Promise<{ status: 'resolved' | 'already_resolved_or_stale'; session: ChatSession }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/plan/input/${requestId}/resolve`, {
      method: 'POST',
    }, payload)
  },
  executeNode(projectId: string, nodeId: string): Promise<{ status: string; session: ChatSession; state: NodeState }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/execute`, {
      method: 'POST',
    })
  },
  completeNode(projectId: string, nodeId: string): Promise<Snapshot> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/complete`, {
      method: 'POST',
    })
  },
  planAndExecute(projectId: string, nodeId: string): Promise<{ status: string; session: ChatSession; state: NodeState }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/plan-and-execute`, {
      method: 'POST',
    })
  },
  startExecution(projectId: string, nodeId: string): Promise<{ status: string; session: ChatSession; state: NodeState }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/start-execution`, {
      method: 'POST',
    })
  },
  getChatSession(projectId: string, nodeId: string): Promise<{ session: ChatSession }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/chat/session`)
  },
  sendChatMessage(
    projectId: string,
    nodeId: string,
    content: string,
  ): Promise<{ status: string; user_message_id: string; assistant_message_id: string }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/chat/messages`, {
      method: 'POST',
    }, {
      content,
    })
  },
  resetChatSession(projectId: string, nodeId: string): Promise<{ session: ChatSession }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/chat/reset`, {
      method: 'POST',
    })
  },
  chatEventsUrl(projectId: string, nodeId: string): string {
    return `/v1/projects/${projectId}/nodes/${nodeId}/chat/events`
  },
  getAskSession(projectId: string, nodeId: string): Promise<{ session: AskSession }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/ask/session`)
  },
  sendAskMessage(
    projectId: string,
    nodeId: string,
    content: string,
  ): Promise<{ status: string; user_message_id: string; assistant_message_id: string }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/ask/messages`, {
      method: 'POST',
    }, {
      content,
    })
  },
  resetAskSession(projectId: string, nodeId: string): Promise<{ session: AskSession }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/ask/reset`, {
      method: 'POST',
    })
  },
  askEventsUrl(projectId: string, nodeId: string): string {
    return `/v1/projects/${projectId}/nodes/${nodeId}/ask/events`
  },
  getAskConversation(
    projectId: string,
    nodeId: string,
  ): Promise<AskConversationResponse> {
    return jsonFetch(`/v2/projects/${projectId}/nodes/${nodeId}/conversations/ask`)
  },
  getPlanningConversation(
    projectId: string,
    nodeId: string,
  ): Promise<PlanningConversationResponse> {
    return jsonFetch(`/v2/projects/${projectId}/nodes/${nodeId}/conversations/planning`)
  },
  sendAskConversationMessage(
    projectId: string,
    nodeId: string,
    content: string,
  ): Promise<AskConversationSendAcceptedResponse> {
    return jsonFetch(
      `/v2/projects/${projectId}/nodes/${nodeId}/conversations/ask/send`,
      { method: 'POST' },
      { content },
    )
  },
  askConversationEventsUrl(
    projectId: string,
    nodeId: string,
    options: {
      afterEventSeq: number
      expectedStreamId?: string | null
    },
  ): string {
    const search = new URLSearchParams()
    search.set('after_event_seq', String(options.afterEventSeq))
    if (options.expectedStreamId) {
      search.set('expected_stream_id', options.expectedStreamId)
    }
    return `/v2/projects/${projectId}/nodes/${nodeId}/conversations/ask/events?${search.toString()}`
  },
  planningConversationEventsUrl(
    projectId: string,
    nodeId: string,
    options: {
      afterEventSeq: number
      expectedStreamId?: string | null
    },
  ): string {
    const search = new URLSearchParams()
    search.set('after_event_seq', String(options.afterEventSeq))
    if (options.expectedStreamId) {
      search.set('expected_stream_id', options.expectedStreamId)
    }
    return `/v2/projects/${projectId}/nodes/${nodeId}/conversations/planning/events?${search.toString()}`
  },
  getExecutionConversation(
    projectId: string,
    nodeId: string,
  ): Promise<ExecutionConversationResponse> {
    return jsonFetch(`/v2/projects/${projectId}/nodes/${nodeId}/conversations/execution`)
  },
  sendExecutionConversationMessage(
    projectId: string,
    nodeId: string,
    content: string,
  ): Promise<ExecutionConversationSendAcceptedResponse> {
    return jsonFetch(
      `/v2/projects/${projectId}/nodes/${nodeId}/conversations/execution/send`,
      { method: 'POST' },
      { content },
    )
  },
  executionConversationEventsUrl(
    projectId: string,
    nodeId: string,
    options: {
      afterEventSeq: number
      expectedStreamId?: string | null
    },
  ): string {
    const search = new URLSearchParams()
    search.set('after_event_seq', String(options.afterEventSeq))
    if (options.expectedStreamId) {
      search.set('expected_stream_id', options.expectedStreamId)
    }
    return `/v2/projects/${projectId}/nodes/${nodeId}/conversations/execution/events?${search.toString()}`
  },
  listAskPackets(projectId: string, nodeId: string): Promise<{ packets: DeltaContextPacket[] }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/ask/packets`)
  },
  approveAskPacket(projectId: string, nodeId: string, packetId: string): Promise<{ packet: DeltaContextPacket }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/ask/packets/${packetId}/approve`, {
      method: 'POST',
    })
  },
  rejectAskPacket(projectId: string, nodeId: string, packetId: string): Promise<{ packet: DeltaContextPacket }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/ask/packets/${packetId}/reject`, {
      method: 'POST',
    })
  },
  mergeAskPacket(projectId: string, nodeId: string, packetId: string): Promise<{ packet: DeltaContextPacket }> {
    return jsonFetch(`/v1/projects/${projectId}/nodes/${nodeId}/ask/packets/${packetId}/merge`, {
      method: 'POST',
    })
  },
}
