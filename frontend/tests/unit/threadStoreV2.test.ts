import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getThreadSnapshotV2: vi.fn(),
    startThreadTurnV2: vi.fn(),
    resolveThreadUserInputV2: vi.fn(),
    resetThreadV2: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
  appendAuthToken: (url: string) => url,
  buildThreadEventsUrlV2: (
    projectId: string,
    nodeId: string,
    threadRole: string,
    afterSnapshotVersion?: number | null,
  ) =>
    afterSnapshotVersion == null
      ? `/v2/projects/${projectId}/nodes/${nodeId}/threads/${threadRole}/events`
      : `/v2/projects/${projectId}/nodes/${nodeId}/threads/${threadRole}/events?after_snapshot_version=${afterSnapshotVersion}`,
}))

import type { ThreadSnapshotV2 } from '../../src/api/types'
import { useConversationThreadStoreV2 } from '../../src/features/conversation/state/threadStoreV2'

type EventSourceMockInstance = {
  url: string
  readyState: number
  emitOpen: () => void
  emitMessage: (data: string) => void
  emitError: () => void
  close: () => void
}

type EventSourceMockClass = {
  instances: EventSourceMockInstance[]
}

function makeSnapshot(nodeId = 'node-1', overrides: Partial<ThreadSnapshotV2> = {}): ThreadSnapshotV2 {
  return {
    projectId: 'project-1',
    nodeId,
    threadRole: 'ask_planning',
    threadId: `thread-${nodeId}`,
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-03-28T00:00:00Z',
    updatedAt: '2026-03-28T00:00:00Z',
    lineage: {
      forkedFromThreadId: null,
      forkedFromNodeId: null,
      forkedFromRole: null,
      forkReason: null,
      lineageRootThreadId: `thread-${nodeId}`,
    },
    items: [],
    pendingRequests: [],
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('threadStoreV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationThreadStoreV2.getState().disconnectThread()
  })

  it('loads a V2 snapshot and opens a V2 thread stream', async () => {
    apiMock.getThreadSnapshotV2.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useConversationThreadStoreV2.getState().loadThread('project-1', 'node-1', 'ask_planning')
    })

    const state = useConversationThreadStoreV2.getState()
    const EventSourceMock = globalThis.EventSource as unknown as EventSourceMockClass

    expect(state.snapshot?.threadId).toBe('thread-node-1')
    expect(state.activeNodeId).toBe('node-1')
    expect(apiMock.getThreadSnapshotV2).toHaveBeenCalledWith('project-1', 'node-1', 'ask_planning')
    expect(EventSourceMock.instances[0]?.url).toContain('/v2/projects/project-1/nodes/node-1/threads/ask_planning/events?after_snapshot_version=1')
  })

  it('ignores stale load responses after the target changes', async () => {
    const first = deferred<ThreadSnapshotV2>()
    apiMock.getThreadSnapshotV2
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValueOnce(makeSnapshot('node-2'))

    await act(async () => {
      void useConversationThreadStoreV2.getState().loadThread('project-1', 'node-1', 'ask_planning')
      await useConversationThreadStoreV2.getState().loadThread('project-1', 'node-2', 'ask_planning')
    })

    await act(async () => {
      first.resolve(makeSnapshot('node-1'))
      await first.promise
    })

    const state = useConversationThreadStoreV2.getState()
    expect(state.activeNodeId).toBe('node-2')
    expect(state.snapshot?.nodeId).toBe('node-2')
  })

  it('uses canonical createdItems returned by startTurnV2', async () => {
    apiMock.getThreadSnapshotV2.mockResolvedValue(makeSnapshot())
    apiMock.startThreadTurnV2.mockResolvedValue({
      accepted: true,
      threadId: 'thread-node-1',
      turnId: 'turn-1',
      snapshotVersion: 2,
      createdItems: [
        {
          id: 'item-user-1',
          kind: 'message',
          threadId: 'thread-node-1',
          turnId: 'turn-1',
          sequence: 1,
          createdAt: '2026-03-28T00:01:00Z',
          updatedAt: '2026-03-28T00:01:00Z',
          status: 'completed',
          source: 'local',
          tone: 'neutral',
          metadata: {},
          role: 'user',
          text: 'Hello from V2',
          format: 'markdown',
        },
      ],
    })

    await act(async () => {
      await useConversationThreadStoreV2.getState().loadThread('project-1', 'node-1', 'ask_planning')
      await useConversationThreadStoreV2.getState().sendTurn('Hello from V2')
    })

    const state = useConversationThreadStoreV2.getState()
    expect(state.snapshot?.activeTurnId).toBe('turn-1')
    expect(state.snapshot?.processingState).toBe('running')
    expect(state.snapshot?.items).toHaveLength(1)
    expect(state.snapshot?.items[0]).toEqual(
      expect.objectContaining({
        id: 'item-user-1',
        kind: 'message',
      }),
    )
  })
})
