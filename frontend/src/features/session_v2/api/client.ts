import type {
  PendingServerRequest,
  RejectRequestV4,
  ResolveRequestV4,
  ServerRequestEnvelope,
  SessionEventEnvelope,
  SessionThread,
  SessionTurn,
  TurnInterruptRequestV4,
  TurnStartRequestV4,
  TurnSteerRequestV4,
} from '../contracts'
import { appendAuthToken, initAuthToken } from '../../../api/client'

type ErrorPayload = {
  code?: string
  message?: string
}

type SuccessEnvelope<T> = {
  ok: true
  data: T
}

type FailureEnvelope = {
  ok: false
  error?: ErrorPayload
}

type InitializeResponse = {
  connection: {
    phase: string
    clientName?: string
    serverVersion?: string
  }
}

type ThreadConfigResponse = {
  thread: SessionThread
  model?: string | null
  modelProvider?: string | null
  cwd?: string | null
  approvalPolicy?: string | Record<string, unknown>
  sandbox?: string | Record<string, unknown>
  reasoningEffort?: string | null
  serviceTier?: string | null
}

type ThreadListResponse = {
  data: SessionThread[]
  nextCursor: string | null
}

export type SessionModelEntryV2 = {
  id?: string
  model?: string
  displayName?: string
  description?: string
  hidden?: boolean
  isDefault?: boolean
}

type ModelListResponse = {
  data: SessionModelEntryV2[]
  nextCursor: string | null
}

type TurnListResponse = {
  data: SessionTurn[]
  nextCursor: string | null
}

type LoadedThreadIdsResponse = {
  data: string[]
  nextCursor: string | null
}

type UnsubscribeResponse = {
  status: 'notLoaded' | 'notSubscribed' | 'unsubscribed'
}

type TurnEnvelopeResponse = {
  turn: SessionTurn
}

type BasicOkResponse = {
  status?: string
}

type PendingRequestsResponse = {
  data: PendingServerRequest[]
}

export class SessionV2ApiError extends Error {
  status: number
  code: string | null

  constructor(status: number, payload: ErrorPayload | null) {
    super(payload?.message ?? `Session V2 request failed with status ${status}`)
    this.name = 'SessionV2ApiError'
    this.status = status
    this.code = payload?.code ?? null
  }
}

function toQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const entries = Object.entries(params).filter(([, value]) => value !== null && value !== undefined)
  if (entries.length === 0) {
    return ''
  }
  const query = entries
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&')
  return `?${query}`
}

async function getElectronAuthHeaders(): Promise<Record<string, string>> {
  if (!window.electronAPI) {
    return {}
  }
  const token = await window.electronAPI.getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function jsonFetch<T>(path: string, init?: RequestInit, body?: unknown): Promise<T> {
  const authHeaders = await getElectronAuthHeaders()
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
      ...(init?.headers ?? {}),
    },
    body: body === undefined ? init?.body : JSON.stringify(body),
  })

  let payload: SuccessEnvelope<T> | FailureEnvelope | null = null
  if (response.status !== 204) {
    try {
      payload = (await response.json()) as SuccessEnvelope<T> | FailureEnvelope
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    const errorPayload = payload && 'ok' in payload && payload.ok === false ? payload.error ?? null : null
    throw new SessionV2ApiError(response.status, errorPayload)
  }

  if (!payload || payload.ok !== true) {
    throw new SessionV2ApiError(response.status, {
      code: 'ERR_INTERNAL',
      message: 'Session V2 success envelope is invalid.',
    })
  }
  return payload.data
}

export async function initializeSessionV2(): Promise<InitializeResponse> {
  await initAuthToken()
  return jsonFetch<InitializeResponse>('/v4/session/initialize', { method: 'POST' }, {
    clientInfo: { name: 'PlanningTree Session V2', version: '1.0.0' },
    capabilities: {
      experimentalApi: true,
      optOutNotificationMethods: [],
    },
  })
}

export async function readSessionStatusV2(): Promise<InitializeResponse> {
  await initAuthToken()
  return jsonFetch<InitializeResponse>('/v4/session/status')
}

export async function startThreadV2(payload?: Record<string, unknown>): Promise<ThreadConfigResponse> {
  await initAuthToken()
  return jsonFetch<ThreadConfigResponse>('/v4/session/threads/start', { method: 'POST' }, payload ?? {})
}

export async function resumeThreadV2(
  threadId: string,
  payload?: Record<string, unknown>,
): Promise<ThreadConfigResponse> {
  await initAuthToken()
  return jsonFetch<ThreadConfigResponse>(
    `/v4/session/threads/${encodeURIComponent(threadId)}/resume`,
    { method: 'POST' },
    payload ?? {},
  )
}

export async function forkThreadV2(
  threadId: string,
  payload?: Record<string, unknown>,
): Promise<ThreadConfigResponse> {
  await initAuthToken()
  return jsonFetch<ThreadConfigResponse>(
    `/v4/session/threads/${encodeURIComponent(threadId)}/fork`,
    { method: 'POST' },
    payload ?? {},
  )
}

export async function listThreadsV2(
  payload?: {
    cursor?: string | null
    limit?: number | null
    archived?: boolean | null
    cwd?: string | null
    searchTerm?: string | null
  },
): Promise<ThreadListResponse> {
  await initAuthToken()
  const query = toQuery({
    cursor: payload?.cursor ?? null,
    limit: payload?.limit ?? null,
    archived: payload?.archived ?? null,
    cwd: payload?.cwd ?? null,
    searchTerm: payload?.searchTerm ?? null,
  })
  return jsonFetch<ThreadListResponse>(`/v4/session/threads/list${query}`)
}

export async function listModelsV2(
  payload?: {
    cursor?: string | null
    limit?: number | null
    includeHidden?: boolean | null
  },
): Promise<ModelListResponse> {
  await initAuthToken()
  const query = toQuery({
    cursor: payload?.cursor ?? null,
    limit: payload?.limit ?? null,
    includeHidden: payload?.includeHidden ?? null,
  })
  return jsonFetch<ModelListResponse>(`/v4/session/models/list${query}`)
}

export async function readThreadV2(threadId: string, includeTurns = false): Promise<{ thread: SessionThread }> {
  await initAuthToken()
  const query = toQuery({ includeTurns })
  return jsonFetch<{ thread: SessionThread }>(
    `/v4/session/threads/${encodeURIComponent(threadId)}/read${query}`,
  )
}

export async function listThreadTurnsV2(
  threadId: string,
  payload?: { cursor?: string | null; limit?: number | null },
): Promise<TurnListResponse> {
  await initAuthToken()
  const query = toQuery({
    cursor: payload?.cursor ?? null,
    limit: payload?.limit ?? null,
  })
  return jsonFetch<TurnListResponse>(`/v4/session/threads/${encodeURIComponent(threadId)}/turns${query}`)
}

export async function listLoadedThreadsV2(payload?: {
  cursor?: string | null
  limit?: number | null
}): Promise<LoadedThreadIdsResponse> {
  await initAuthToken()
  const query = toQuery({
    cursor: payload?.cursor ?? null,
    limit: payload?.limit ?? null,
  })
  return jsonFetch<LoadedThreadIdsResponse>(`/v4/session/threads/loaded/list${query}`)
}

export async function unsubscribeThreadV2(threadId: string): Promise<UnsubscribeResponse> {
  await initAuthToken()
  return jsonFetch<UnsubscribeResponse>(
    `/v4/session/threads/${encodeURIComponent(threadId)}/unsubscribe`,
    { method: 'POST' },
  )
}

export async function startTurnV2(threadId: string, payload: TurnStartRequestV4): Promise<TurnEnvelopeResponse> {
  await initAuthToken()
  return jsonFetch<TurnEnvelopeResponse>(
    `/v4/session/threads/${encodeURIComponent(threadId)}/turns/start`,
    { method: 'POST' },
    payload,
  )
}

export async function steerTurnV2(
  threadId: string,
  turnId: string,
  payload: TurnSteerRequestV4,
): Promise<TurnEnvelopeResponse> {
  await initAuthToken()
  return jsonFetch<TurnEnvelopeResponse>(
    `/v4/session/threads/${encodeURIComponent(threadId)}/turns/${encodeURIComponent(turnId)}/steer`,
    { method: 'POST' },
    payload,
  )
}

export async function interruptTurnV2(
  threadId: string,
  turnId: string,
  payload: TurnInterruptRequestV4,
): Promise<BasicOkResponse> {
  await initAuthToken()
  return jsonFetch<BasicOkResponse>(
    `/v4/session/threads/${encodeURIComponent(threadId)}/turns/${encodeURIComponent(turnId)}/interrupt`,
    { method: 'POST' },
    payload,
  )
}

export async function listPendingRequestsV2(): Promise<PendingRequestsResponse> {
  await initAuthToken()
  return jsonFetch<PendingRequestsResponse>('/v4/session/requests/pending')
}

export async function resolvePendingRequestV2(requestId: string, payload: ResolveRequestV4): Promise<BasicOkResponse> {
  await initAuthToken()
  return jsonFetch<BasicOkResponse>(
    `/v4/session/requests/${encodeURIComponent(requestId)}/resolve`,
    { method: 'POST' },
    payload,
  )
}

export async function rejectPendingRequestV2(requestId: string, payload: RejectRequestV4): Promise<BasicOkResponse> {
  await initAuthToken()
  return jsonFetch<BasicOkResponse>(
    `/v4/session/requests/${encodeURIComponent(requestId)}/reject`,
    { method: 'POST' },
    payload,
  )
}

export function openThreadEventsStreamV2(
  threadId: string,
  options?: {
    cursorEventId?: string | null
  },
): EventSource {
  const query = toQuery({
    cursor: options?.cursorEventId ?? null,
  })
  const url = appendAuthToken(`/v4/session/threads/${encodeURIComponent(threadId)}/events${query}`)
  return new EventSource(url)
}

export function parseSessionEventEnvelope(raw: string): SessionEventEnvelope {
  return JSON.parse(raw) as SessionEventEnvelope
}

export function parseServerRequestEnvelope(raw: string): ServerRequestEnvelope {
  return JSON.parse(raw) as ServerRequestEnvelope
}
