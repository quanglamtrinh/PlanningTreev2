import { describe, expect, it } from 'vitest'

import type {
  ConversationMessageItemV3,
  DiffItemV3,
  ThreadEventV3,
  ThreadSnapshotV3,
  UserInputAnswerV3,
  UserInputItemV3,
} from '../../src/api/types'
import {
  applyOptimisticUserInputSubmissionV3,
  applyThreadEventV3,
  classifyThreadEventOperationV3,
} from '../../src/features/conversation/state/applyThreadEventV3'

function makeSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
  return {
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

function makeMessageItem(overrides: Partial<ConversationMessageItemV3> = {}): ConversationMessageItemV3 {
  return {
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
    text: 'Hello',
    format: 'markdown',
    ...overrides,
  }
}

function makeUserInputItem(overrides: Partial<UserInputItemV3> = {}): UserInputItemV3 {
  return {
    id: 'input-1',
    kind: 'userInput',
    threadId: 'thread-1',
    turnId: 'turn-1',
    sequence: 3,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:00Z',
    status: 'requested',
    source: 'upstream',
    tone: 'info',
    metadata: {},
    requestId: 'req-1',
    title: 'Need answer',
    questions: [],
    answers: [],
    requestedAt: '2026-04-01T00:00:00Z',
    resolvedAt: null,
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
    const legacyItem = makeDiffItem({ changes: [] })
    delete (legacyItem as { changes?: unknown }).changes
    const snapshot = makeSnapshot({
      items: [legacyItem as DiffItemV3],
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

  it('prefers canonical changesReplace over filesReplace when both are present', () => {
    const snapshot = makeSnapshot({
      items: [makeDiffItem()],
    })
    const event: ThreadEventV3 = {
      eventId: 'evt-4',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:04:00Z',
      snapshotVersion: 5,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'diff-1',
        patch: {
          kind: 'diff',
          changesReplace: [
            {
              path: 'src/canonical.ts',
              kind: 'add',
              diff: '@@ -0,0 +1 @@\\n+export const canonical = true\\n',
              summary: 'canonical',
            },
          ],
          filesReplace: [
            {
              path: 'src/legacy.ts',
              changeType: 'deleted',
              patchText: '@@ -1 +0,0 @@\\n-old\\n',
              summary: 'legacy',
            },
          ],
          updatedAt: '2026-04-01T00:04:00Z',
        },
      },
    }

    const next = applyThreadEventV3(snapshot, event)
    const item = next.items[0] as DiffItemV3

    expect(item.changes).toEqual([
      {
        path: 'src/canonical.ts',
        kind: 'add',
        diff: '@@ -0,0 +1 @@\\n+export const canonical = true\\n',
        summary: 'canonical',
      },
    ])
    expect(item.files).toEqual([
      {
        path: 'src/canonical.ts',
        changeType: 'created',
        patchText: '@@ -0,0 +1 @@\\n+export const canonical = true\\n',
        summary: 'canonical',
      },
    ])
  })

  it('does not rebuild canonical changes from legacy files when current changes is explicitly empty', () => {
    const snapshot = makeSnapshot({
      items: [
        makeDiffItem({
          changes: [],
          files: [
            {
              path: 'src/stale.ts',
              changeType: 'updated',
              patchText: '@@ -1 +1 @@\\n-old\\n+stale\\n',
              summary: 'stale',
            },
          ],
        }),
      ],
    })
    const event: ThreadEventV3 = {
      eventId: 'evt-5',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:05:00Z',
      snapshotVersion: 6,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'diff-1',
        patch: {
          kind: 'diff',
          changesAppend: [
            {
              path: 'src/new.ts',
              kind: 'add',
              diff: '@@ -0,0 +1 @@\\n+export const value = 2\\n',
              summary: 'new file',
            },
          ],
          updatedAt: '2026-04-01T00:05:00Z',
        },
      },
    }

    const next = applyThreadEventV3(snapshot, event)
    const item = next.items[0] as DiffItemV3

    expect(item.changes).toEqual([
      {
        path: 'src/new.ts',
        kind: 'add',
        diff: '@@ -0,0 +1 @@\\n+export const value = 2\\n',
        summary: 'new file',
      },
    ])
    expect(item.files).toEqual([
      {
        path: 'src/new.ts',
        changeType: 'created',
        patchText: '@@ -0,0 +1 @@\\n+export const value = 2\\n',
        summary: 'new file',
      },
    ])
  })

  it('classifies operations as insert, reorder, patch-content, and patch-meta', () => {
    const snapshot = makeSnapshot({
      items: [makeMessageItem()],
    })
    const insertEvent: ThreadEventV3 = {
      eventId: 'evt-op-1',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:05:30Z',
      snapshotVersion: 6,
      type: 'conversation.item.upsert.v3',
      payload: {
        item: makeMessageItem({
          id: 'msg-2',
          sequence: 2,
          createdAt: '2026-04-01T00:05:30Z',
          updatedAt: '2026-04-01T00:05:30Z',
          text: 'Insert',
        }),
      },
    }
    const reorderEvent: ThreadEventV3 = {
      ...insertEvent,
      eventId: 'evt-op-2',
      type: 'conversation.item.upsert.v3',
      payload: {
        item: makeMessageItem({
          id: 'msg-1',
          sequence: 99,
          createdAt: '2026-04-01T00:05:31Z',
          updatedAt: '2026-04-01T00:05:31Z',
        }),
      },
    }
    const patchContentEvent: ThreadEventV3 = {
      eventId: 'evt-op-3',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:05:32Z',
      snapshotVersion: 7,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'msg-1',
        patch: {
          kind: 'message',
          textAppend: ' delta',
          updatedAt: '2026-04-01T00:05:32Z',
        },
      },
    }
    const patchMetaEvent: ThreadEventV3 = {
      ...patchContentEvent,
      eventId: 'evt-op-4',
      payload: {
        itemId: 'msg-1',
        patch: {
          kind: 'message',
          status: 'completed',
          updatedAt: '2026-04-01T00:05:33Z',
        },
      },
    }

    expect(classifyThreadEventOperationV3(snapshot, insertEvent)).toBe('insert')
    expect(classifyThreadEventOperationV3(snapshot, reorderEvent)).toBe('reorder')
    expect(classifyThreadEventOperationV3(snapshot, patchContentEvent)).toBe('patch-content')
    expect(classifyThreadEventOperationV3(snapshot, patchMetaEvent)).toBe('patch-meta')
  })

  it('does not trigger global reorder for patch-only events', () => {
    const later = makeMessageItem({
      id: 'msg-later',
      sequence: 2,
      createdAt: '2026-04-01T00:02:00Z',
      updatedAt: '2026-04-01T00:02:00Z',
      text: 'Later',
    })
    const earlier = makeMessageItem({
      id: 'msg-earlier',
      sequence: 1,
      createdAt: '2026-04-01T00:01:00Z',
      updatedAt: '2026-04-01T00:01:00Z',
      text: 'Earlier',
    })
    const snapshot = makeSnapshot({
      items: [later, earlier],
    })
    const event: ThreadEventV3 = {
      eventId: 'evt-order-1',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:06:00Z',
      snapshotVersion: 8,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'msg-later',
        patch: {
          kind: 'message',
          textAppend: ' patched',
          updatedAt: '2026-04-01T00:06:00Z',
        },
      },
    }

    const next = applyThreadEventV3(snapshot, event)
    expect(next.items.map((item) => item.id)).toEqual(['msg-later', 'msg-earlier'])
  })

  it('preserves structural sharing for unchanged branches on patch', () => {
    const messageA = makeMessageItem({
      id: 'msg-a',
      sequence: 1,
      createdAt: '2026-04-01T00:01:00Z',
      updatedAt: '2026-04-01T00:01:00Z',
      text: 'A',
    })
    const messageB = makeMessageItem({
      id: 'msg-b',
      sequence: 2,
      createdAt: '2026-04-01T00:02:00Z',
      updatedAt: '2026-04-01T00:02:00Z',
      text: 'B',
    })
    const snapshot = makeSnapshot({
      items: [messageA, messageB],
    })
    const event: ThreadEventV3 = {
      eventId: 'evt-share-1',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:07:00Z',
      snapshotVersion: 9,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'msg-a',
        patch: {
          kind: 'message',
          textAppend: ' +',
          updatedAt: '2026-04-01T00:07:00Z',
        },
      },
    }

    const next = applyThreadEventV3(snapshot, event)
    expect(next.items).not.toBe(snapshot.items)
    expect(next.items[1]).toBe(snapshot.items[1])
    expect(next.uiSignals).toBe(snapshot.uiSignals)
  })

  it('keeps items identity for lifecycle-only events', () => {
    const snapshot = makeSnapshot({
      items: [makeMessageItem()],
    })
    const event: ThreadEventV3 = {
      eventId: 'evt-life-1',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:07:10Z',
      snapshotVersion: 10,
      type: 'thread.lifecycle.v3',
      payload: {
        activeTurnId: 'turn-10',
        processingState: 'running',
        state: 'turn_started',
        detail: null,
      },
    }

    const next = applyThreadEventV3(snapshot, event)
    expect(next.items).toBe(snapshot.items)
    expect(next.uiSignals).toBe(snapshot.uiSignals)
  })

  it('applies optimistic user-input submission via normalized helper while preserving order', () => {
    const answers: UserInputAnswerV3[] = [{ questionId: 'q1', value: 'yes', label: 'Yes' }]
    const message = makeMessageItem({
      id: 'msg-keep',
      sequence: 1,
      createdAt: '2026-04-01T00:00:10Z',
      updatedAt: '2026-04-01T00:00:10Z',
    })
    const userInput = makeUserInputItem({
      id: 'input-1',
      sequence: 3,
      createdAt: '2026-04-01T00:00:20Z',
      updatedAt: '2026-04-01T00:00:20Z',
      requestId: 'req-1',
    })
    const snapshot = makeSnapshot({
      items: [message, userInput],
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
            createdAt: '2026-04-01T00:00:20Z',
            submittedAt: null,
            resolvedAt: null,
            answers: [],
          },
        ],
      },
    })

    const next = applyOptimisticUserInputSubmissionV3(
      snapshot,
      'req-1',
      answers,
      '2026-04-01T00:09:00Z',
    )

    expect(next.items.map((item) => item.id)).toEqual(['msg-keep', 'input-1'])
    expect(next.items[0]).toBe(snapshot.items[0])
    expect((next.items[1] as UserInputItemV3).status).toBe('answer_submitted')
    expect((next.items[1] as UserInputItemV3).answers).toEqual(answers)
    expect(next.uiSignals.activeUserInputRequests[0].status).toBe('answer_submitted')
    expect(next.uiSignals.activeUserInputRequests[0].answers).toEqual(answers)
  })

  it('uses fast append path for message text patches when guards pass', () => {
    const snapshot = makeSnapshot({
      items: [makeMessageItem()],
    })
    const event: ThreadEventV3 = {
      eventId: 'evt-fast-1',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:06:00Z',
      snapshotVersion: 7,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'msg-1',
        patch: {
          kind: 'message',
          textAppend: ' world',
          updatedAt: '2026-04-01T00:06:00Z',
        },
      },
    }

    const diagnostics = { fastAppendUsed: false, fastAppendFallback: false }
    const next = applyThreadEventV3(snapshot, event, diagnostics)

    expect((next.items[0] as ConversationMessageItemV3).text).toBe('Hello world')
    expect(next.items).toHaveLength(1)
    expect(diagnostics.fastAppendUsed).toBe(true)
    expect(diagnostics.fastAppendFallback).toBe(false)
  })

  it('falls back from fast append when patch shape is not append-safe', () => {
    const snapshot = makeSnapshot({
      items: [makeMessageItem()],
    })
    const event = {
      eventId: 'evt-fast-2',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:07:00Z',
      snapshotVersion: 8,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'msg-1',
        patch: {
          kind: 'message',
          textAppend: ' fallback',
          updatedAt: '2026-04-01T00:07:00Z',
          extraShape: 'force-generic',
        },
      },
    } as unknown as ThreadEventV3

    const diagnostics = { fastAppendUsed: false, fastAppendFallback: false }
    const next = applyThreadEventV3(snapshot, event, diagnostics)

    expect((next.items[0] as ConversationMessageItemV3).text).toBe('Hello fallback')
    expect(diagnostics.fastAppendUsed).toBe(false)
    expect(diagnostics.fastAppendFallback).toBe(true)
  })

  it('keeps fast-path parity with generic patch result for equivalent message append semantics', () => {
    const snapshot = makeSnapshot({
      items: [makeMessageItem()],
    })
    const fastEvent: ThreadEventV3 = {
      eventId: 'evt-fast-3a',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'execution',
      occurredAt: '2026-04-01T00:08:00Z',
      snapshotVersion: 9,
      type: 'conversation.item.patch.v3',
      payload: {
        itemId: 'msg-1',
        patch: {
          kind: 'message',
          textAppend: ' parity',
          status: 'completed',
          updatedAt: '2026-04-01T00:08:00Z',
        },
      },
    }
    const genericEvent = {
      ...fastEvent,
      eventId: 'evt-fast-3b',
      payload: {
        ...fastEvent.payload,
        patch: {
          ...fastEvent.payload.patch,
          extraShape: 'force-generic',
        },
      },
    } as unknown as ThreadEventV3

    const fastDiagnostics = { fastAppendUsed: false, fastAppendFallback: false }
    const genericDiagnostics = { fastAppendUsed: false, fastAppendFallback: false }
    const fastResult = applyThreadEventV3(snapshot, fastEvent, fastDiagnostics)
    const genericResult = applyThreadEventV3(snapshot, genericEvent, genericDiagnostics)

    expect(fastResult).toEqual(genericResult)
    expect(fastDiagnostics.fastAppendUsed).toBe(true)
    expect(genericDiagnostics.fastAppendFallback).toBe(true)
  })
})
