import { act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getThreadSnapshotByIdV2: vi.fn(),
    startThreadTurnV2: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
  appendAuthToken: (url: string) => url,
  buildThreadByIdEventsUrlV2: (
    projectId: string,
    nodeId: string,
    threadId: string,
    afterSnapshotVersion?: number | null,
  ) =>
    afterSnapshotVersion == null
      ? `/v2/projects/${projectId}/threads/by-id/${threadId}/events?node_id=${nodeId}`
      : `/v2/projects/${projectId}/threads/by-id/${threadId}/events?node_id=${nodeId}&after_snapshot_version=${afterSnapshotVersion}`,
}))

import type { ThreadSnapshotV2 } from '../../src/api/types'
import { useThreadByIdStoreV2 } from '../../src/features/conversation/state/threadByIdStoreV2'

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

function getEventSourceMock(): EventSourceMockClass {
  return globalThis.EventSource as unknown as EventSourceMockClass
}

function makeSnapshot(overrides: Partial<ThreadSnapshotV2> = {}): ThreadSnapshotV2 {
  return {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadRole: 'execution',
    threadId: 'thread-1',
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
      lineageRootThreadId: 'thread-1',
    },
    items: [],
    pendingRequests: [],
    ...overrides,
  }
}

function makeAuditSnapshot(overrides: Partial<ThreadSnapshotV2> = {}): ThreadSnapshotV2 {
  return makeSnapshot({
    threadRole: 'audit',
    threadId: 'review-thread-1',
    lineage: {
      forkedFromThreadId: 'exec-thread-1',
      forkedFromNodeId: 'node-1',
      forkedFromRole: 'execution',
      forkReason: 'execution_bootstrap',
      lineageRootThreadId: 'exec-thread-1',
    },
    ...overrides,
  })
}

describe('threadByIdStoreV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useThreadByIdStoreV2.getState().disconnectThread()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('keeps an idle snapshot after loadThread resolves', async () => {
    apiMock.getThreadSnapshotByIdV2.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useThreadByIdStoreV2
        .getState()
        .loadThread('project-1', 'node-1', 'thread-1', 'execution')
    })

    const state = useThreadByIdStoreV2.getState()
    const eventSource = getEventSourceMock().instances[0]

    expect(state.snapshot?.threadId).toBe('thread-1')
    expect(state.snapshot?.processingState).toBe('idle')
    expect(state.isLoading).toBe(false)
    expect(state.lastSnapshotVersion).toBe(1)
    expect(eventSource?.url).toContain(
      '/v2/projects/project-1/threads/by-id/thread-1/events?node_id=node-1&after_snapshot_version=1',
    )
  })

  it('keeps an idle review snapshot after loadThread resolves', async () => {
    apiMock.getThreadSnapshotByIdV2.mockResolvedValue(makeAuditSnapshot())

    await act(async () => {
      await useThreadByIdStoreV2
        .getState()
        .loadThread('project-1', 'node-1', 'review-thread-1', 'audit')
    })

    const state = useThreadByIdStoreV2.getState()
    const eventSource = getEventSourceMock().instances[0]

    expect(state.snapshot?.threadId).toBe('review-thread-1')
    expect(state.snapshot?.threadRole).toBe('audit')
    expect(state.snapshot?.processingState).toBe('idle')
    expect(state.isLoading).toBe(false)
    expect(state.lastSnapshotVersion).toBe(1)
    expect(eventSource?.url).toContain(
      '/v2/projects/project-1/threads/by-id/review-thread-1/events?node_id=node-1&after_snapshot_version=1',
    )
  })

  it('applies idle thread.snapshot events without restoring the previous null snapshot', async () => {
    apiMock.getThreadSnapshotByIdV2.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useThreadByIdStoreV2
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
          occurredAt: '2026-03-28T00:01:00Z',
          snapshotVersion: 2,
          type: 'thread.snapshot',
          payload: {
            snapshot: makeSnapshot({
              snapshotVersion: 2,
              updatedAt: '2026-03-28T00:01:00Z',
              items: [
                {
                  id: 'msg-1',
                  kind: 'message',
                  threadId: 'thread-1',
                  turnId: null,
                  sequence: 1,
                  createdAt: '2026-03-28T00:01:00Z',
                  updatedAt: '2026-03-28T00:01:00Z',
                  status: 'completed',
                  source: 'upstream',
                  tone: 'neutral',
                  metadata: {},
                  role: 'assistant',
                  text: 'Hello',
                  format: 'markdown',
                },
              ],
            }),
          },
        }),
      )
    })

    const state = useThreadByIdStoreV2.getState()
    expect(state.snapshot?.snapshotVersion).toBe(2)
    expect(state.snapshot?.items).toHaveLength(1)
    expect(state.lastEventId).toBe('evt-2')
    expect(state.isLoading).toBe(false)
  })

  it('applies idle review thread.snapshot events without restoring the previous null snapshot', async () => {
    apiMock.getThreadSnapshotByIdV2.mockResolvedValue(makeAuditSnapshot())

    await act(async () => {
      await useThreadByIdStoreV2
        .getState()
        .loadThread('project-1', 'node-1', 'review-thread-1', 'audit')
    })

    const eventSource = getEventSourceMock().instances[0]
    eventSource.emitOpen()

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          eventId: 'evt-audit-2',
          channel: 'thread',
          projectId: 'project-1',
          nodeId: 'node-1',
          threadRole: 'audit',
          occurredAt: '2026-03-28T00:01:00Z',
          snapshotVersion: 2,
          type: 'thread.snapshot',
          payload: {
            snapshot: makeAuditSnapshot({
              snapshotVersion: 2,
              updatedAt: '2026-03-28T00:01:00Z',
              items: [
                {
                  id: 'audit-msg-1',
                  kind: 'message',
                  threadId: 'review-thread-1',
                  turnId: null,
                  sequence: 1,
                  createdAt: '2026-03-28T00:01:00Z',
                  updatedAt: '2026-03-28T00:01:00Z',
                  status: 'completed',
                  source: 'upstream',
                  tone: 'neutral',
                  metadata: {},
                  role: 'assistant',
                  text: 'Review complete',
                  format: 'markdown',
                },
              ],
            }),
          },
        }),
      )
    })

    const state = useThreadByIdStoreV2.getState()
    expect(state.snapshot?.threadId).toBe('review-thread-1')
    expect(state.snapshot?.threadRole).toBe('audit')
    expect(state.snapshot?.snapshotVersion).toBe(2)
    expect(state.snapshot?.items).toHaveLength(1)
    expect(state.lastEventId).toBe('evt-audit-2')
    expect(state.isLoading).toBe(false)
  })
})
