import { act, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getThreadSnapshotByIdV3: vi.fn(),
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
  selectCore,
  selectTransport,
  selectUiControl,
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

describe('threadByIdStoreV3', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useThreadByIdStoreV3.getState().disconnectThread()
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

  it('records render errors through store telemetry', () => {
    useThreadByIdStoreV3.getState().recordRenderError('render failed')

    const state = useThreadByIdStoreV3.getState()
    expect(state.error).toBe('render failed')
    expect(state.telemetry.renderErrorCount).toBe(1)
  })
})
