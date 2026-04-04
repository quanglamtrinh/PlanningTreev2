import { describe, expect, it } from 'vitest'

import type { DiffItemV3, ThreadEventV3, ThreadSnapshotV3 } from '../../src/api/types'
import { applyThreadEventV3 } from '../../src/features/conversation/state/applyThreadEventV3'

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

function makeDiffItem(overrides: Partial<DiffItemV3> = {}): DiffItemV3 {
  return {
    id: 'diff-1',
    kind: 'diff',
    threadId: 'thread-1',
    turnId: 'turn-1',
    sequence: 1,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:00Z',
    status: 'in_progress',
    source: 'upstream',
    tone: 'neutral',
    metadata: {},
    title: 'File changes',
    summaryText: null,
    changes: [
      {
        path: 'src/main.ts',
        kind: 'modify',
        diff: '@@ -1 +1 @@\\n-old\\n+new\\n',
        summary: 'main update',
      },
    ],
    files: [
      {
        path: 'src/main.ts',
        changeType: 'updated',
        patchText: '@@ -1 +1 @@\\n-old\\n+new\\n',
        summary: 'main update',
      },
    ],
    ...overrides,
  }
}

describe('applyThreadEventV3', () => {
  it('applies diff changesAppend and synchronizes files mirror', () => {
    const snapshot = makeSnapshot({
      items: [makeDiffItem()],
    })
    const event: ThreadEventV3 = {
      eventId: 'evt-1',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:01:00Z',
      snapshotVersion: 2,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'diff-1',
        patch: {
          kind: 'diff',
          changesAppend: [
            {
              path: 'src/new.ts',
              kind: 'add',
              diff: '@@ -0,0 +1 @@\\n+export const value = 1\\n',
              summary: 'new file',
            },
          ],
          updatedAt: '2026-04-01T00:01:00Z',
        },
      },
    }

    const next = applyThreadEventV3(snapshot, event)
    const item = next.items[0] as DiffItemV3

    expect(item.changes).toHaveLength(2)
    expect(item.changes[1]).toEqual({
      path: 'src/new.ts',
      kind: 'add',
      diff: '@@ -0,0 +1 @@\\n+export const value = 1\\n',
      summary: 'new file',
    })
    expect(item.files).toEqual([
      {
        path: 'src/main.ts',
        changeType: 'updated',
        patchText: '@@ -1 +1 @@\\n-old\\n+new\\n',
        summary: 'main update',
      },
      {
        path: 'src/new.ts',
        changeType: 'created',
        patchText: '@@ -0,0 +1 @@\\n+export const value = 1\\n',
        summary: 'new file',
      },
    ])
  })

  it('treats changesReplace as authoritative, including explicit empty array', () => {
    const snapshot = makeSnapshot({
      items: [makeDiffItem()],
    })
    const event: ThreadEventV3 = {
      eventId: 'evt-2',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:02:00Z',
      snapshotVersion: 3,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'diff-1',
        patch: {
          kind: 'diff',
          changesReplace: [],
          updatedAt: '2026-04-01T00:02:00Z',
        },
      },
    }

    const next = applyThreadEventV3(snapshot, event)
    const item = next.items[0] as DiffItemV3

    expect(item.changes).toEqual([])
    expect(item.files).toEqual([])
  })

  it('keeps compatibility when patch uses filesAppend only', () => {
    const snapshot = makeSnapshot({
      items: [makeDiffItem({ changes: [] })],
    })
    const event: ThreadEventV3 = {
      eventId: 'evt-3',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:03:00Z',
      snapshotVersion: 4,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'diff-1',
        patch: {
          kind: 'diff',
          filesAppend: [
            {
              path: 'src/legacy.ts',
              changeType: 'deleted',
              patchText: '@@ -1 +0,0 @@\\n-old\\n',
              summary: 'legacy remove',
            },
          ],
          updatedAt: '2026-04-01T00:03:00Z',
        },
      },
    }

    const next = applyThreadEventV3(snapshot, event)
    const item = next.items[0] as DiffItemV3

    expect(item.changes).toEqual([
      {
        path: 'src/main.ts',
        kind: 'modify',
        diff: '@@ -1 +1 @@\\n-old\\n+new\\n',
        summary: 'main update',
      },
      {
        path: 'src/legacy.ts',
        kind: 'delete',
        diff: '@@ -1 +0,0 @@\\n-old\\n',
        summary: 'legacy remove',
      },
    ])
  })
})
