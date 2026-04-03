import { act, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getThreadSnapshotByIdV3: vi.fn(),
    startThreadTurnV2: vi.fn(),
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
  })
})
