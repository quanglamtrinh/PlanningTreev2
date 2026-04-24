import { describe, expect, it, vi } from 'vitest'
import type { ConversationItemV3, ThreadSnapshotV3 } from '../../src/api/types'
import { breadcrumbV3SessionUiAdapter } from '../../src/features/conversation/sessionV2Adapters'

function makeBaseSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
  return {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadId: 'thread-1',
    threadRole: 'execution',
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:05Z',
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

function makeMessageItem(
  overrides: Partial<ConversationItemV3> = {},
): ConversationItemV3 {
  return {
    id: 'item-message',
    kind: 'message',
    threadId: 'thread-1',
    turnId: 'turn-1',
    sequence: 1,
    createdAt: '2026-04-01T00:00:01Z',
    updatedAt: '2026-04-01T00:00:01Z',
    status: 'completed',
    source: 'upstream',
    tone: 'neutral',
    metadata: {},
    role: 'assistant',
    text: 'hello',
    format: 'markdown',
    ...overrides,
  }
}

describe('sessionV2Adapters transcript adapter', () => {
  it('groups items by turn id and maps active turn status + orphan turn', () => {
    const snapshot = makeBaseSnapshot({
      activeTurnId: 'turn-2',
      processingState: 'waiting_user_input',
      items: [
        makeMessageItem({
          id: 'msg-user',
          role: 'user',
          turnId: 'turn-1',
          sequence: 1,
          text: 'user question',
        }),
        {
          id: 'tool-run',
          kind: 'tool',
          threadId: 'thread-1',
          turnId: 'turn-2',
          sequence: 2,
          createdAt: '2026-04-01T00:00:02Z',
          updatedAt: '2026-04-01T00:00:03Z',
          status: 'in_progress',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          toolType: 'commandExecution',
          title: 'Run tests',
          toolName: 'command',
          callId: 'call-1',
          argumentsText: null,
          outputText: 'running...',
          outputFiles: [],
          exitCode: null,
        },
        {
          id: 'orphan-status',
          kind: 'status',
          threadId: 'thread-1',
          turnId: null,
          sequence: 3,
          createdAt: '2026-04-01T00:00:04Z',
          updatedAt: '2026-04-01T00:00:04Z',
          status: 'completed',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          code: 'CODE',
          label: 'Status label',
          detail: 'detail',
        },
      ],
    })

    const model = breadcrumbV3SessionUiAdapter.transcript.toTranscriptModel(
      { snapshot },
      {
        threadTab: 'execution',
        projectId: 'project-1',
        nodeId: 'node-1',
        activeThreadId: 'thread-1',
      },
    )

    expect(model.threadId).toBe('thread-1')
    expect(model.turns.map((turn) => turn.id)).toEqual(['turn-1', 'turn-2', '_orphan'])
    expect(model.turns.find((turn) => turn.id === 'turn-1')?.status).toBe('completed')
    expect(model.turns.find((turn) => turn.id === 'turn-2')?.status).toBe('waitingUserInput')
    expect(model.turns.find((turn) => turn.id === '_orphan')?.status).toBe('completed')
    expect(model.itemsByTurn['thread-1:turn-1']?.[0]?.kind).toBe('userMessage')
    expect(model.itemsByTurn['thread-1:turn-2']?.[0]?.kind).toBe('commandExecution')
    expect(model.itemsByTurn['thread-1:_orphan']?.[0]?.kind).toBe('agentMessage')
  })

  it('maps diff/review/userInput items into transcript-friendly session items', () => {
    const snapshot = makeBaseSnapshot({
      items: [
        {
          id: 'diff-1',
          kind: 'diff',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 1,
          createdAt: '2026-04-01T00:00:01Z',
          updatedAt: '2026-04-01T00:00:01Z',
          status: 'completed',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          title: 'Diff',
          summaryText: 'Changed files',
          changes: [],
          files: [
            {
              path: 'src/a.ts',
              changeType: 'updated',
              summary: 'updated',
              patchText: '@@',
            },
          ],
        },
        {
          id: 'review-1',
          kind: 'review',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 2,
          createdAt: '2026-04-01T00:00:02Z',
          updatedAt: '2026-04-01T00:00:02Z',
          status: 'completed',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          title: 'Review',
          text: 'Looks good',
          disposition: 'approved',
        },
        {
          id: 'user-input-1',
          kind: 'userInput',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 3,
          createdAt: '2026-04-01T00:00:03Z',
          updatedAt: '2026-04-01T00:00:03Z',
          status: 'requested',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          requestId: 'req-1',
          title: 'Need input',
          questions: [],
          answers: [],
          requestedAt: '2026-04-01T00:00:03Z',
          resolvedAt: null,
        },
      ],
    })

    const model = breadcrumbV3SessionUiAdapter.transcript.toTranscriptModel(
      { snapshot },
      {
        threadTab: 'execution',
        projectId: 'project-1',
        nodeId: 'node-1',
        activeThreadId: 'thread-1',
      },
    )
    const turnItems = model.itemsByTurn['thread-1:turn-1'] ?? []

    expect(turnItems[0]?.kind).toBe('fileChange')
    expect(turnItems[0]?.payload.type).toBe('fileChange')
    expect(turnItems[1]?.kind).toBe('agentMessage')
    expect(turnItems[1]?.payload.text).toContain('Looks good')
    expect(turnItems[2]?.kind).toBe('userInput')
    expect(turnItems[2]?.status).toBe('inProgress')
  })
})

describe('sessionV2Adapters composer adapter', () => {
  it('serializes input payload and forwards direct submit text', async () => {
    const submitText = vi.fn().mockResolvedValue(undefined)
    const model = breadcrumbV3SessionUiAdapter.composer.toComposerModel(
      {
        composerState: {
          snapshot: makeBaseSnapshot(),
          isLoading: false,
          isSending: false,
          isActiveTurn: false,
          earlyResponse: {
            phase: 'idle',
            pendingSinceMs: null,
          },
        },
        submitText,
        currentCwd: 'C:/workspace/project-1',
        disabled: false,
      },
      {
        threadTab: 'execution',
        projectId: 'project-1',
        nodeId: 'node-1',
        activeThreadId: 'thread-1',
      },
    )

    await model.onSubmit({
      input: [
        { type: 'text', text: 'fix bug' },
        { type: 'image', url: 'https://example.com/img.png' },
        { type: 'localImage', path: 'C:/tmp/a.png' },
      ],
      text: 'fallback text',
      requestedPolicy: { accessMode: 'full-access' },
    })

    expect(model.isTurnRunning).toBe(false)
    expect(submitText).toHaveBeenCalledWith(
      'fix bug\n[Image] https://example.com/img.png\n[Local image] C:/tmp/a.png',
    )
  })
})

describe('sessionV2Adapters pending request adapter', () => {
  it('maps pending request from V3 snapshot and converts overlay result to user input answers', () => {
    const snapshot = makeBaseSnapshot({
      threadId: 'ask-thread-1',
      threadRole: 'ask_planning',
      items: [
        {
          id: 'item-user-input-1',
          kind: 'userInput',
          threadId: 'ask-thread-1',
          turnId: 'turn-1',
          sequence: 1,
          createdAt: '2026-04-01T00:00:01Z',
          updatedAt: '2026-04-01T00:00:01Z',
          status: 'requested',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          requestId: 'req-1',
          title: 'Need confirmation',
          questions: [
            {
              id: 'q-1',
              header: null,
              prompt: 'Choose option',
              inputType: 'single_select',
              options: [{ label: 'Option A', description: 'recommended' }],
            },
          ],
          answers: [],
          requestedAt: '2026-04-01T00:00:01Z',
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
            itemId: 'item-user-input-1',
            threadId: 'ask-thread-1',
            turnId: 'turn-1',
            status: 'requested',
            createdAt: '2026-04-01T00:00:01Z',
            submittedAt: null,
            resolvedAt: null,
            answers: [],
          },
        ],
      },
    })

    const request = breadcrumbV3SessionUiAdapter.pendingRequest.toPendingRequest(
      { snapshot },
      {
        threadTab: 'ask',
        projectId: 'project-1',
        nodeId: 'node-1',
        activeThreadId: 'ask-thread-1',
      },
    )
    expect(request).not.toBeNull()
    expect(request?.method).toBe('item/tool/requestUserInput')
    expect(request?.payload.questions).toEqual([
      {
        id: 'q-1',
        question: 'Choose option',
        options: [{ label: 'Option A', description: 'recommended', value: 'Option A' }],
      },
    ])

    const answers = breadcrumbV3SessionUiAdapter.pendingRequest.toUserInputAnswers(
      request!,
      {
        answers: [
          { id: 'q-1', selectedOption: 'Option A', notes: '', status: 'answered' },
          { id: 'q-2', selectedOption: '', notes: 'freeform', status: 'answered' },
        ],
      },
    )
    expect(answers).toEqual([
      {
        questionId: 'q-1',
        value: 'Option A',
        label: 'Option A',
      },
      {
        questionId: 'q-2',
        value: 'freeform',
        label: null,
      },
    ])
  })
})
