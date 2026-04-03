import { act, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getThreadSnapshotByIdV3: vi.fn(),
    startThreadTurnByIdV3: vi.fn(),
    resolveThreadUserInputByIdV3: vi.fn(),
    planActionByIdV3: vi.fn(),
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
  ) =>
    afterSnapshotVersion == null
      ? `/v3/projects/${projectId}/threads/by-id/${threadId}/events?node_id=${nodeId}`
      : `/v3/projects/${projectId}/threads/by-id/${threadId}/events?node_id=${nodeId}&after_snapshot_version=${afterSnapshotVersion}`,
}))

import type { ThreadSnapshotV3 } from '../../src/api/types'
import { useThreadByIdStoreV3 } from '../../src/features/conversation/state/threadByIdStoreV3'

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
  return {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadId: 'thread-1',
    lane: 'execution',
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
    expect(state.snapshot?.lane).toBe('execution')
    expect(state.lastSnapshotVersion).toBe(1)
    expect(state.telemetry.firstFrameLatencyMs).not.toBeNull()
    expect(state.telemetry.streamReconnectCount).toBe(0)
    expect(state.telemetry.applyErrorCount).toBe(0)
    expect(state.telemetry.forcedSnapshotReloadCount).toBe(0)
    expect(eventSource?.url).toContain(
      '/v3/projects/project-1/threads/by-id/thread-1/events?node_id=node-1&after_snapshot_version=1',
    )
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
          eventId: 'evt-2',
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
    expect(state.lastEventId).toBe('evt-2')
    expect(state.isLoading).toBe(false)
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
          eventId: 'evt-bad',
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

      await act(async () => {
        await useThreadByIdStoreV3.getState().resolveUserInput('req-1', [
          { questionId: 'q1', value: 'yes', label: 'Yes' },
        ])
      })

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

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000)
      })

      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
      expect(useThreadByIdStoreV3.getState().snapshot?.snapshotVersion).toBe(6)
      expect(useThreadByIdStoreV3.getState().telemetry.forcedSnapshotReloadCount).toBe(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('increments reconnect telemetry when stream errors and schedules reload', async () => {
    vi.useFakeTimers()
    try {
      apiMock.getThreadSnapshotByIdV3
        .mockResolvedValueOnce(makeSnapshot())
        .mockResolvedValueOnce(makeSnapshot({ snapshotVersion: 2 }))

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

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1100)
      })

      expect(apiMock.getThreadSnapshotByIdV3).toHaveBeenCalledTimes(2)
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
