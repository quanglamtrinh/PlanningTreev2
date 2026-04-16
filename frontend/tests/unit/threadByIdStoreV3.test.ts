import { act, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getThreadSnapshotByIdV3: vi.fn(),
    getThreadHistoryPageByIdV3: vi.fn(),
    startThreadTurnByIdV3: vi.fn(),
    resolveThreadUserInputByIdV3: vi.fn(),
    planActionByIdV3: vi.fn(),
    probeThreadByIdEventsCursorV3: vi.fn().mockResolvedValue('ok'),
    reportAskRolloutMetricEvent: vi.fn().mockResolvedValue({ ok: true }),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
  appendAuthToken: (url: string) => url,
  buildThreadByIdEventsUrlV3: (
    projectId: string,
    nodeId: string,
    threadId: string,
    afterSnapshotVersion?: number | null,
    lastEventId?: string | null,
  ) =>
    `/v3/projects/${projectId}/threads/by-id/${threadId}/events?node_id=${nodeId}${
      afterSnapshotVersion == null ? '' : `&after_snapshot_version=${afterSnapshotVersion}`
    }${lastEventId == null || lastEventId === '' ? '' : `&last_event_id=${lastEventId}`}`,
}))

import type { ThreadSnapshotV3 } from '../../src/api/types'
import {
  selectAskFollowupQueueActions,
  decideReloadPolicy,
  resolvePhase12CapPolicy,
  resolvePhase12CapProfile,
  selectAskFollowupQueueState,
  selectComposerState,
  selectCore,
  selectFeedRenderState,
  selectThreadActions,
  selectTransportBannerState,
  selectTransport,
  selectUiControl,
  selectWorkflowActionState,
  useThreadByIdStoreV3,
} from '../../src/features/conversation/state/threadByIdStoreV3'

type EventSourceMockInstance = {
  url: string
  readyState: number
  emitOpen: () => void
  emitMessage: (data: string) => void
}

type EventSourceMockClass = {
  instances: EventSourceMockInstance[]
}

function getEventSourceMock(): EventSourceMockClass {
  return globalThis.EventSource as unknown as EventSourceMockClass
}

function makeSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
  const snapshot: ThreadSnapshotV3 = {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadId: 'thread-1',
    threadRole: 'execution',
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:00Z',
    items: [],
    uiSignals: {
      planReady: {
        planItemId: null,
        revision: null,
        ready: false,
        failed: false,
      },
      activeUserInputRequests: [],
    },
    ...overrides,
  }
  return snapshot
}

function makeMessageUpsertEnvelope(eventId: string, sequence: number, text: string) {
  return {
    schema_version: 1,
    event_id: eventId,
    event_type: 'conversation.item.upsert.v3',
    thread_id: 'thread-1',
    turn_id: `turn-${sequence}`,
    snapshot_version: sequence,
    occurred_at_ms: Date.parse(`2026-04-01T00:0${sequence}:00Z`),
    eventId,
    channel: 'thread',
    projectId: 'project-1',
    nodeId: 'node-1',
    threadRole: 'execution',
    occurredAt: `2026-04-01T00:0${sequence}:00Z`,
    snapshotVersion: sequence,
    type: 'conversation.item.upsert.v3',
    payload: {
      item: {
        id: 'msg-1',
        kind: 'message',
        threadId: 'thread-1',
        turnId: `turn-${sequence}`,
        sequence,
        createdAt: `2026-04-01T00:0${sequence}:00Z`,
        updatedAt: `2026-04-01T00:0${sequence}:00Z`,
        status: 'in_progress',
        source: 'upstream',
        tone: 'neutral',
        metadata: {},
        role: 'assistant',
        text,
        format: 'markdown',
      },
    },
  }
}

function makeMessagePatchEnvelope(eventId: string, sequence: number, textAppend: string) {
  return {
    schema_version: 1,
    event_id: eventId,
    event_type: 'conversation.item.patch.v3',
    thread_id: 'thread-1',
    turn_id: `turn-${sequence}`,
    snapshot_version: sequence,
    occurred_at_ms: Date.parse(`2026-04-01T00:0${sequence}:01Z`),
    eventId,
    channel: 'thread',
    projectId: 'project-1',
    nodeId: 'node-1',
    threadRole: 'execution',
    occurredAt: `2026-04-01T00:0${sequence}:01Z`,
    snapshotVersion: sequence,
    type: 'conversation.item.patch.v3',
    payload: {
      itemId: 'msg-1',
      patch: {
        kind: 'message',
        textAppend,
        updatedAt: `2026-04-01T00:0${sequence}:01Z`,
      },
    },
  }
}

function makePendingUserInputSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
  return makeSnapshot({
    snapshotVersion: 5,
    processingState: 'waiting_user_input',
    items: [
      {
        id: 'input-1',
        kind: 'userInput',
        threadId: 'thread-1',
        turnId: 'turn-1',
        sequence: 3,
        createdAt: '2026-04-01T00:00:10Z',
        updatedAt: '2026-04-01T00:00:10Z',
        status: 'requested',
        source: 'upstream',
        tone: 'info',
        metadata: {},
        requestId: 'req-1',
        title: 'Need answer',
        questions: [],
        answers: [],
        requestedAt: '2026-04-01T00:00:10Z',
        resolvedAt: null,
      },
    ],
    uiSignals: {
      planReady: {
        planItemId: null,
        revision: null,
        ready: false,
        failed: false,
      },
      activeUserInputRequests: [
        {
          requestId: 'req-1',
          itemId: 'input-1',
          threadId: 'thread-1',
          turnId: 'turn-1',
          status: 'requested',
          createdAt: '2026-04-01T00:00:10Z',
          submittedAt: null,
          resolvedAt: null,
          answers: [],
        },
      ],
    },
    ...overrides,
  })
}

function makeAskSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
  return makeSnapshot({
    threadId: 'ask-thread-1',
    threadRole: 'ask_planning',
    ...overrides,
  })
}

function setExecutionQueueRuntimeState(
  overrides: Partial<ReturnType<typeof useThreadByIdStoreV3.getState>> = {},
) {
  useThreadByIdStoreV3.setState({
    activeProjectId: 'project-1',
    activeNodeId: 'node-1',
    activeThreadId: 'thread-1',
    activeThreadRole: 'execution',
    snapshot: makeSnapshot(),
    isLoading: false,
    isSending: false,
    executionFollowupQueue: [],
    executionQueuePauseReason: 'none',
    executionQueueOperatorPaused: false,
    executionQueueWorkflowPhase: 'execution_decision_pending',
    executionQueueCanSendExecutionMessage: true,
    executionQueueLatestExecutionRunId: 'run-1',
    ...overrides,
  })
}

function setAskQueueRuntimeState(
  overrides: Partial<ReturnType<typeof useThreadByIdStoreV3.getState>> = {},
) {
  useThreadByIdStoreV3.setState({
    activeProjectId: 'project-1',
    activeNodeId: 'node-1',
    activeThreadId: 'ask-thread-1',
    activeThreadRole: 'ask_planning',
    snapshot: makeAskSnapshot(),
    isLoading: false,
    isSending: false,
    streamStatus: 'open',
    askFollowupQueue: [],
    askQueuePauseReason: 'none',
    ...overrides,
  })
}

function makeExecutionQueueEntry(overrides: {
  entryId?: string
  text?: string
  idempotencyKey?: string
  createdAtMs?: number
  latestExecutionRunId?: string | null
  planReadyRevision?: number | null
  status?: 'queued' | 'requires_confirmation' | 'sending' | 'failed'
  attemptCount?: number
  lastError?: string | null
} = {}) {
  return {
    entryId: overrides.entryId ?? 'entry-1',
    text: overrides.text ?? 'queued message',
    idempotencyKey: overrides.idempotencyKey ?? 'idem-1',
    createdAtMs: overrides.createdAtMs ?? Date.now(),
    enqueueContext: {
      latestExecutionRunId: overrides.latestExecutionRunId ?? 'run-1',
      planReadyRevision: overrides.planReadyRevision ?? null,
    },
    status: overrides.status ?? ('queued' as const),
    attemptCount: overrides.attemptCount ?? 0,
    lastError: overrides.lastError ?? null,
  }
}

function makeAskQueueEntry(overrides: {
  entryId?: string
  text?: string
  idempotencyKey?: string
  createdAtMs?: number
  threadId?: string | null
  snapshotVersion?: number | null
  staleMarker?: boolean
  status?: 'queued' | 'requires_confirmation' | 'sending' | 'failed'
  confirmationReason?: 'stale_age' | 'thread_drift' | 'snapshot_drift' | 'stale_marker' | null
  attemptCount?: number
  lastError?: string | null
} = {}) {
  return {
    entryId: overrides.entryId ?? 'ask-entry-1',
    text: overrides.text ?? 'queued ask message',
    idempotencyKey: overrides.idempotencyKey ?? 'ask-idem-1',
    createdAtMs: overrides.createdAtMs ?? Date.now(),
    enqueueContext: {
      threadId: overrides.threadId ?? 'ask-thread-1',
      snapshotVersion: overrides.snapshotVersion ?? 1,
      staleMarker: overrides.staleMarker ?? false,
    },
    status: overrides.status ?? ('queued' as const),
    confirmationReason: overrides.confirmationReason ?? null,
    attemptCount: overrides.attemptCount ?? 0,
    lastError: overrides.lastError ?? null,
  }
}

function executionQueueStorageKey(): string {
  return 'ptm:v3:execution-followup-queue:project-1::node-1::thread-1'
}

function askQueueStorageKey(): string {
  return 'ptm:v3:ask-followup-queue:project-1::node-1::ask-thread-1'
}

describe('threadByIdStoreV3', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useThreadByIdStoreV3.getState().disconnectThread()
    globalThis.localStorage.clear()
  })

  it('loads V3 snapshot and subscribes to V3 events stream', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const state = useThreadByIdStoreV3.getState()
    const eventSource = getEventSourceMock().instances[0]

    expect(state.snapshot?.threadId).toBe('thread-1')
    expect(state.snapshot?.threadRole).toBe('execution')
    expect(state.lastSnapshotVersion).toBe(1)
    expect(state.telemetry.firstFrameLatencyMs).not.toBeNull()
    expect(state.telemetry.streamReconnectCount).toBe(0)
    expect(state.telemetry.applyErrorCount).toBe(0)
    expect(state.telemetry.forcedSnapshotReloadCount).toBe(0)
    expect(state.telemetry.lastForcedReloadReason).toBeNull()
    expect(eventSource?.url).toContain(
      '/v3/projects/project-1/threads/by-id/thread-1/events?node_id=node-1&after_snapshot_version=1',
    )
  })

  it('requests capped snapshot window with live_limit=1000 on initial load', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'thread-1',
      1000,
    )
  })

  it('resolves adaptive profile precedence as env override > runtime hint > standard', () => {
    expect(resolvePhase12CapProfile({ envValue: 'LOW', deviceMemory: 16 })).toBe('low')
    expect(resolvePhase12CapProfile({ deviceMemory: 2 })).toBe('low')
    expect(resolvePhase12CapProfile({ deviceMemory: 6 })).toBe('standard')
    expect(resolvePhase12CapProfile({ deviceMemory: 12 })).toBe('high')
    expect(resolvePhase12CapProfile({ deviceMemory: null })).toBe('standard')
  })

  it('computes adaptive cap policy by profile with soft trim target locked at 1000', () => {
    expect(resolvePhase12CapPolicy({ envValue: 'low' })).toEqual({
      profile: 'low',
      softCap: 1000,
      headroom: 100,
      effectiveHardCap: 1100,
      effectiveTrimTarget: 1000,
    })
    expect(resolvePhase12CapPolicy({ envValue: 'standard' })).toEqual({
      profile: 'standard',
      softCap: 1000,
      headroom: 200,
      effectiveHardCap: 1200,
      effectiveTrimTarget: 1000,
    })
    expect(resolvePhase12CapPolicy({ envValue: 'high' })).toEqual({
      profile: 'high',
      softCap: 1000,
      headroom: 400,
      effectiveHardCap: 1400,
      effectiveTrimTarget: 1000,
    })
  })

  it('enforces scrollback trim hysteresis on oversized snapshots', async () => {
    const oversizedItems = Array.from({ length: 1300 }, (_, index) => {
      const sequence = index + 1
      return {
        id: `msg-${sequence}`,
        kind: 'message' as const,
        threadId: 'thread-1',
        turnId: `turn-${sequence}`,
        sequence,
        createdAt: `2026-04-01T00:${String(sequence % 60).padStart(2, '0')}:00Z`,
        updatedAt: `2026-04-01T00:${String(sequence % 60).padStart(2, '0')}:00Z`,
        status: 'completed' as const,
        source: 'upstream' as const,
        tone: 'neutral' as const,
        metadata: {},
        role: 'assistant' as const,
        text: `message-${sequence}`,
        format: 'markdown' as const,
      }
    })
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(
      makeSnapshot({
        snapshotVersion: 10,
        items: oversizedItems,
      }),
    )

    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const state = useThreadByIdStoreV3.getState()
    const sequences = state.snapshot?.items.map((item) => item.sequence) ?? []
    expect(sequences).toHaveLength(1000)
    expect(sequences[0]).toBe(301)
    expect(sequences[sequences.length - 1]).toBe(1300)
    expect(state.hasOlderHistory).toBe(true)
    expect(state.oldestVisibleSequence).toBe(301)
    expect(state.totalItemCount).toBe(1300)
  })

  it('prepends history pages in order and updates pagination metadata', async () => {
    const liveItems = Array.from({ length: 10 }, (_, index) => {
      const sequence = 101 + index
      return {
        id: `msg-${sequence}`,
        kind: 'message' as const,
        threadId: 'thread-1',
        turnId: `turn-${sequence}`,
        sequence,
        createdAt: `2026-04-01T00:${String(index).padStart(2, '0')}:00Z`,
        updatedAt: `2026-04-01T00:${String(index).padStart(2, '0')}:00Z`,
        status: 'completed' as const,
        source: 'upstream' as const,
        tone: 'neutral' as const,
        metadata: {},
        role: 'assistant' as const,
        text: `live-${sequence}`,
        format: 'markdown' as const,
      }
    })
    const olderItems = Array.from({ length: 10 }, (_, index) => {
      const sequence = 91 + index
      return {
        id: `msg-${sequence}`,
        kind: 'message' as const,
        threadId: 'thread-1',
        turnId: `turn-${sequence}`,
        sequence,
        createdAt: `2026-04-01T00:${String(index + 10).padStart(2, '0')}:00Z`,
        updatedAt: `2026-04-01T00:${String(index + 10).padStart(2, '0')}:00Z`,
        status: 'completed' as const,
        source: 'upstream' as const,
        tone: 'neutral' as const,
        metadata: {},
        role: 'assistant' as const,
        text: `older-${sequence}`,
        format: 'markdown' as const,
      }
    })

    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(
      makeSnapshot({
        snapshotVersion: 5,
        items: liveItems,
        historyMeta: {
          hasOlder: true,
          oldestVisibleSequence: 101,
          totalItemCount: 20,
        },
      }),
    )
    apiMock.getThreadHistoryPageByIdV3.mockResolvedValue({
      items: olderItems,
      has_more: false,
      next_before_sequence: null,
      total_item_count: 20,
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })
    await act(async () => {
      await useThreadByIdStoreV3.getState().loadMoreHistory()
    })

    expect(apiMock.getThreadHistoryPageByIdV3).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'thread-1',
      { beforeSequence: 101, limit: 200 },
    )
    const state = useThreadByIdStoreV3.getState()
    const sequences = state.snapshot?.items.map((item) => item.sequence) ?? []
    expect(sequences).toEqual([
      91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110,
    ])
    expect(state.hasOlderHistory).toBe(false)
    expect(state.oldestVisibleSequence).toBe(91)
    expect(state.totalItemCount).toBe(20)
    expect(state.isLoadingHistory).toBe(false)
    expect(state.historyError).toBeNull()
  })

  it('keeps loadMoreHistory bounded by adaptive cap when prepend would overflow live window', async () => {
    const liveItems = Array.from({ length: 1000 }, (_, index) => {
      const sequence = 301 + index
      return {
        id: `msg-${sequence}`,
        kind: 'message' as const,
        threadId: 'thread-1',
        turnId: `turn-${sequence}`,
        sequence,
        createdAt: `2026-04-01T01:${String(index % 60).padStart(2, '0')}:00Z`,
        updatedAt: `2026-04-01T01:${String(index % 60).padStart(2, '0')}:00Z`,
        status: 'completed' as const,
        source: 'upstream' as const,
        tone: 'neutral' as const,
        metadata: {},
        role: 'assistant' as const,
        text: `live-${sequence}`,
        format: 'markdown' as const,
      }
    })
    const olderItems = Array.from({ length: 300 }, (_, index) => {
      const sequence = 1 + index
      return {
        id: `msg-${sequence}`,
        kind: 'message' as const,
        threadId: 'thread-1',
        turnId: `turn-${sequence}`,
        sequence,
        createdAt: `2026-04-01T00:${String(index % 60).padStart(2, '0')}:00Z`,
        updatedAt: `2026-04-01T00:${String(index % 60).padStart(2, '0')}:00Z`,
        status: 'completed' as const,
        source: 'upstream' as const,
        tone: 'neutral' as const,
        metadata: {},
        role: 'assistant' as const,
        text: `older-${sequence}`,
        format: 'markdown' as const,
      }
    })

    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(
      makeSnapshot({
        snapshotVersion: 5,
        items: liveItems,
        historyMeta: {
          hasOlder: true,
          oldestVisibleSequence: 301,
          totalItemCount: 1300,
        },
      }),
    )
    apiMock.getThreadHistoryPageByIdV3.mockResolvedValue({
      items: olderItems,
      has_more: false,
      next_before_sequence: null,
      total_item_count: 1300,
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })
    await act(async () => {
      await useThreadByIdStoreV3.getState().loadMoreHistory()
    })

    const state = useThreadByIdStoreV3.getState()
    const sequences = state.snapshot?.items.map((item) => item.sequence) ?? []
    expect(sequences).toHaveLength(1000)
    expect(sequences[0]).toBe(301)
    expect(sequences[sequences.length - 1]).toBe(1300)
    expect(state.hasOlderHistory).toBe(true)
    expect(state.oldestVisibleSequence).toBe(301)
    expect(state.totalItemCount).toBe(1300)
  })

  it('exposes guardrail selectors for core/transport/ui-control domains', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const state = useThreadByIdStoreV3.getState()
    const core = selectCore(state)
    const transport = selectTransport(state)
    const uiControl = selectUiControl(state)

    expect(core.snapshot?.threadId).toBe('thread-1')
    expect(core.lastSnapshotVersion).toBe(1)
    expect(transport.activeProjectId).toBe('project-1')
    expect(transport.streamStatus).toBe('connecting')
    expect(uiControl.isLoading).toBe(false)
    expect(uiControl.error).toBeNull()
  })

  it('exposes focused phase-8 selectors for feed/composer/transport/workflow domains', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(
      makeSnapshot({
        activeTurnId: 'turn-1',
      }),
    )

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const state = useThreadByIdStoreV3.getState()
    const feed = selectFeedRenderState(state)
    const composer = selectComposerState(state)
    const transportBanner = selectTransportBannerState(state)
    const workflowAction = selectWorkflowActionState(state)
    const askQueue = selectAskFollowupQueueState(state)
    const askActions = selectAskFollowupQueueActions(state)
    const actions = selectThreadActions(state)

    expect(Object.keys(feed).sort()).toEqual(
      ['error', 'isLoading', 'isSending', 'lastCompletedAt', 'lastDurationMs', 'snapshot'].sort(),
    )
    expect(Object.keys(composer).sort()).toEqual(
      ['isActiveTurn', 'isLoading', 'isSending', 'snapshot'].sort(),
    )
    expect(Object.keys(transportBanner).sort()).toEqual(
      ['error', 'forcedReloadCount', 'lastForcedReloadReason', 'streamStatus'].sort(),
    )
    expect(Object.keys(workflowAction).sort()).toEqual(
      ['isLoading', 'isSending', 'lastCompletedAt', 'lastDurationMs', 'snapshot'].sort(),
    )
    expect(Object.keys(askQueue).sort()).toEqual(
      ['activeThreadRole', 'askFollowupQueue', 'askQueuePauseReason', 'isSending'].sort(),
    )
    expect(Object.keys(askActions).sort()).toEqual(
      ['confirmQueued', 'removeQueued', 'reorderAskQueued', 'retryAskQueued', 'sendAskQueuedNow'].sort(),
    )
    expect(composer.isActiveTurn).toBe(true)
    expect(transportBanner.streamStatus).toBe('connecting')
    expect(actions.loadThread).toBe(state.loadThread)
    expect(actions.disconnectThread).toBe(state.disconnectThread)
  })

  it('maps every forced reload trigger to a non-empty reason code', () => {
    const forcedPolicies = [
      decideReloadPolicy({ type: 'stream_replay_miss', message: 'replay miss' }),
      decideReloadPolicy({ type: 'contract_envelope_invalid', message: 'invalid envelope' }),
      decideReloadPolicy({ type: 'contract_thread_id_mismatch', message: 'thread mismatch' }),
      decideReloadPolicy({ type: 'contract_event_cursor_invalid', message: 'cursor invalid' }),
      decideReloadPolicy({ type: 'apply_event_failed', message: 'apply failed' }),
      decideReloadPolicy({ type: 'user_input_resolve_timeout' }),
      decideReloadPolicy({ type: 'user_input_resolve_request_failed', message: 'resolve failed' }),
      decideReloadPolicy({ type: 'stream_healthcheck_failed', setLoading: true }),
      decideReloadPolicy({ type: 'manual_retry', setLoading: true, message: 'manual retry' }),
    ]

    for (const policy of forcedPolicies) {
      expect(policy.kind).toBe('forced')
      if (policy.kind === 'forced') {
        expect(policy.reason).toBeTruthy()
      }
    }
  })

  it('applies thread.snapshot.v3 events', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          schema_version: 1,
          event_id: '2',
          event_type: 'thread.snapshot.v3',
          thread_id: 'thread-1',
          turn_id: null,
          snapshot_version: 2,
          occurred_at_ms: Date.parse('2026-04-01T00:01:00Z'),
          eventId: '2',
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'execution',
          occurredAt: '2026-04-01T00:01:00Z',
          snapshotVersion: 2,
          type: 'thread.snapshot.v3',
          payload: {
            snapshot: makeSnapshot({
              snapshotVersion: 2,
              updatedAt: '2026-04-01T00:01:00Z',
              items: [
                {
                  id: 'msg-1',
                  kind: 'message',
                  threadId: 'thread-1',
                  turnId: null,
                  sequence: 1,
                  createdAt: '2026-04-01T00:01:00Z',
                  updatedAt: '2026-04-01T00:01:00Z',
                  status: 'completed',
                  source: 'upstream',
                  tone: 'neutral',
                  metadata: {},
                  role: 'assistant',
                  text: 'Hello from V3',
                  format: 'markdown',
                },
              ],
            }),
          },
        }),
      )
    })

    const state = useThreadByIdStoreV3.getState()
    expect(state.snapshot?.snapshotVersion).toBe(2)
    expect(state.snapshot?.items).toHaveLength(1)
    expect(state.lastEventId).toBe('2')
    expect(state.isLoading).toBe(false)
  })

  it('handles stream_open without advancing lastEventId cursor', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          schema_version: 1,
          event_type: 'stream_open',
          thread_id: 'thread-1',
          turn_id: null,
          snapshot_version: 1,
          occurred_at_ms: Date.parse('2026-04-01T00:00:01Z'),
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'execution',
          occurredAt: '2026-04-01T00:00:01Z',
          snapshotVersion: 1,
          type: 'stream_open',
          payload: {
            streamStatus: 'open',
            threadId: 'thread-1',
            threadRole: 'execution',
            snapshotVersion: 1,
            processingState: 'idle',
            activeTurnId: null,
          },
        }),
      )
    })

    const state = useThreadByIdStoreV3.getState()
    expect(state.streamStatus).toBe('open')
    expect(state.lastEventId).toBeNull()
    expect(state.telemetry.heartbeat_cursor_pollution_count).toBe(0)
    expect(state.telemetry.firstMeaningfulFrameLatencyMs).not.toBeNull()
  })

  it('uses legacy fallback parser path and tracks fallback counter', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          eventId: '4',
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'execution',
          occurredAt: '2026-04-01T00:01:00Z',
          snapshotVersion: 2,
          type: 'thread.snapshot.v3',
          payload: {
            snapshot: makeSnapshot({
              snapshotVersion: 2,
              updatedAt: '2026-04-01T00:01:00Z',
            }),
          },
        }),
      )
    })

    const state = useThreadByIdStoreV3.getState()
    expect(state.snapshot?.snapshotVersion).toBe(2)
    expect(state.lastEventId).toBe('4')
    expect(state.telemetry.legacy_fallback_used_count).toBe(1)
  })

  it('treats canonical/legacy mismatch as hard contract error and reloads snapshot', async () => {
    apiMock.getThreadSnapshotByIdV3
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(makeSnapshot({ snapshotVersion: 2 }))

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          schema_version: 1,
          event_id: '10',
          event_type: 'thread.snapshot.v3',
          thread_id: 'thread-1',
          turn_id: null,
          snapshot_version: 2,
          occurred_at_ms: Date.parse('2026-04-01T00:01:00Z'),
          eventId: '11',
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'execution',
          occurredAt: '2026-04-01T00:01:00Z',
          snapshotVersion: 2,
          type: 'thread.snapshot.v3',
          payload: {
            snapshot: makeSnapshot({
              snapshotVersion: 2,
              updatedAt: '2026-04-01T00:01:00Z',
            }),
          },
        }),
      )
    })

    await waitFor(() => {
      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
    })

    const state = useThreadByIdStoreV3.getState()
    expect(state.telemetry.envelope_validation_failure_count).toBe(1)
    expect(state.telemetry.forcedSnapshotReloadCount).toBe(1)
    expect(state.telemetry.lastForcedReloadReason).toBe('CONTRACT_ENVELOPE_INVALID')
    expect(state.lastEventId).toBeNull()
  })

  it('rejects business event with mismatched thread_id and reloads snapshot', async () => {
    apiMock.getThreadSnapshotByIdV3
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(makeSnapshot({ snapshotVersion: 2 }))

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          schema_version: 1,
          event_id: '12',
          event_type: 'thread.snapshot.v3',
          thread_id: 'thread-2',
          turn_id: null,
          snapshot_version: 2,
          occurred_at_ms: Date.parse('2026-04-01T00:01:00Z'),
          eventId: '12',
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'execution',
          occurredAt: '2026-04-01T00:01:00Z',
          snapshotVersion: 2,
          type: 'thread.snapshot.v3',
          payload: {
            snapshot: makeSnapshot({
              threadId: 'thread-2',
              snapshotVersion: 2,
              updatedAt: '2026-04-01T00:01:00Z',
            }),
          },
        }),
      )
    })

    await waitFor(() => {
      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
    })

    const state = useThreadByIdStoreV3.getState()
    expect(state.telemetry.envelope_validation_failure_count).toBe(1)
    expect(state.telemetry.forcedSnapshotReloadCount).toBe(1)
    expect(state.telemetry.lastForcedReloadReason).toBe('CONTRACT_THREAD_ID_MISMATCH')
    expect(state.lastEventId).toBeNull()
  })

  it('rejects duplicate event_id cursor and reloads with CONTRACT_EVENT_CURSOR_INVALID', async () => {
    apiMock.getThreadSnapshotByIdV3
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(makeSnapshot({ snapshotVersion: 3 }))

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          schema_version: 1,
          event_id: '2',
          event_type: 'thread.snapshot.v3',
          thread_id: 'thread-1',
          turn_id: null,
          snapshot_version: 2,
          occurred_at_ms: Date.parse('2026-04-01T00:01:00Z'),
          eventId: '2',
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'execution',
          occurredAt: '2026-04-01T00:01:00Z',
          snapshotVersion: 2,
          type: 'thread.snapshot.v3',
          payload: {
            snapshot: makeSnapshot({
              snapshotVersion: 2,
              updatedAt: '2026-04-01T00:01:00Z',
            }),
          },
        }),
      )
      eventSource.emitMessage(
        JSON.stringify({
          schema_version: 1,
          event_id: '2',
          event_type: 'thread.snapshot.v3',
          thread_id: 'thread-1',
          turn_id: null,
          snapshot_version: 3,
          occurred_at_ms: Date.parse('2026-04-01T00:01:01Z'),
          eventId: '2',
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'execution',
          occurredAt: '2026-04-01T00:01:01Z',
          snapshotVersion: 3,
          type: 'thread.snapshot.v3',
          payload: {
            snapshot: makeSnapshot({
              snapshotVersion: 3,
              updatedAt: '2026-04-01T00:01:01Z',
            }),
          },
        }),
      )
    })

    await waitFor(() => {
      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
    })
    const state = useThreadByIdStoreV3.getState()
    expect(state.telemetry.forcedSnapshotReloadCount).toBe(1)
    expect(state.telemetry.lastForcedReloadReason).toBe('CONTRACT_EVENT_CURSOR_INVALID')
  })

  it('reloads snapshot when event patch cannot be applied', async () => {
    apiMock.getThreadSnapshotByIdV3
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(
        makeSnapshot({
          snapshotVersion: 2,
          items: [
            {
              id: 'msg-1',
              kind: 'message',
              threadId: 'thread-1',
              turnId: null,
              sequence: 1,
              createdAt: '2026-04-01T00:01:00Z',
              updatedAt: '2026-04-01T00:01:00Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              role: 'assistant',
              text: 'Recovered snapshot',
              format: 'markdown',
            },
          ],
        }),
      )

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          schema_version: 1,
          event_id: '3',
          event_type: 'conversation.item.patch.v3',
          thread_id: 'thread-1',
          turn_id: null,
          snapshot_version: 2,
          occurred_at_ms: Date.parse('2026-04-01T00:01:00Z'),
          eventId: '3',
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'execution',
          occurredAt: '2026-04-01T00:01:00Z',
          snapshotVersion: 2,
          type: 'conversation.item.patch.v3',
          payload: {
            itemId: 'missing',
            patch: {
              kind: 'message',
              textAppend: 'delta',
              updatedAt: '2026-04-01T00:01:00Z',
            },
          },
        }),
      )
    })

    await waitFor(() => {
      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
      expect(useThreadByIdStoreV3.getState().snapshot?.snapshotVersion).toBe(2)
    })
    expect(useThreadByIdStoreV3.getState().telemetry.applyErrorCount).toBe(1)
    expect(useThreadByIdStoreV3.getState().telemetry.forcedSnapshotReloadCount).toBe(1)
    expect(useThreadByIdStoreV3.getState().telemetry.lastForcedReloadReason).toBe(
      'APPLY_EVENT_FAILED',
    )
  })

  it('runs plan action through dedicated V3 endpoint and updates turn state', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())
    apiMock.planActionByIdV3.mockResolvedValue({
      accepted: true,
      threadId: 'thread-1',
      turnId: 'turn-followup-1',
      snapshotVersion: 3,
      action: 'implement_plan',
      planItemId: 'plan-1',
      revision: 7,
    })

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().runPlanAction('implement_plan', 'plan-1', 7)
    })

    expect(apiMock.planActionByIdV3).toHaveBeenCalledWith('project-1', 'node-1', 'thread-1', {
      action: 'implement_plan',
      planItemId: 'plan-1',
      revision: 7,
      text: undefined,
    })
    const state = useThreadByIdStoreV3.getState()
    expect(state.isSending).toBe(false)
    expect(state.snapshot?.processingState).toBe('running')
    expect(state.snapshot?.activeTurnId).toBe('turn-followup-1')
    expect(state.lastSnapshotVersion).toBe(3)
  })

  it('optimistically submits user-input answers and falls back to snapshot reload on timeout', async () => {
    vi.useFakeTimers()
    try {
      apiMock.getThreadSnapshotByIdV3
        .mockResolvedValueOnce(
          makeSnapshot({
            snapshotVersion: 5,
            processingState: 'waiting_user_input',
            items: [
              {
                id: 'msg-0',
                kind: 'message',
                threadId: 'thread-1',
                turnId: 'turn-1',
                sequence: 1,
                createdAt: '2026-04-01T00:00:05Z',
                updatedAt: '2026-04-01T00:00:05Z',
                status: 'completed',
                source: 'upstream',
                tone: 'neutral',
                metadata: {},
                role: 'assistant',
                text: 'Context',
                format: 'markdown',
              },
              {
                id: 'input-1',
                kind: 'userInput',
                threadId: 'thread-1',
                turnId: 'turn-1',
                sequence: 3,
                createdAt: '2026-04-01T00:00:10Z',
                updatedAt: '2026-04-01T00:00:10Z',
                status: 'requested',
                source: 'upstream',
                tone: 'info',
                metadata: {},
                requestId: 'req-1',
                title: 'Need answer',
                questions: [],
                answers: [],
                requestedAt: '2026-04-01T00:00:10Z',
                resolvedAt: null,
              },
            ],
            uiSignals: {
              planReady: {
                planItemId: null,
                revision: null,
                ready: false,
                failed: false,
              },
              activeUserInputRequests: [
                {
                  requestId: 'req-1',
                  itemId: 'input-1',
                  threadId: 'thread-1',
                  turnId: 'turn-1',
                  status: 'requested',
                  createdAt: '2026-04-01T00:00:10Z',
                  submittedAt: null,
                  resolvedAt: null,
                  answers: [],
                },
              ],
            },
          }),
        )
        .mockResolvedValueOnce(
          makeSnapshot({
            snapshotVersion: 6,
            processingState: 'idle',
            items: [
              {
                id: 'msg-0',
                kind: 'message',
                threadId: 'thread-1',
                turnId: 'turn-1',
                sequence: 1,
                createdAt: '2026-04-01T00:00:05Z',
                updatedAt: '2026-04-01T00:00:05Z',
                status: 'completed',
                source: 'upstream',
                tone: 'neutral',
                metadata: {},
                role: 'assistant',
                text: 'Context',
                format: 'markdown',
              },
              {
                id: 'input-1',
                kind: 'userInput',
                threadId: 'thread-1',
                turnId: 'turn-1',
                sequence: 3,
                createdAt: '2026-04-01T00:00:10Z',
                updatedAt: '2026-04-01T00:00:20Z',
                status: 'answered',
                source: 'upstream',
                tone: 'info',
                metadata: {},
                requestId: 'req-1',
                title: 'Need answer',
                questions: [],
                answers: [{ questionId: 'q1', value: 'yes', label: 'Yes' }],
                requestedAt: '2026-04-01T00:00:10Z',
                resolvedAt: '2026-04-01T00:00:20Z',
              },
            ],
            uiSignals: {
              planReady: {
                planItemId: null,
                revision: null,
                ready: false,
                failed: false,
              },
              activeUserInputRequests: [
                {
                  requestId: 'req-1',
                  itemId: 'input-1',
                  threadId: 'thread-1',
                  turnId: 'turn-1',
                  status: 'answered',
                  createdAt: '2026-04-01T00:00:10Z',
                  submittedAt: '2026-04-01T00:00:11Z',
                  resolvedAt: '2026-04-01T00:00:20Z',
                  answers: [{ questionId: 'q1', value: 'yes', label: 'Yes' }],
                },
              ],
            },
          }),
        )
      apiMock.resolveThreadUserInputByIdV3.mockResolvedValue({
        requestId: 'req-1',
        itemId: 'input-1',
        threadId: 'thread-1',
        turnId: 'turn-1',
        status: 'answer_submitted',
        answers: [{ questionId: 'q1', value: 'yes', label: 'Yes' }],
        submittedAt: '2026-04-01T00:00:11Z',
      })

      await act(async () => {
        await useThreadByIdStoreV3
          .getState()
          .loadThread('project-1', 'node-1', 'thread-1', 'execution')
      })
      const beforeResolveSnapshot = useThreadByIdStoreV3.getState().snapshot
      const beforeResolveMessageRef = beforeResolveSnapshot?.items[0]

      await act(async () => {
        await useThreadByIdStoreV3.getState().resolveUserInput('req-1', [
          { questionId: 'q1', value: 'yes', label: 'Yes' },
        ])
      })
      const afterOptimisticSnapshot = useThreadByIdStoreV3.getState().snapshot

      expect(apiMock.resolveThreadUserInputByIdV3).toHaveBeenCalledWith(
        'project-1',
        'node-1',
        'thread-1',
        'req-1',
        [{ questionId: 'q1', value: 'yes', label: 'Yes' }],
      )
      expect(
        useThreadByIdStoreV3.getState().snapshot?.uiSignals.activeUserInputRequests[0]?.status,
      ).toBe('answer_submitted')
      expect(afterOptimisticSnapshot?.items.map((item) => item.id)).toEqual(['msg-0', 'input-1'])
      expect(afterOptimisticSnapshot?.items[0]).toBe(beforeResolveMessageRef)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000)
      })

      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
      expect(useThreadByIdStoreV3.getState().snapshot?.snapshotVersion).toBe(6)
      expect(useThreadByIdStoreV3.getState().telemetry.forcedSnapshotReloadCount).toBe(1)
      expect(useThreadByIdStoreV3.getState().telemetry.lastForcedReloadReason).toBe(
        'USER_INPUT_RESOLVE_TIMEOUT',
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it('forces snapshot reload with STREAM_HEALTHCHECK_FAILED when stream is unhealthy after resolve submit', async () => {
    apiMock.getThreadSnapshotByIdV3
      .mockResolvedValueOnce(makePendingUserInputSnapshot())
      .mockResolvedValueOnce(
        makePendingUserInputSnapshot({
          snapshotVersion: 6,
          processingState: 'idle',
        }),
      )
    apiMock.resolveThreadUserInputByIdV3.mockResolvedValue({
      requestId: 'req-1',
      itemId: 'input-1',
      threadId: 'thread-1',
      turnId: 'turn-1',
      status: 'answer_submitted',
      answers: [{ questionId: 'q1', value: 'yes', label: 'Yes' }],
      submittedAt: '2026-04-01T00:00:11Z',
    })

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    useThreadByIdStoreV3.setState({ streamStatus: 'error' })

    await act(async () => {
      await useThreadByIdStoreV3.getState().resolveUserInput('req-1', [
        { questionId: 'q1', value: 'yes', label: 'Yes' },
      ])
    })

    expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
    const state = useThreadByIdStoreV3.getState()
    expect(state.telemetry.forcedSnapshotReloadCount).toBe(1)
    expect(state.telemetry.lastForcedReloadReason).toBe('STREAM_HEALTHCHECK_FAILED')
  })

  it('forces snapshot reload with USER_INPUT_RESOLVE_REQUEST_FAILED when resolve API fails', async () => {
    apiMock.getThreadSnapshotByIdV3
      .mockResolvedValueOnce(makePendingUserInputSnapshot())
      .mockResolvedValueOnce(
        makePendingUserInputSnapshot({
          snapshotVersion: 6,
          processingState: 'failed',
        }),
      )
    apiMock.resolveThreadUserInputByIdV3.mockRejectedValue(new Error('resolve failed'))

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().resolveUserInput('req-1', [
        { questionId: 'q1', value: 'yes', label: 'Yes' },
      ])
    })

    expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
    const state = useThreadByIdStoreV3.getState()
    expect(state.telemetry.forcedSnapshotReloadCount).toBe(1)
    expect(state.telemetry.lastForcedReloadReason).toBe('USER_INPUT_RESOLVE_REQUEST_FAILED')
  })

  it('increments reconnect telemetry when stream errors and reopens stream without snapshot reload', async () => {
    vi.useFakeTimers()
    try {
      apiMock.getThreadSnapshotByIdV3.mockResolvedValueOnce(makeSnapshot())

      await act(async () => {
        await useThreadByIdStoreV3
          .getState()
          .loadThread('project-1', 'node-1', 'thread-1', 'execution')
      })

      const eventSource = getEventSourceMock().instances[0]
      await act(async () => {
        eventSource.emitError()
      })

      expect(useThreadByIdStoreV3.getState().streamStatus).toBe('reconnecting')
      expect(useThreadByIdStoreV3.getState().telemetry.streamReconnectCount).toBe(1)
      expect(useThreadByIdStoreV3.getState().telemetry.lastForcedReloadReason).toBeNull()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1100)
      })

      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(1)
      expect(getEventSourceMock().instances).toHaveLength(2)
      expect(apiMock.probeThreadByIdEventsCursorV3).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('reconnects with last_event_id query when cursor is available', async () => {
    vi.useFakeTimers()
    try {
      apiMock.getThreadSnapshotByIdV3.mockResolvedValueOnce(makeSnapshot())
      apiMock.probeThreadByIdEventsCursorV3.mockResolvedValue('ok')

      await act(async () => {
        await useThreadByIdStoreV3
          .getState()
          .loadThread('project-1', 'node-1', 'thread-1', 'execution')
      })

      const firstSource = getEventSourceMock().instances[0]
      firstSource.emitOpen()

      await act(async () => {
        firstSource.emitMessage(
          JSON.stringify({
            schema_version: 1,
            event_id: '2',
            event_type: 'thread.snapshot.v3',
            thread_id: 'thread-1',
            turn_id: null,
            snapshot_version: 2,
            occurred_at_ms: Date.parse('2026-04-01T00:01:00Z'),
            eventId: '2',
            channel: 'thread',
            projectId: 'project-1',
            nodeId: 'node-1',
            threadRole: 'execution',
            occurredAt: '2026-04-01T00:01:00Z',
            snapshotVersion: 2,
            type: 'thread.snapshot.v3',
            payload: {
              snapshot: makeSnapshot({
                snapshotVersion: 2,
                updatedAt: '2026-04-01T00:01:00Z',
              }),
            },
          }),
        )
      })

      await act(async () => {
        firstSource.emitError()
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1100)
      })

      expect(apiMock.probeThreadByIdEventsCursorV3).toHaveBeenCalledWith(
        'project-1',
        'node-1',
        'thread-1',
        '2',
      )
      const secondSource = getEventSourceMock().instances[1]
      expect(secondSource.url).toContain('last_event_id=2')
    } finally {
      vi.useRealTimers()
    }
  })

  it('handles replay_miss by targeted snapshot resync and cursor reset', async () => {
    vi.useFakeTimers()
    try {
      apiMock.getThreadSnapshotByIdV3
        .mockResolvedValueOnce(makeSnapshot())
        .mockResolvedValueOnce(makeSnapshot({ snapshotVersion: 3 }))
      apiMock.probeThreadByIdEventsCursorV3.mockResolvedValue('mismatch')

      await act(async () => {
        await useThreadByIdStoreV3
          .getState()
          .loadThread('project-1', 'node-1', 'thread-1', 'execution')
      })

      const firstSource = getEventSourceMock().instances[0]
      firstSource.emitOpen()

      await act(async () => {
        firstSource.emitMessage(
          JSON.stringify({
            schema_version: 1,
            event_id: '2',
            event_type: 'thread.snapshot.v3',
            thread_id: 'thread-1',
            turn_id: null,
            snapshot_version: 2,
            occurred_at_ms: Date.parse('2026-04-01T00:01:00Z'),
            eventId: '2',
            channel: 'thread',
            projectId: 'project-1',
            nodeId: 'node-1',
            threadRole: 'execution',
            occurredAt: '2026-04-01T00:01:00Z',
            snapshotVersion: 2,
            type: 'thread.snapshot.v3',
            payload: {
              snapshot: makeSnapshot({
                snapshotVersion: 2,
                updatedAt: '2026-04-01T00:01:00Z',
              }),
            },
          }),
        )
      })

      await act(async () => {
        firstSource.emitError()
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1100)
      })

      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenNthCalledWith(
        2,
        'project-1',
        'node-1',
        'thread-1',
        1000,
      )
      const state = useThreadByIdStoreV3.getState()
      expect(state.lastEventId).toBeNull()
      expect(state.telemetry.forcedSnapshotReloadCount).toBe(1)
      expect(state.telemetry.lastForcedReloadReason).toBe('REPLAY_MISS')
      expect(getEventSourceMock().instances).toHaveLength(2)
      expect(getEventSourceMock().instances[1]?.url).not.toContain('last_event_id=')
    } finally {
      vi.useRealTimers()
    }
  })

  it('batches burst business events into one flush while preserving order and cursor', async () => {
    vi.useFakeTimers()
    try {
      apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())

      await act(async () => {
        await useThreadByIdStoreV3
          .getState()
          .loadThread('project-1', 'node-1', 'thread-1', 'execution')
      })

      const eventSource = getEventSourceMock().instances[0]
      eventSource.emitOpen()

      await act(async () => {
        eventSource.emitMessage(JSON.stringify(makeMessageUpsertEnvelope('2', 2, 'Hello')))
        eventSource.emitMessage(JSON.stringify(makeMessagePatchEnvelope('3', 3, ' there')))
        eventSource.emitMessage(JSON.stringify(makeMessagePatchEnvelope('4', 4, '!')))
      })

      expect(useThreadByIdStoreV3.getState().lastEventId).toBeNull()
      expect(useThreadByIdStoreV3.getState().telemetry.batchedEventsApplied).toBe(0)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(20)
      })

      const state = useThreadByIdStoreV3.getState()
      expect(state.lastEventId).toBe('4')
      expect(state.snapshot?.items).toHaveLength(1)
      expect(state.snapshot?.items[0].kind).toBe('message')
      expect((state.snapshot?.items[0] as { text: string }).text).toBe('Hello there!')
      expect(state.telemetry.batchedFlushCount).toBe(1)
      expect(state.telemetry.batchedEventsApplied).toBe(3)
      expect(state.telemetry.forcedFlushCount).toBe(0)
      expect(state.telemetry.fastAppendHitCount).toBe(2)
      expect(state.telemetry.fastAppendFallbackCount).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('forces immediate flush for critical lifecycle boundaries', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          schema_version: 1,
          event_id: '2',
          event_type: 'thread.lifecycle.v3',
          thread_id: 'thread-1',
          turn_id: 'turn-2',
          snapshot_version: 2,
          occurred_at_ms: Date.parse('2026-04-01T00:02:00Z'),
          eventId: '2',
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'execution',
          occurredAt: '2026-04-01T00:02:00Z',
          snapshotVersion: 2,
          type: 'thread.lifecycle.v3',
          payload: {
            activeTurnId: 'turn-2',
            processingState: 'waiting_user_input',
            state: 'waiting_user_input',
            detail: null,
          },
        }),
      )
    })

    const state = useThreadByIdStoreV3.getState()
    expect(state.lastEventId).toBe('2')
    expect(state.telemetry.batchedFlushCount).toBe(1)
    expect(state.telemetry.forcedFlushCount).toBe(1)
    expect(state.snapshot?.processingState).toBe('waiting_user_input')
  })

  it('clears queued events on stream error before reconnect to avoid stale apply', async () => {
    vi.useFakeTimers()
    try {
      apiMock.getThreadSnapshotByIdV3.mockResolvedValue(
        makeSnapshot({
          items: [
            {
              id: 'msg-1',
              kind: 'message',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 1,
              createdAt: '2026-04-01T00:00:00Z',
              updatedAt: '2026-04-01T00:00:00Z',
              status: 'in_progress',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              role: 'assistant',
              text: 'Base',
              format: 'markdown',
            },
          ],
        }),
      )

      await act(async () => {
        await useThreadByIdStoreV3
          .getState()
          .loadThread('project-1', 'node-1', 'thread-1', 'execution')
      })

      const eventSource = getEventSourceMock().instances[0]
      eventSource.emitOpen()

      await act(async () => {
        eventSource.emitMessage(JSON.stringify(makeMessagePatchEnvelope('2', 2, ' stale')))
      })

      await act(async () => {
        eventSource.emitError()
      })

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1100)
      })

      const state = useThreadByIdStoreV3.getState()
      expect(state.lastEventId).toBeNull()
      expect(state.telemetry.batchedEventsApplied).toBe(0)
      expect((state.snapshot?.items[0] as { text: string }).text).toBe('Base')
      expect(getEventSourceMock().instances).toHaveLength(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports ask stream reconnect/error events to rollout metrics API', async () => {
    vi.useFakeTimers()
    try {
      apiMock.getThreadSnapshotByIdV3
        .mockResolvedValueOnce(makeSnapshot({ threadId: 'ask-thread-1', threadRole: 'ask_planning' }))
        .mockResolvedValueOnce(
          makeSnapshot({ threadId: 'ask-thread-1', threadRole: 'ask_planning', snapshotVersion: 2 }),
        )

      await act(async () => {
        await useThreadByIdStoreV3
          .getState()
          .loadThread('project-1', 'node-1', 'ask-thread-1', 'ask_planning')
      })

      const eventSource = getEventSourceMock().instances[0]
      await act(async () => {
        eventSource.emitError()
      })

      expect(apiMock.reportAskRolloutMetricEvent).toHaveBeenCalledWith('stream_error')
      expect(apiMock.reportAskRolloutMetricEvent).toHaveBeenCalledWith('stream_reconnect')
    } finally {
      vi.useRealTimers()
    }
  })

  it('enqueues ask turn and auto-flushes immediately when send window is open', async () => {
    apiMock.startThreadTurnByIdV3.mockResolvedValue({
      threadId: 'ask-thread-1',
      turnId: 'ask-turn-2',
      snapshotVersion: 2,
    })
    setAskQueueRuntimeState({
      snapshot: makeAskSnapshot({
        activeTurnId: null,
        processingState: 'idle',
      }),
      streamStatus: 'open',
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().sendTurn('ask hello')
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    const metadata = apiMock.startThreadTurnByIdV3.mock.calls[0]?.[4] as Record<string, unknown> | undefined
    expect(metadata?.idempotencyKey).toEqual(expect.any(String))
    expect(String(metadata?.idempotencyKey ?? '')).toMatch(/^ask_turn:/)
    const state = useThreadByIdStoreV3.getState()
    expect(state.askFollowupQueue).toHaveLength(0)
    expect(state.snapshot?.activeTurnId).toBe('ask-turn-2')
    expect(state.snapshot?.processingState).toBe('running')
  })

  it('blocks ask auto-flush for stream mismatch and waiting user input', async () => {
    setAskQueueRuntimeState({
      streamStatus: 'reconnecting',
    })
    await act(async () => {
      await useThreadByIdStoreV3.getState().sendTurn('blocked by stream')
    })
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)
    expect(useThreadByIdStoreV3.getState().askFollowupQueue).toHaveLength(1)
    expect(useThreadByIdStoreV3.getState().askQueuePauseReason).toBe('stream_or_state_mismatch')

    useThreadByIdStoreV3.setState({
      streamStatus: 'open',
      askFollowupQueue: [],
      askQueuePauseReason: 'none',
      snapshot: makeAskSnapshot({
        activeTurnId: null,
        processingState: 'idle',
        uiSignals: {
          planReady: {
            planItemId: null,
            revision: null,
            ready: false,
            failed: false,
          },
          activeUserInputRequests: [
            {
              requestId: 'ask-input-1',
              itemId: 'input-1',
              threadId: 'ask-thread-1',
              turnId: 'turn-1',
              status: 'requested',
              createdAt: '2026-04-01T00:00:10Z',
              submittedAt: null,
              resolvedAt: null,
              answers: [],
            },
          ],
        },
      }),
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().sendTurn('blocked by input')
    })
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)
    expect(useThreadByIdStoreV3.getState().askFollowupQueue).toHaveLength(1)
    expect(useThreadByIdStoreV3.getState().askQueuePauseReason).toBe('waiting_user_input')
  })

  it('marks failed ask head and stops auto-flush at failed FIFO head', async () => {
    apiMock.startThreadTurnByIdV3.mockRejectedValueOnce(new Error('ask send failed'))
    setAskQueueRuntimeState()

    await act(async () => {
      await useThreadByIdStoreV3.getState().sendTurn('first ask')
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    const afterFailure = useThreadByIdStoreV3.getState().askFollowupQueue
    expect(afterFailure).toHaveLength(1)
    expect(afterFailure[0].status).toBe('failed')
    expect(afterFailure[0].lastError).toContain('ask send failed')

    await act(async () => {
      await useThreadByIdStoreV3.getState().sendTurn('second ask')
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    expect(useThreadByIdStoreV3.getState().askFollowupQueue.map((entry) => entry.status)).toEqual([
      'failed',
      'queued',
    ])
  })

  it('clears ask queue on thread-route mismatch failure to honor reset policy', async () => {
    const mismatchError = Object.assign(
      new Error('Thread id does not match any active route for this node.'),
      {
        code: 'invalid_request',
        status: 400,
      },
    )
    apiMock.startThreadTurnByIdV3.mockRejectedValueOnce(mismatchError)
    setAskQueueRuntimeState()

    await act(async () => {
      await useThreadByIdStoreV3.getState().sendTurn('ask after reset mismatch')
    })

    const state = useThreadByIdStoreV3.getState()
    expect(state.askFollowupQueue).toHaveLength(0)
    expect(state.streamStatus).toBe('error')
    expect(state.askQueuePauseReason).toBe('stream_or_state_mismatch')
    expect(state.error).toContain('Thread id does not match any active route for this node.')
    expect(globalThis.localStorage.getItem(askQueueStorageKey())).toBeNull()
  })

  it('hydrates ask requires_confirmation entries and never auto-sends them after reload', async () => {
    globalThis.localStorage.setItem(
      askQueueStorageKey(),
      JSON.stringify([
        makeAskQueueEntry({
          entryId: 'ask-persisted-blocked',
          text: 'persisted blocked ask',
          status: 'requires_confirmation',
          confirmationReason: 'thread_drift',
        }),
      ]),
    )
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeAskSnapshot())
    apiMock.startThreadTurnByIdV3.mockResolvedValue({
      threadId: 'ask-thread-1',
      turnId: 'ask-turn-hydrated',
      snapshotVersion: 3,
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'ask-thread-1', 'ask_planning')
    })

    const hydratedQueue = useThreadByIdStoreV3.getState().askFollowupQueue
    expect(hydratedQueue).toHaveLength(1)
    expect(hydratedQueue[0].status).toBe('requires_confirmation')
    expect(hydratedQueue[0].confirmationReason).toBe('thread_drift')
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)

    const eventSource = getEventSourceMock().instances[0]
    await act(async () => {
      eventSource.emitOpen()
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)
    expect(useThreadByIdStoreV3.getState().askFollowupQueue).toHaveLength(1)
    expect(useThreadByIdStoreV3.getState().askQueuePauseReason).toBe('requires_confirmation')
  })

  it('transitions risky ask head to requires_confirmation and only sends after explicit confirm', async () => {
    let resolveSend: (() => void) | null = null
    const pendingSend = new Promise<void>((resolve) => {
      resolveSend = resolve
    })
    apiMock.startThreadTurnByIdV3.mockImplementation(async () => {
      await pendingSend
      return {
        threadId: 'ask-thread-1',
        turnId: 'ask-turn-confirmed',
        snapshotVersion: 4,
      }
    })
    const staleCreatedAtMs = Date.now() - 90_500
    globalThis.localStorage.setItem(
      askQueueStorageKey(),
      JSON.stringify([
        makeAskQueueEntry({
          entryId: 'ask-risky-1',
          text: 'risky ask',
          idempotencyKey: 'ask-idem-risky-1',
          createdAtMs: staleCreatedAtMs,
          status: 'queued',
        }),
      ]),
    )
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeAskSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'ask-thread-1', 'ask_planning')
    })

    const eventSource = getEventSourceMock().instances[0]
    await act(async () => {
      eventSource.emitOpen()
    })

    await waitFor(() => {
      const head = useThreadByIdStoreV3.getState().askFollowupQueue[0]
      expect(head?.status).toBe('requires_confirmation')
    })
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)
    const blockedHead = useThreadByIdStoreV3.getState().askFollowupQueue[0]
    expect(blockedHead?.confirmationReason).toBe('stale_age')
    expect(useThreadByIdStoreV3.getState().askQueuePauseReason).toBe('requires_confirmation')

    let confirmPromise: Promise<void> | null = null
    act(() => {
      confirmPromise = useThreadByIdStoreV3.getState().confirmQueued('ask-risky-1')
    })
    expect(confirmPromise).not.toBeNull()

    await waitFor(() => {
      expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    })
    const sendingHead = useThreadByIdStoreV3.getState().askFollowupQueue[0]
    expect(sendingHead?.status).toBe('sending')
    expect(sendingHead?.confirmationReason).toBeNull()
    expect(Number(sendingHead?.createdAtMs ?? 0)).toBeGreaterThan(staleCreatedAtMs)

    resolveSend?.()
    await act(async () => {
      await confirmPromise!
      await pendingSend
    })

    expect(useThreadByIdStoreV3.getState().askFollowupQueue).toHaveLength(0)
  })

  it('keeps strict FIFO when ask head requires confirmation and removeQueued unblocks next entry flush', async () => {
    apiMock.startThreadTurnByIdV3.mockResolvedValue({
      threadId: 'ask-thread-1',
      turnId: 'ask-turn-after-discard',
      snapshotVersion: 4,
    })
    globalThis.localStorage.setItem(
      askQueueStorageKey(),
      JSON.stringify([
        makeAskQueueEntry({
          entryId: 'ask-blocked-head',
          text: 'blocked head ask',
          idempotencyKey: 'ask-idem-blocked-head',
          status: 'requires_confirmation',
          confirmationReason: 'thread_drift',
        }),
        makeAskQueueEntry({
          entryId: 'ask-next-queued',
          text: 'next queued ask',
          idempotencyKey: 'ask-idem-next-queued',
          status: 'queued',
        }),
      ]),
    )
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeAskSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'ask-thread-1', 'ask_planning')
    })

    const eventSource = getEventSourceMock().instances[0]
    await act(async () => {
      eventSource.emitOpen()
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)
    expect(useThreadByIdStoreV3.getState().askQueuePauseReason).toBe('requires_confirmation')
    expect(useThreadByIdStoreV3.getState().askFollowupQueue.map((entry) => entry.entryId)).toEqual([
      'ask-blocked-head',
      'ask-next-queued',
    ])

    await act(async () => {
      useThreadByIdStoreV3.getState().removeQueued('ask-blocked-head')
    })

    await waitFor(() => {
      expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    })
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'ask-thread-1',
      'next queued ask',
      { idempotencyKey: 'ask-idem-next-queued' },
    )
    expect(useThreadByIdStoreV3.getState().askFollowupQueue).toHaveLength(0)
  })

  it('preserves ask queue order across rapid sends during active turn with explicit confirmation after drift', async () => {
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(
      makeAskSnapshot({
        activeTurnId: 'ask-turn-running',
        processingState: 'running',
      }),
    )
    apiMock.startThreadTurnByIdV3
      .mockResolvedValueOnce({ threadId: 'ask-thread-1', turnId: 'ask-turn-1', snapshotVersion: 3 })
      .mockResolvedValueOnce({ threadId: 'ask-thread-1', turnId: 'ask-turn-2', snapshotVersion: 4 })
      .mockResolvedValueOnce({ threadId: 'ask-thread-1', turnId: 'ask-turn-3', snapshotVersion: 5 })

    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'ask-thread-1', 'ask_planning')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      await Promise.all([
        useThreadByIdStoreV3.getState().sendTurn('ask first'),
        useThreadByIdStoreV3.getState().sendTurn('ask second'),
        useThreadByIdStoreV3.getState().sendTurn('ask third'),
      ])
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)
    expect(useThreadByIdStoreV3.getState().askFollowupQueue.map((entry) => entry.text)).toEqual([
      'ask first',
      'ask second',
      'ask third',
    ])

    for (let index = 0; index < 3; index += 1) {
      const eventId = String(index + 2)
      await act(async () => {
        eventSource.emitMessage(
          JSON.stringify({
            schema_version: 1,
            event_id: eventId,
            event_type: 'thread.snapshot.v3',
            thread_id: 'ask-thread-1',
            turn_id: null,
            snapshot_version: index + 2,
            occurred_at_ms: Date.parse(`2026-04-01T00:0${index + 1}:00Z`),
            eventId,
            channel: 'thread',
            projectId: 'project-1',
            nodeId: 'node-1',
            threadRole: 'ask_planning',
            occurredAt: `2026-04-01T00:0${index + 1}:00Z`,
            snapshotVersion: index + 2,
            type: 'thread.snapshot.v3',
            payload: {
              snapshot: makeAskSnapshot({
                snapshotVersion: index + 2,
                activeTurnId: null,
                processingState: 'idle',
              }),
            },
          }),
        )
      })

      await waitFor(() => {
        const head = useThreadByIdStoreV3.getState().askFollowupQueue[0]
        expect(head?.status).toBe('requires_confirmation')
      })
      const head = useThreadByIdStoreV3.getState().askFollowupQueue[0]
      expect(head?.confirmationReason).toBe('snapshot_drift')
      expect(head?.entryId).toBeTruthy()
      await act(async () => {
        await useThreadByIdStoreV3.getState().confirmQueued(head!.entryId)
      })

      await waitFor(() => {
        expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(index + 1)
      })
    }

    expect(apiMock.startThreadTurnByIdV3.mock.calls.map((call) => call[3])).toEqual([
      'ask first',
      'ask second',
      'ask third',
    ])
  })

  it('keeps ask queue single-flight under repeated dispatch triggers for the same head entry', async () => {
    let resolveSend: (() => void) | null = null
    const pendingSend = new Promise<void>((resolve) => {
      resolveSend = resolve
    })
    apiMock.startThreadTurnByIdV3.mockImplementation(async () => {
      await pendingSend
      return {
        threadId: 'ask-thread-1',
        turnId: 'ask-turn-single-flight',
        snapshotVersion: 3,
      }
    })
    globalThis.localStorage.setItem(
      askQueueStorageKey(),
      JSON.stringify([
        makeAskQueueEntry({
          entryId: 'ask-single-flight',
          text: 'ask once only',
          status: 'queued',
        }),
      ]),
    )
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeAskSnapshot())

    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'ask-thread-1', 'ask_planning')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()
    eventSource.emitOpen()

    await waitFor(() => {
      expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    })

    resolveSend?.()
    await act(async () => {
      await pendingSend
    })
  })

  it('reorders ask queue entries, persists order, and recomputes pause reason', () => {
    setAskQueueRuntimeState({
      snapshot: makeAskSnapshot({
        activeTurnId: 'ask-turn-running',
        processingState: 'running',
      }),
      askFollowupQueue: [
        makeAskQueueEntry({ entryId: 'ask-1', text: 'first ask' }),
        makeAskQueueEntry({ entryId: 'ask-2', text: 'second ask' }),
        makeAskQueueEntry({ entryId: 'ask-3', text: 'third ask' }),
      ],
    })

    useThreadByIdStoreV3.getState().reorderAskQueued(2, 0)

    const state = useThreadByIdStoreV3.getState()
    expect(state.askFollowupQueue.map((entry) => entry.entryId)).toEqual(['ask-3', 'ask-1', 'ask-2'])
    expect(state.askQueuePauseReason).toBe('active_turn_running')
    const persistedPayload = globalThis.localStorage.getItem(askQueueStorageKey())
    expect(persistedPayload).toBeTruthy()
    const persisted = JSON.parse(String(persistedPayload)) as Array<{ entryId: string }>
    expect(persisted.map((entry) => entry.entryId)).toEqual(['ask-3', 'ask-1', 'ask-2'])
  })

  it('keeps reorderAskQueued as no-op when ask queue is sending', () => {
    setAskQueueRuntimeState({
      askFollowupQueue: [
        makeAskQueueEntry({ entryId: 'ask-sending', status: 'sending' }),
        makeAskQueueEntry({ entryId: 'ask-queued' }),
      ],
    })

    useThreadByIdStoreV3.getState().reorderAskQueued(1, 0)

    expect(useThreadByIdStoreV3.getState().askFollowupQueue.map((entry) => entry.entryId)).toEqual([
      'ask-sending',
      'ask-queued',
    ])
  })

  it('keeps reorderAskQueued as no-op when active lane is not ask', () => {
    setExecutionQueueRuntimeState({
      askFollowupQueue: [
        makeAskQueueEntry({ entryId: 'ask-a' }),
        makeAskQueueEntry({ entryId: 'ask-b' }),
      ],
    })

    useThreadByIdStoreV3.getState().reorderAskQueued(1, 0)

    expect(useThreadByIdStoreV3.getState().askFollowupQueue.map((entry) => entry.entryId)).toEqual([
      'ask-a',
      'ask-b',
    ])
  })

  it('sendAskQueuedNow sends only a queued head entry', async () => {
    apiMock.startThreadTurnByIdV3.mockResolvedValue({
      threadId: 'ask-thread-1',
      turnId: 'ask-turn-send-now',
      snapshotVersion: 3,
    })
    setAskQueueRuntimeState({
      askFollowupQueue: [
        makeAskQueueEntry({
          entryId: 'ask-head',
          text: 'head queued ask',
          idempotencyKey: 'ask-idem-head',
          status: 'queued',
        }),
      ],
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().sendAskQueuedNow('ask-head')
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'ask-thread-1',
      'head queued ask',
      { idempotencyKey: 'ask-idem-head' },
    )
    expect(useThreadByIdStoreV3.getState().askFollowupQueue).toHaveLength(0)
  })

  it('keeps sendAskQueuedNow as no-op for non-head and requires_confirmation entries', async () => {
    setAskQueueRuntimeState({
      askFollowupQueue: [
        makeAskQueueEntry({ entryId: 'ask-head-queued', text: 'head queued ask' }),
        makeAskQueueEntry({ entryId: 'ask-tail-queued', text: 'tail queued ask' }),
      ],
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().sendAskQueuedNow('ask-tail-queued')
    })
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)

    setAskQueueRuntimeState({
      askFollowupQueue: [
        makeAskQueueEntry({
          entryId: 'ask-blocked-head',
          status: 'requires_confirmation',
          confirmationReason: 'thread_drift',
        }),
      ],
      askQueuePauseReason: 'requires_confirmation',
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().sendAskQueuedNow('ask-blocked-head')
    })
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)
  })

  it('retryAskQueued transitions failed ask head to queued and flushes when eligible', async () => {
    apiMock.startThreadTurnByIdV3.mockResolvedValue({
      threadId: 'ask-thread-1',
      turnId: 'ask-turn-retry',
      snapshotVersion: 3,
    })
    setAskQueueRuntimeState({
      askFollowupQueue: [
        makeAskQueueEntry({
          entryId: 'ask-failed-head',
          text: 'failed ask head',
          idempotencyKey: 'ask-idem-failed-head',
          status: 'failed',
          lastError: 'send failed',
          attemptCount: 1,
        }),
      ],
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().retryAskQueued('ask-failed-head')
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'ask-thread-1',
      'failed ask head',
      { idempotencyKey: 'ask-idem-failed-head' },
    )
    expect(useThreadByIdStoreV3.getState().askFollowupQueue).toHaveLength(0)
  })

  it('enqueues execution follow-up and propagates idempotency key when send window is open', async () => {
    apiMock.startThreadTurnByIdV3.mockResolvedValue({
      threadId: 'thread-1',
      turnId: 'turn-queue-1',
      snapshotVersion: 3,
    })
    setExecutionQueueRuntimeState({
      snapshot: makeSnapshot({
        processingState: 'idle',
        activeTurnId: null,
      }),
      executionQueueWorkflowPhase: 'execution_decision_pending',
      executionQueueCanSendExecutionMessage: true,
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().enqueueFollowup('queued hello')
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    const metadata = apiMock.startThreadTurnByIdV3.mock.calls[0]?.[4] as Record<string, unknown> | undefined
    expect(metadata?.idempotencyKey).toEqual(expect.any(String))
    const state = useThreadByIdStoreV3.getState()
    expect(state.executionFollowupQueue).toHaveLength(0)
    expect(state.snapshot?.activeTurnId).toBe('turn-queue-1')
    expect(state.snapshot?.processingState).toBe('running')
  })

  it('keeps queued follow-up while runtime is blocked or waiting for user input', async () => {
    apiMock.startThreadTurnByIdV3.mockResolvedValue({
      threadId: 'thread-1',
      turnId: 'turn-queue-2',
      snapshotVersion: 3,
    })

    setExecutionQueueRuntimeState({
      snapshot: makeSnapshot({
        processingState: 'running',
        activeTurnId: 'turn-1',
      }),
      executionQueueWorkflowPhase: 'execution_running',
      executionQueueCanSendExecutionMessage: false,
    })
    await act(async () => {
      await useThreadByIdStoreV3.getState().enqueueFollowup('blocked by workflow')
    })
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)
    expect(useThreadByIdStoreV3.getState().executionFollowupQueue).toHaveLength(1)
    expect(useThreadByIdStoreV3.getState().executionQueuePauseReason).toBe('workflow_blocked')

    setExecutionQueueRuntimeState({
      snapshot: makePendingUserInputSnapshot({
        activeTurnId: null,
      }),
      executionQueueWorkflowPhase: 'execution_decision_pending',
      executionQueueCanSendExecutionMessage: true,
    })
    await act(async () => {
      await useThreadByIdStoreV3.getState().enqueueFollowup('blocked by pending input')
    })
    expect(useThreadByIdStoreV3.getState().executionFollowupQueue).toHaveLength(1)
    expect(useThreadByIdStoreV3.getState().executionQueuePauseReason).toBe('runtime_waiting_input')
  })

  it('persists queued follow-ups in localStorage and hydrates without loss on reload', async () => {
    setExecutionQueueRuntimeState({
      snapshot: makeSnapshot({
        processingState: 'running',
        activeTurnId: 'turn-1',
      }),
      executionQueueWorkflowPhase: 'execution_running',
      executionQueueCanSendExecutionMessage: false,
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().enqueueFollowup('first persisted')
      await useThreadByIdStoreV3.getState().enqueueFollowup('second persisted')
    })

    const persistedPayload = globalThis.localStorage.getItem(executionQueueStorageKey())
    expect(persistedPayload).toBeTruthy()

    useThreadByIdStoreV3.getState().disconnectThread()
    apiMock.getThreadSnapshotByIdV3.mockResolvedValue(makeSnapshot())
    await act(async () => {
      await useThreadByIdStoreV3.getState().loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const hydratedQueue = useThreadByIdStoreV3.getState().executionFollowupQueue
    expect(hydratedQueue).toHaveLength(2)
    expect(hydratedQueue.map((entry) => entry.text)).toEqual(['first persisted', 'second persisted'])
    expect(hydratedQueue.every((entry) => entry.status === 'queued')).toBe(true)
  })

  it('enforces single-flight send invariant for queued follow-ups', async () => {
    let resolveFirstSend: (() => void) | null = null
    const firstSendPromise = new Promise<void>((resolve) => {
      resolveFirstSend = resolve
    })
    apiMock.startThreadTurnByIdV3.mockImplementation(async () => {
      await firstSendPromise
      return {
        threadId: 'thread-1',
        turnId: 'turn-single-flight',
        snapshotVersion: 3,
      }
    })

    setExecutionQueueRuntimeState({
      snapshot: makeSnapshot(),
      executionFollowupQueue: [
        makeExecutionQueueEntry({ entryId: 'entry-1', text: 'first queued', idempotencyKey: 'idem-1' }),
        makeExecutionQueueEntry({ entryId: 'entry-2', text: 'second queued', idempotencyKey: 'idem-2' }),
      ],
    })

    const sendFirst = useThreadByIdStoreV3.getState().sendQueuedNow('entry-1')
    const sendSecond = useThreadByIdStoreV3.getState().sendQueuedNow('entry-2')

    await waitFor(() => {
      expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    })
    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'thread-1',
      'first queued',
      { idempotencyKey: 'idem-1' },
    )

    resolveFirstSend?.()
    await act(async () => {
      await Promise.all([sendFirst, sendSecond])
    })
  })

  it('requires confirmation for stale/changed-context queued entries before send', async () => {
    apiMock.startThreadTurnByIdV3.mockResolvedValue({
      threadId: 'thread-1',
      turnId: 'turn-confirmation',
      snapshotVersion: 4,
    })

    setExecutionQueueRuntimeState({
      snapshot: makeSnapshot({
        processingState: 'idle',
        activeTurnId: null,
      }),
      executionQueueLatestExecutionRunId: 'run-new',
      executionFollowupQueue: [
        makeExecutionQueueEntry({
          entryId: 'entry-stale',
          text: 'stale follow-up',
          createdAtMs: Date.now() - 90_500,
          latestExecutionRunId: 'run-old',
        }),
      ],
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().sendQueuedNow('entry-stale')
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(0)
    expect(useThreadByIdStoreV3.getState().executionFollowupQueue[0]?.status).toBe(
      'requires_confirmation',
    )

    await act(async () => {
      await useThreadByIdStoreV3.getState().confirmQueued('entry-stale')
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    expect(useThreadByIdStoreV3.getState().executionFollowupQueue).toHaveLength(0)
  })

  it('supports reorder and remove before automatic flush when send window opens', async () => {
    apiMock.startThreadTurnByIdV3.mockResolvedValue({
      threadId: 'thread-1',
      turnId: 'turn-flush',
      snapshotVersion: 5,
    })
    setExecutionQueueRuntimeState({
      snapshot: makeSnapshot({
        processingState: 'running',
        activeTurnId: 'turn-processing',
      }),
      executionQueueWorkflowPhase: 'execution_running',
      executionQueueCanSendExecutionMessage: false,
    })

    await act(async () => {
      await useThreadByIdStoreV3.getState().enqueueFollowup('first')
      await useThreadByIdStoreV3.getState().enqueueFollowup('second')
      await useThreadByIdStoreV3.getState().enqueueFollowup('third')
    })
    useThreadByIdStoreV3.getState().reorderQueued(2, 0)
    useThreadByIdStoreV3.getState().removeQueued(useThreadByIdStoreV3.getState().executionFollowupQueue[1].entryId)

    useThreadByIdStoreV3.setState({
      snapshot: makeSnapshot({
        processingState: 'idle',
        activeTurnId: null,
      }),
    })
    await act(async () => {
      await useThreadByIdStoreV3.getState().syncExecutionQueueContext({
        workflowPhase: 'execution_decision_pending',
        canSendExecutionMessage: true,
        latestExecutionRunId: 'run-1',
      })
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(1)
    expect(apiMock.startThreadTurnByIdV3.mock.calls.map((call) => call[3])).toEqual(['third'])
    expect(useThreadByIdStoreV3.getState().executionFollowupQueue).toHaveLength(1)

    useThreadByIdStoreV3.setState({
      snapshot: makeSnapshot({
        processingState: 'idle',
        activeTurnId: null,
      }),
    })
    await act(async () => {
      await useThreadByIdStoreV3.getState().syncExecutionQueueContext({
        workflowPhase: 'execution_decision_pending',
        canSendExecutionMessage: true,
        latestExecutionRunId: 'run-1',
      })
    })

    expect(apiMock.startThreadTurnByIdV3).toHaveBeenCalledTimes(2)
    expect(apiMock.startThreadTurnByIdV3.mock.calls.map((call) => call[3])).toEqual(['third', 'second'])
    expect(useThreadByIdStoreV3.getState().executionFollowupQueue).toHaveLength(0)
  })

  it('records render errors through store telemetry', () => {
    useThreadByIdStoreV3.getState().recordRenderError('render failed')

    const state = useThreadByIdStoreV3.getState()
    expect(state.error).toBe('render failed')
    expect(state.telemetry.renderErrorCount).toBe(1)
  })
})
