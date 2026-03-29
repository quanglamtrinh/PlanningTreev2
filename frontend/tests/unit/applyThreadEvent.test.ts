import { describe, expect, it } from 'vitest'

import type {
  ConversationItemPatchEventV2,
  PendingUserInputRequest,
  ThreadEventV2,
  ThreadSnapshotV2,
  ToolItem,
  UserInputItem,
} from '../../src/api/types'
import { applyThreadEvent, ThreadEventApplyError } from '../../src/features/conversation/state/applyThreadEvent'

function makeSnapshot(overrides: Partial<ThreadSnapshotV2> = {}): ThreadSnapshotV2 {
  return {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadRole: 'ask_planning',
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

describe('applyThreadEvent', () => {
  it('replaces the authoritative snapshot on thread.snapshot', () => {
    const nextSnapshot = makeSnapshot({ snapshotVersion: 4 })
    const event: ThreadEventV2 = {
      eventId: 'evt-1',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'ask_planning',
      occurredAt: '2026-03-28T00:01:00Z',
      snapshotVersion: 4,
      type: 'thread.snapshot',
      payload: { snapshot: nextSnapshot },
    }

    expect(applyThreadEvent(null, event)).toEqual(nextSnapshot)
  })

  it('applies tool append patches and lets outputFilesReplace overwrite preview entries', () => {
    const toolItem: ToolItem = {
      id: 'tool-1',
      kind: 'tool',
      threadId: 'thread-1',
      turnId: 'turn-1',
      sequence: 1,
      createdAt: '2026-03-28T00:00:00Z',
      updatedAt: '2026-03-28T00:00:00Z',
      status: 'in_progress',
      source: 'upstream',
      tone: 'neutral',
      metadata: {},
      toolType: 'fileChange',
      title: 'Apply files',
      toolName: 'apply_patch',
      callId: 'call-1',
      argumentsText: null,
      outputText: '',
      outputFiles: [],
      exitCode: null,
    }
    const snapshot = makeSnapshot({ items: [toolItem] })
    const previewPatch: ConversationItemPatchEventV2 = {
      eventId: 'evt-2',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'ask_planning',
      occurredAt: '2026-03-28T00:01:00Z',
      snapshotVersion: 2,
      type: 'conversation.item.patch',
      payload: {
        itemId: 'tool-1',
        patch: {
          kind: 'tool',
          outputTextAppend: 'preview',
          outputFilesAppend: [{ path: 'a.ts', changeType: 'created', summary: 'preview' }],
          updatedAt: '2026-03-28T00:01:00Z',
        },
      },
    }
    const finalPatch: ConversationItemPatchEventV2 = {
      ...previewPatch,
      eventId: 'evt-3',
      snapshotVersion: 3,
      payload: {
        itemId: 'tool-1',
        patch: {
          kind: 'tool',
          outputFilesReplace: [{ path: 'b.ts', changeType: 'updated', summary: 'final' }],
          status: 'completed',
          updatedAt: '2026-03-28T00:02:00Z',
        },
      },
    }

    const previewSnapshot = applyThreadEvent(snapshot, previewPatch)
    const finalSnapshot = applyThreadEvent(previewSnapshot, finalPatch)
    const finalItem = finalSnapshot.items[0] as ToolItem

    expect(finalItem.outputText).toBe('preview')
    expect(finalItem.outputFiles).toEqual([{ path: 'b.ts', changeType: 'updated', summary: 'final' }])
    expect(finalItem.status).toBe('completed')
  })

  it('preserves stdin markers in appended command output', () => {
    const toolItem: ToolItem = {
      id: 'tool-stdin-1',
      kind: 'tool',
      threadId: 'thread-1',
      turnId: 'turn-1',
      sequence: 1,
      createdAt: '2026-03-28T00:00:00Z',
      updatedAt: '2026-03-28T00:00:00Z',
      status: 'in_progress',
      source: 'upstream',
      tone: 'neutral',
      metadata: {},
      toolType: 'commandExecution',
      title: 'Run command',
      toolName: 'powershell',
      callId: 'call-1',
      argumentsText: null,
      outputText: 'stdout line\n',
      outputFiles: [],
      exitCode: null,
    }

    const nextSnapshot = applyThreadEvent(makeSnapshot({ items: [toolItem] }), {
      eventId: 'evt-stdin',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'ask_planning',
      occurredAt: '2026-03-28T00:02:00Z',
      snapshotVersion: 2,
      type: 'conversation.item.patch',
      payload: {
        itemId: 'tool-stdin-1',
        patch: {
          kind: 'tool',
          outputTextAppend: '[stdin]\ny\n',
          status: 'in_progress',
          updatedAt: '2026-03-28T00:02:00Z',
        },
      },
    })

    expect((nextSnapshot.items[0] as ToolItem).outputText).toBe('stdout line\n[stdin]\ny\n')
  })

  it('updates pending requests from companion user-input events', () => {
    const item: UserInputItem = {
      id: 'input-1',
      kind: 'userInput',
      threadId: 'thread-1',
      turnId: 'turn-1',
      sequence: 3,
      createdAt: '2026-03-28T00:00:00Z',
      updatedAt: '2026-03-28T00:00:00Z',
      status: 'requested',
      source: 'upstream',
      tone: 'neutral',
      metadata: {},
      requestId: 'request-1',
      title: 'Need input',
      questions: [],
      answers: [],
      requestedAt: '2026-03-28T00:00:00Z',
      resolvedAt: null,
    }
    const pendingRequest: PendingUserInputRequest = {
      requestId: 'request-1',
      itemId: 'input-1',
      threadId: 'thread-1',
      turnId: 'turn-1',
      status: 'requested',
      createdAt: '2026-03-28T00:00:00Z',
      submittedAt: null,
      resolvedAt: null,
      answers: [],
    }
    const requestedSnapshot = applyThreadEvent(
      makeSnapshot({ items: [item] }),
      {
        eventId: 'evt-4',
        channel: 'thread',
        projectId: 'project-1',
        nodeId: 'node-1',
        threadRole: 'ask_planning',
        occurredAt: '2026-03-28T00:01:00Z',
        snapshotVersion: 2,
        type: 'conversation.request.user_input.requested',
        payload: {
          requestId: 'request-1',
          itemId: 'input-1',
          item,
          pendingRequest,
        },
      },
    )

    const resolvedSnapshot = applyThreadEvent(requestedSnapshot, {
      eventId: 'evt-5',
      channel: 'thread',
      projectId: 'project-1',
      nodeId: 'node-1',
      threadRole: 'ask_planning',
      occurredAt: '2026-03-28T00:02:00Z',
      snapshotVersion: 3,
      type: 'conversation.request.user_input.resolved',
      payload: {
        requestId: 'request-1',
        itemId: 'input-1',
        status: 'answered',
        answers: [{ questionId: 'q1', value: 'yes', label: 'Yes' }],
        resolvedAt: '2026-03-28T00:02:00Z',
      },
    })

    expect(resolvedSnapshot.pendingRequests).toEqual([
      expect.objectContaining({
        requestId: 'request-1',
        status: 'answered',
        answers: [{ questionId: 'q1', value: 'yes', label: 'Yes' }],
      }),
    ])
  })

  it('throws a mismatch error when a patch targets a missing item', () => {
    expect(() =>
      applyThreadEvent(makeSnapshot(), {
        eventId: 'evt-6',
        channel: 'thread',
        projectId: 'project-1',
        nodeId: 'node-1',
        threadRole: 'ask_planning',
        occurredAt: '2026-03-28T00:01:00Z',
        snapshotVersion: 2,
        type: 'conversation.item.patch',
        payload: {
          itemId: 'missing',
          patch: {
            kind: 'message',
            textAppend: 'hello',
            updatedAt: '2026-03-28T00:01:00Z',
          },
        },
      })
    ).toThrowError(ThreadEventApplyError)
  })
})
