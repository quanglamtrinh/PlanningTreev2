import { beforeEach, describe, expect, it } from 'vitest'

import type { SessionEventEnvelope, SessionItem, SessionThread, SessionTurn } from '../../src/features/session_v2/contracts'
import {
  selectActiveItemsByTurn,
  selectActiveRunningTurn,
  selectActiveThread,
  selectActiveTranscriptModel,
  selectActiveTurns,
  selectVisibleTranscriptRows,
  selectThreadsSorted,
  useThreadSessionStore,
} from '../../src/features/session_v2/store/threadSessionStore'

function thread(overrides: Partial<SessionThread> & { id: string }): SessionThread {
  return {
    id: overrides.id,
    name: null,
    modelProvider: 'openai',
    cwd: 'C:/repo',
    ephemeral: false,
    archived: false,
    status: { type: 'idle' },
    createdAt: 1,
    updatedAt: 1,
    turns: [],
    ...overrides,
  }
}

describe('threadSessionStore', () => {
  beforeEach(() => {
    useThreadSessionStore.getState().clear()
  })

  it('seeds thread list and sets active thread', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadList([
      {
        id: 'thread-1',
        name: 'Thread 1',
        modelProvider: 'openai',
        cwd: 'C:/repo',
        ephemeral: false,
        archived: false,
        status: { type: 'idle' },
        createdAt: 1,
        updatedAt: 1,
        turns: [],
      },
    ])
    store.setActiveThreadId('thread-1')

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.threadOrder).toEqual(['thread-1'])
    expect(snapshot.activeThreadId).toBe('thread-1')
    expect(snapshot.threadsById['thread-1']?.name).toBe('Thread 1')
  })

  it('prioritizes latest server thread ordering on refresh', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadList([
      {
        id: 'thread-old',
        name: 'Old',
        modelProvider: 'openai',
        cwd: 'C:/repo',
        ephemeral: false,
        archived: false,
        status: { type: 'idle' },
        createdAt: 1,
        updatedAt: 1,
        turns: [],
      },
      {
        id: 'thread-new',
        name: 'New',
        modelProvider: 'openai',
        cwd: 'C:/repo',
        ephemeral: false,
        archived: false,
        status: { type: 'idle' },
        createdAt: 2,
        updatedAt: 2,
        turns: [],
      },
    ])

    store.setThreadList([
      {
        id: 'thread-new',
        name: 'New',
        modelProvider: 'openai',
        cwd: 'C:/repo',
        ephemeral: false,
        archived: false,
        status: { type: 'idle' },
        createdAt: 2,
        updatedAt: 3,
        turns: [],
      },
      {
        id: 'thread-old',
        name: 'Old',
        modelProvider: 'openai',
        cwd: 'C:/repo',
        ephemeral: false,
        archived: false,
        status: { type: 'idle' },
        createdAt: 1,
        updatedAt: 2,
        turns: [],
      },
    ])

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.threadOrder.slice(0, 2)).toEqual(['thread-new', 'thread-old'])
  })

  it('can hydrate a thread without bumping list activity timestamp', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadList([
      thread({ id: 'thread-old', name: 'Old', updatedAt: 10 }),
      thread({ id: 'thread-new', name: 'New', updatedAt: 20 }),
    ])

    store.upsertThread(
      thread({ id: 'thread-old', name: 'Old loaded', status: { type: 'idle' }, updatedAt: 30 }),
      { preserveUpdatedAt: true },
    )

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.threadsById['thread-old']?.name).toBe('Old loaded')
    expect(snapshot.threadsById['thread-old']?.updatedAt).toBe(10)
  })

  it('keeps state identity for idempotent hydrate upserts', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadList([thread({ id: 'thread-1', name: 'Thread 1', updatedAt: 10 })])

    const beforeState = useThreadSessionStore.getState()
    const beforeThread = beforeState.threadsById['thread-1']

    store.upsertThread(
      thread({ id: 'thread-1', name: 'Thread 1', status: { type: 'idle' }, updatedAt: 999 }),
      { preserveUpdatedAt: true },
    )

    const afterState = useThreadSessionStore.getState()
    expect(afterState).toBe(beforeState)
    expect(afterState.threadsById['thread-1']).toBe(beforeThread)
  })

  it('keeps state identity when refresh list payload is unchanged', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadList([thread({ id: 'thread-1', name: 'Thread 1', updatedAt: 10 })])

    const beforeState = useThreadSessionStore.getState()
    const beforeThread = beforeState.threadsById['thread-1']

    store.setThreadList([thread({ id: 'thread-1', name: 'Thread 1', status: { type: 'idle' }, updatedAt: 10 })])

    const afterState = useThreadSessionStore.getState()
    expect(afterState).toBe(beforeState)
    expect(afterState.threadsById['thread-1']).toBe(beforeThread)
  })

  it('keeps state identity when hydrate returns equivalent nested metadata', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadList([
      thread({
        id: 'thread-1',
        name: 'Thread 1',
        updatedAt: 10,
        metadata: {
          workspace: { cwd: 'C:/repo', roots: ['C:/repo'] },
          tags: ['a', 'b'],
        },
      }),
    ])

    const beforeState = useThreadSessionStore.getState()
    const beforeThread = beforeState.threadsById['thread-1']

    store.upsertThread(
      thread({
        id: 'thread-1',
        name: 'Thread 1',
        updatedAt: 999,
        status: { type: 'idle' },
        metadata: {
          workspace: { cwd: 'C:/repo', roots: ['C:/repo'] },
          tags: ['a', 'b'],
        },
      }),
      { preserveUpdatedAt: true },
    )

    const afterState = useThreadSessionStore.getState()
    expect(afterState).toBe(beforeState)
    expect(afterState.threadsById['thread-1']).toBe(beforeThread)
  })

  it('ignores equivalent thread turns payload churn from hydrate', () => {
    const store = useThreadSessionStore.getState()
    const cachedTurns: SessionTurn[] = [
      {
        id: 'turn-1',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 10,
        completedAtMs: 20,
        items: [],
        error: null,
      },
    ]

    store.setThreadList([
      thread({
        id: 'thread-1',
        name: 'Thread 1',
        updatedAt: 10,
        turns: cachedTurns,
      }),
    ])

    const beforeState = useThreadSessionStore.getState()
    const beforeThread = beforeState.threadsById['thread-1']
    const serverTurns: SessionTurn[] = cachedTurns.map((turn) => ({ ...turn, items: [...turn.items] }))

    store.upsertThread(
      thread({
        id: 'thread-1',
        name: 'Thread 1',
        updatedAt: 999,
        status: { type: 'idle' },
        turns: serverTurns,
      }),
      { preserveUpdatedAt: true },
    )

    const afterState = useThreadSessionStore.getState()
    expect(afterState).toBe(beforeState)
    expect(afterState.threadsById['thread-1']).toBe(beforeThread)
    expect(afterState.threadsById['thread-1']?.turns).toBe(cachedTurns)
  })

  it('bumps list activity timestamp only through explicit thread activity', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadList([thread({ id: 'thread-1', updatedAt: 10 })])

    store.markThreadActivity('thread-1', 25)

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.threadsById['thread-1']?.updatedAt).toBe(25)
  })

  it('tracks stream reconnect counters', () => {
    const store = useThreadSessionStore.getState()
    store.markStreamConnected('thread-1')
    store.markStreamReconnect('thread-1')
    store.markStreamReconnect('thread-1')
    store.markStreamDisconnected('thread-1')

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.streamState.connectedByThread['thread-1']).toBe(false)
    expect(snapshot.streamState.reconnectCountByThread['thread-1']).toBe(2)
  })

  it('normalizes hydrated turn items when payload is missing', () => {
    const store = useThreadSessionStore.getState()
    const turns: SessionTurn[] = [
      {
        id: 'turn-1',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 1,
        completedAtMs: 2,
        error: null,
        items: [
          {
            id: 'item-1',
            threadId: 'thread-1',
            turnId: 'turn-1',
            kind: 'agentMessage',
            status: 'completed',
            createdAtMs: 1,
            updatedAtMs: 1,
            payload: undefined as unknown as Record<string, unknown>,
          } as SessionItem,
        ],
      },
    ]

    store.setThreadTurns('thread-1', turns)

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-1']
    expect(items).toHaveLength(1)
    expect(items[0].payload).toEqual({})
  })

  it('deduplicates hydrated turn items by item id', () => {
    const store = useThreadSessionStore.getState()
    const turns: SessionTurn[] = [
      {
        id: 'turn-dup',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 1,
        completedAtMs: 2,
        error: null,
        items: [
          {
            id: 'item-dup',
            threadId: 'thread-1',
            turnId: 'turn-dup',
            kind: 'userMessage',
            status: 'completed',
            createdAtMs: 1,
            updatedAtMs: 1,
            payload: { type: 'userMessage', text: 'same message' },
          } as SessionItem,
          {
            id: 'item-dup',
            threadId: 'thread-1',
            turnId: 'turn-dup',
            kind: 'userMessage',
            status: 'completed',
            createdAtMs: 1,
            updatedAtMs: 2,
            payload: { type: 'userMessage', text: 'same message' },
          } as SessionItem,
        ],
      },
    ]

    store.setThreadTurns('thread-1', turns)

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-dup']
    expect(items).toHaveLength(1)
    expect(items[0].id).toBe('item-dup')
    expect(items[0].payload.text).toBe('same message')
  })

  it('preserves a primed running turn when provider snapshot replace does not include it', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadTurns('thread-1', [
      {
        id: 'turn-running',
        threadId: 'thread-1',
        status: 'inProgress',
        lastCodexStatus: 'inProgress',
        startedAtMs: 10,
        completedAtMs: null,
        items: [],
        error: null,
        metadata: { primedByWorkflowAction: true },
      },
    ])

    store.setThreadTurns(
      'thread-1',
      [
        {
          id: 'turn-history',
          threadId: 'thread-1',
          status: 'completed',
          lastCodexStatus: 'completed',
          startedAtMs: 1,
          completedAtMs: 2,
          items: [],
          error: null,
        },
      ],
      { mode: 'replace' },
    )

    const turns = useThreadSessionStore.getState().turnsByThread['thread-1']
    expect(turns.map((turn) => turn.id)).toEqual(['turn-history', 'turn-running'])
    expect(turns.find((turn) => turn.id === 'turn-running')?.status).toBe('inProgress')
  })

  it('maps Codex ThreadItem shape into payload text for transcript rendering', () => {
    const store = useThreadSessionStore.getState()
    const turns = [
      {
        id: 'turn-2',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 10,
        completedAtMs: 20,
        error: null,
        items: [
          {
            id: 'item-2',
            type: 'agentMessage',
            text: 'Hello from Codex',
            phase: null,
            memoryCitation: null,
          },
        ],
      },
    ] as unknown as SessionTurn[]

    store.setThreadTurns('thread-1', turns)

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-2']
    expect(items).toHaveLength(1)
    expect(items[0].kind).toBe('agentMessage')
    expect(items[0].status).toBe('completed')
    expect(items[0].payload.type).toBe('agentMessage')
    expect(items[0].payload.text).toBe('Hello from Codex')
  })

  it('drops unknown hydrated item kind', () => {
    const store = useThreadSessionStore.getState()
    const turns = [
      {
        id: 'turn-native',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 10,
        completedAtMs: 20,
        error: null,
        items: [
          {
            id: 'item-native',
            kind: 'browserScreenshot',
            status: 'completed',
            imageUrl: 'https://example.test/screenshot.png',
          },
        ],
      },
    ] as unknown as SessionTurn[]

    store.setThreadTurns('thread-1', turns)

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-native']
    expect(items).toHaveLength(0)
  })

  it('retains unknown hydrated workflow context items', () => {
    const store = useThreadSessionStore.getState()
    const turns = [
      {
        id: 'turn-workflow-context',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 10,
        completedAtMs: 20,
        error: null,
        items: [
          {
            id: 'item-context-native',
            kind: 'systemMessage',
            status: 'completed',
            metadata: {
              workflowContext: true,
            },
          },
        ],
      },
    ] as unknown as SessionTurn[]

    store.setThreadTurns('thread-1', turns)

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-workflow-context']
    expect(items).toHaveLength(1)
    expect(items[0].kind).toBe('systemMessage')
    expect(items[0].normalizedKind).toBeNull()
    expect((items[0].payload.metadata as Record<string, unknown>).workflowContext).toBe(true)
  })

  it('infers failed item status from terminal turn when hydrate payload omits status', () => {
    const store = useThreadSessionStore.getState()
    const turns = [
      {
        id: 'turn-failed',
        threadId: 'thread-1',
        status: 'failed',
        lastCodexStatus: 'failed',
        startedAtMs: 10,
        completedAtMs: 20,
        error: null,
        items: [
          {
            id: 'item-failed',
            type: 'agentMessage',
            text: 'partial output',
          },
        ],
      },
    ] as unknown as SessionTurn[]

    store.setThreadTurns('thread-1', turns)

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-failed']
    expect(items).toHaveLength(1)
    expect(items[0].status).toBe('failed')
  })

  it('sorts hydrated turn items chronologically by created timestamp', () => {
    const store = useThreadSessionStore.getState()
    const turns = [
      {
        id: 'turn-order',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 10,
        completedAtMs: 20,
        error: null,
        items: [
          {
            id: 'item-b',
            type: 'agentMessage',
            createdAt: '2026-01-01T00:00:02.000Z',
            text: 'B',
          },
          {
            id: 'item-a',
            type: 'userMessage',
            createdAt: '2026-01-01T00:00:01.000Z',
            text: 'A',
          },
        ],
      },
    ] as unknown as SessionTurn[]

    store.setThreadTurns('thread-1', turns)

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-order']
    expect(items.map((item) => item.id)).toEqual(['item-a', 'item-b'])
  })

  it('stores turns in chronological order when provider returns newest first', () => {
    const store = useThreadSessionStore.getState()
    const turns = [
      {
        id: 'turn-newest',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 30,
        completedAtMs: 35,
        error: null,
        items: [],
      },
      {
        id: 'turn-middle',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 20,
        completedAtMs: 25,
        error: null,
        items: [],
      },
      {
        id: 'turn-oldest',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 10,
        completedAtMs: 15,
        error: null,
        items: [],
      },
    ] as SessionTurn[]

    store.setThreadTurns('thread-1', turns)

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.turnsByThread['thread-1'].map((turn) => turn.id)).toEqual([
      'turn-oldest',
      'turn-middle',
      'turn-newest',
    ])
  })

  it('replaces thread projection on full resync and drops stale turn items', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadTurns('thread-1', [
      {
        id: 'turn-stale',
        threadId: 'thread-1',
        status: 'inProgress',
        lastCodexStatus: 'inProgress',
        startedAtMs: 10,
        completedAtMs: null,
        error: null,
        items: [
          {
            id: 'item-stale',
            threadId: 'thread-1',
            turnId: 'turn-stale',
            kind: 'agentMessage',
            status: 'inProgress',
            createdAtMs: 10,
            updatedAtMs: 10,
            payload: { type: 'agentMessage', text: 'stale' },
          } as SessionItem,
        ],
      },
    ])
    store.setItemsForTurn('thread-2', 'turn-other', [
      {
        id: 'item-other',
        threadId: 'thread-2',
        turnId: 'turn-other',
        kind: 'agentMessage',
        status: 'completed',
        createdAtMs: 1,
        updatedAtMs: 1,
        payload: { type: 'agentMessage', text: 'keep' },
      },
    ])

    store.setThreadTurns(
      'thread-1',
      [
        {
          id: 'turn-fresh',
          threadId: 'thread-1',
          status: 'completed',
          lastCodexStatus: 'completed',
          startedAtMs: 20,
          completedAtMs: 30,
          error: null,
          items: [
            {
              id: 'item-fresh',
              threadId: 'thread-1',
              turnId: 'turn-fresh',
              kind: 'agentMessage',
              status: 'completed',
              createdAtMs: 20,
              updatedAtMs: 30,
              payload: { type: 'agentMessage', text: 'fresh' },
            } as SessionItem,
          ],
        },
      ],
      { mode: 'replace' },
    )

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.turnsByThread['thread-1'].map((turn) => turn.id)).toEqual(['turn-fresh'])
    expect(snapshot.itemsByTurn['thread-1:turn-stale']).toBeUndefined()
    expect(snapshot.itemsByTurn['thread-1:turn-fresh']?.map((item) => item.id)).toEqual(['item-fresh'])
    expect(snapshot.itemsByTurn['thread-2:turn-other']?.map((item) => item.id)).toEqual(['item-other'])
  })

  it('stores hydrated turns without retaining turn item render payloads', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadTurns('thread-1', [
      {
        id: 'turn-1',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 1,
        completedAtMs: 2,
        error: null,
        items: [
          {
            id: 'item-1',
            threadId: 'thread-1',
            turnId: 'turn-1',
            kind: 'userMessage',
            status: 'completed',
            createdAtMs: 1,
            updatedAtMs: 1,
            payload: { type: 'userMessage', text: 'hello' },
          } as SessionItem,
        ],
      },
    ])

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.turnsByThread['thread-1'][0].items).toEqual([])
    expect(snapshot.itemsByTurn['thread-1:turn-1']).toHaveLength(1)
  })

  it('does not duplicate same-id items when live arrives before hydrate', () => {
    const store = useThreadSessionStore.getState()
    store.setItemsForTurn('thread-1', 'turn-1', [
      {
        id: 'item-1',
        threadId: 'thread-1',
        turnId: 'turn-1',
        kind: 'userMessage',
        status: 'inProgress',
        createdAtMs: 1,
        updatedAtMs: 2,
        payload: { type: 'userMessage', text: 'Build it' },
      },
    ])

    store.setThreadTurns('thread-1', [
      {
        id: 'turn-1',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 1,
        completedAtMs: 3,
        error: null,
        items: [
          {
            id: 'item-1',
            threadId: 'thread-1',
            turnId: 'turn-1',
            kind: 'userMessage',
            status: 'completed',
            createdAtMs: 1,
            updatedAtMs: 1,
            payload: { type: 'userMessage', text: 'Build it' },
          } as SessionItem,
        ],
      },
    ])

    const items = useThreadSessionStore.getState().itemsByTurn['thread-1:turn-1']
    expect(items).toHaveLength(1)
    expect(items[0].id).toBe('item-1')
  })

  it('does not duplicate same-id items when hydrate arrives before live', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadTurns('thread-1', [
      {
        id: 'turn-1',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 1,
        completedAtMs: 3,
        error: null,
        items: [
          {
            id: 'thread-1:2',
            threadId: 'thread-1',
            turnId: 'turn-1',
            kind: 'userMessage',
            status: 'completed',
            createdAtMs: 1,
            updatedAtMs: 1,
            payload: { type: 'userMessage', text: 'Build it' },
          } as SessionItem,
        ],
      },
    ])
    store.applyEvent({
      schemaVersion: 1,
      eventId: 'thread-1:2',
      eventSeq: 2,
      tier: 'tier0',
      method: 'user/message',
      threadId: 'thread-1',
      turnId: 'turn-1',
      occurredAtMs: 2,
      replayable: true,
      snapshotVersion: null,
      source: 'journal',
      params: { text: 'Build it' },
    })

    const items = useThreadSessionStore.getState().itemsByTurn['thread-1:turn-1']
    expect(items).toHaveLength(1)
    expect(items[0].payload.text).toBe('Build it')
  })

  it('preserves richer streaming live payload when stale hydrate arrives', () => {
    const store = useThreadSessionStore.getState()
    store.setItemsForTurn('thread-1', 'turn-1', [
      {
        id: 'item-1',
        threadId: 'thread-1',
        turnId: 'turn-1',
        kind: 'agentMessage',
        status: 'inProgress',
        createdAtMs: 1,
        updatedAtMs: 5,
        payload: { type: 'agentMessage', text: 'Hello streaming world' },
      },
    ])

    store.setThreadTurns('thread-1', [
      {
        id: 'turn-1',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 1,
        completedAtMs: 4,
        error: null,
        items: [
          {
            id: 'item-1',
            threadId: 'thread-1',
            turnId: 'turn-1',
            kind: 'agentMessage',
            status: 'completed',
            createdAtMs: 1,
            updatedAtMs: 2,
            payload: { type: 'agentMessage', text: 'Hello' },
          } as SessionItem,
        ],
      },
    ])

    const item = useThreadSessionStore.getState().itemsByTurn['thread-1:turn-1'][0]
    expect(item.status).toBe('inProgress')
    expect(item.payload.text).toBe('Hello streaming world')
  })

  it('replace hydrate merges backend fallback message into live event-id message', () => {
    const store = useThreadSessionStore.getState()
    store.setItemsForTurn('thread-1', 'turn-1', [
      {
        id: 'thread-1:2',
        threadId: 'thread-1',
        turnId: 'turn-1',
        kind: 'message',
        normalizedKind: 'userMessage',
        status: 'inProgress',
        createdAtMs: 2,
        updatedAtMs: 3,
        payload: { type: 'message', role: 'user', text: 'Build it' },
      } as SessionItem,
    ])

    store.setThreadTurns(
      'thread-1',
      [
        {
          id: 'turn-1',
          threadId: 'thread-1',
          status: 'completed',
          lastCodexStatus: 'completed',
          startedAtMs: 1,
          completedAtMs: 4,
          error: null,
          items: [
            {
              id: 'item-1',
              threadId: 'thread-1',
              turnId: 'turn-1',
              kind: 'userMessage',
              status: 'completed',
              createdAtMs: 2,
              updatedAtMs: 4,
              payload: { type: 'userMessage', text: 'Build it' },
            } as SessionItem,
          ],
        },
      ],
      { mode: 'replace' },
    )

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-1']
    expect(items).toHaveLength(1)
    expect(items[0].id).toBe('item-1')
    expect(items[0].payload.text).toBe('Build it')
    expect(selectVisibleTranscriptRows(snapshot, 'thread-1').map((row) => row.item.payload.text)).toEqual(['Build it'])
  })

  it('replace hydrate preserves workflow metadata and replaces duplicate live items', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadTurns('thread-1', [
      {
        id: 'turn-frame',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 1,
        completedAtMs: 2,
        error: null,
        metadata: {
          workflowInternal: true,
          workflowInternalKind: 'artifact_generation',
          artifactKind: 'frame',
        },
        items: [
          {
            id: 'live-user',
            threadId: 'thread-1',
            turnId: 'turn-frame',
            kind: 'userMessage',
            status: 'completed',
            createdAtMs: 1,
            updatedAtMs: 1,
            payload: { type: 'userMessage', text: 'Generate frame' },
          } as SessionItem,
          {
            id: 'live-agent',
            threadId: 'thread-1',
            turnId: 'turn-frame',
            kind: 'agentMessage',
            status: 'completed',
            createdAtMs: 2,
            updatedAtMs: 2,
            payload: { type: 'agentMessage', text: '{"content":"Generated frame"}' },
          } as SessionItem,
        ],
      },
    ])

    store.setThreadTurns(
      'thread-1',
      [
        {
          id: 'turn-frame',
          threadId: 'thread-1',
          status: 'completed',
          lastCodexStatus: 'completed',
          startedAtMs: 1,
          completedAtMs: 2,
          error: null,
          items: [
            {
              id: 'hydrate-user',
              threadId: 'thread-1',
              turnId: 'turn-frame',
              kind: 'userMessage',
              status: 'completed',
              createdAtMs: 1,
              updatedAtMs: 3,
              payload: { type: 'userMessage', content: [{ type: 'text', text: 'Generate frame' }] },
            } as SessionItem,
            {
              id: 'hydrate-agent',
              threadId: 'thread-1',
              turnId: 'turn-frame',
              kind: 'agentMessage',
              status: 'completed',
              createdAtMs: 2,
              updatedAtMs: 3,
              payload: { type: 'agentMessage', text: '{"content":"Generated frame"}' },
            } as SessionItem,
          ],
        },
      ],
      { mode: 'replace' },
    )

    const snapshot = useThreadSessionStore.getState()
    const turn = snapshot.turnsByThread['thread-1'][0]
    const items = snapshot.itemsByTurn['thread-1:turn-frame']
    expect(turn.metadata?.workflowInternal).toBe(true)
    expect(items.map((item) => item.id)).toEqual(['hydrate-user', 'hydrate-agent'])
    expect(selectVisibleTranscriptRows(snapshot, 'thread-1')).toEqual([])
  })

  it('selectVisibleTranscriptRows hides internal workflow raw chat for generate and regenerate frame/spec', () => {
    const store = useThreadSessionStore.getState()
    const cases = [
      ['turn-generate-frame', 'frame', undefined, 'Hidden generate frame prompt'],
      ['turn-regenerate-frame', 'frame', 'regenerate_frame', 'Hidden regenerate frame prompt'],
      ['turn-generate-spec', 'spec', undefined, 'Hidden generate spec prompt'],
      ['turn-regenerate-spec', 'spec', 'regenerate_spec', 'Hidden regenerate spec prompt'],
    ] as const

    store.setThreadTurns('thread-1', cases.map(([turnId, artifactKind, workflowKind, text], index) => ({
      id: turnId,
      threadId: 'thread-1',
      status: 'completed',
      lastCodexStatus: 'completed',
      startedAtMs: index + 1,
      completedAtMs: index + 2,
      error: null,
      metadata: {
        workflowInternal: true,
        workflowInternalKind: 'artifact_generation',
        artifactKind,
        ...(workflowKind ? { workflowKind } : {}),
      },
      items: [
        {
          id: `${turnId}:user`,
          threadId: 'thread-1',
          turnId,
          kind: 'userMessage',
          status: 'completed',
          createdAtMs: index + 1,
          updatedAtMs: index + 1,
          payload: { type: 'userMessage', text },
        } as SessionItem,
        {
          id: `${turnId}:agent`,
          threadId: 'thread-1',
          turnId,
          kind: 'agentMessage',
          status: 'completed',
          createdAtMs: index + 1,
          updatedAtMs: index + 1,
          payload: { type: 'agentMessage', text: `{"hidden":"${artifactKind}"}` },
        } as SessionItem,
      ],
    })))

    const rows = selectVisibleTranscriptRows(useThreadSessionStore.getState(), 'thread-1')
    expect(rows).toEqual([])
  })

  it('selectVisibleTranscriptRows hides explicitly internal items and emits visible chat', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadTurns('thread-1', [
      {
        id: 'turn-1',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 1,
        completedAtMs: 2,
        error: null,
        items: [
          {
            id: 'item-internal',
            threadId: 'thread-1',
            turnId: 'turn-1',
            kind: 'agentMessage',
            status: 'completed',
            createdAtMs: 1,
            updatedAtMs: 1,
            payload: { type: 'agentMessage', text: 'hidden', metadata: { workflowInternal: true } },
          } as SessionItem,
          {
            id: 'item-visible',
            threadId: 'thread-1',
            turnId: 'turn-1',
            kind: 'agentMessage',
            status: 'completed',
            createdAtMs: 2,
            updatedAtMs: 2,
            payload: { type: 'agentMessage', text: 'visible' },
          } as SessionItem,
        ],
      },
    ])

    const rows = selectVisibleTranscriptRows(useThreadSessionStore.getState(), 'thread-1')
    expect(rows.map((row) => row.item.id)).toEqual(['item-visible'])
    expect(rows[0].item.renderAs).toBe('chatBubble')
    expect(rows[0].item.visibility).toBe('user')
  })

  it('applies batched stream envelopes in order for delta-heavy updates', () => {
    const store = useThreadSessionStore.getState()
    const envelopes: SessionEventEnvelope[] = [
      {
        schemaVersion: 1,
        eventId: 'thread-1:1',
        eventSeq: 1,
        tier: 'tier0',
        method: 'item/started',
        threadId: 'thread-1',
        turnId: 'turn-1',
        occurredAtMs: 1,
        replayable: true,
        snapshotVersion: null,
        source: 'journal',
        params: {
          item: {
            id: 'item-1',
            kind: 'agentMessage',
            status: 'inProgress',
            text: 'Hello',
          },
        },
      },
      {
        schemaVersion: 1,
        eventId: 'thread-1:2',
        eventSeq: 2,
        tier: 'tier0',
        method: 'item/agentMessage/delta',
        threadId: 'thread-1',
        turnId: 'turn-1',
        occurredAtMs: 2,
        replayable: true,
        snapshotVersion: null,
        source: 'journal',
        params: {
          itemId: 'item-1',
          delta: ' there',
        },
      },
      {
        schemaVersion: 1,
        eventId: 'thread-1:3',
        eventSeq: 3,
        tier: 'tier0',
        method: 'item/agentMessage/delta',
        threadId: 'thread-1',
        turnId: 'turn-1',
        occurredAtMs: 3,
        replayable: true,
        snapshotVersion: null,
        source: 'journal',
        params: {
          itemId: 'item-1',
          delta: '!',
        },
      },
    ]

    store.applyEventsBatch(envelopes)

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-1']
    expect(items).toHaveLength(1)
    expect(items[0].payload.text).toBe('Hello there!')
    expect(snapshot.lastEventSeqByThread['thread-1']).toBe(3)
    expect(snapshot.lastEventIdByThread['thread-1']).toBe('thread-1:3')
  })

  it('drops unknown stream items from item events', () => {
    const store = useThreadSessionStore.getState()
    store.applyEvent({
      schemaVersion: 1,
      eventId: 'thread-1:unknown',
      eventSeq: 1,
      tier: 'tier0',
      method: 'item/started',
      threadId: 'thread-1',
      turnId: 'turn-unknown',
      occurredAtMs: 1,
      replayable: true,
      snapshotVersion: null,
      source: 'journal',
      params: {
        item: {
          id: 'item-unknown',
          kind: 'mcpToolCall',
          status: 'inProgress',
          arguments: {},
        },
      },
    })

    const snapshot = useThreadSessionStore.getState()
    const items = snapshot.itemsByTurn['thread-1:turn-unknown'] ?? []
    expect(items).toHaveLength(0)
  })

  it('exposes shared selectors for active thread transcript state', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadList([
      thread({ id: 'thread-2', name: 'Older', updatedAt: 10 }),
      thread({ id: 'thread-1', name: 'Newest', updatedAt: 20 }),
    ])
    store.setActiveThreadId('thread-1')
    store.setThreadTurns('thread-1', [
      {
        id: 'turn-1',
        threadId: 'thread-1',
        status: 'completed',
        lastCodexStatus: 'completed',
        startedAtMs: 1,
        completedAtMs: 2,
        items: [],
        error: null,
      },
      {
        id: 'turn-2',
        threadId: 'thread-1',
        status: 'inProgress',
        lastCodexStatus: 'inProgress',
        startedAtMs: 3,
        completedAtMs: null,
        items: [],
        error: null,
      },
    ])
    store.setItemsForTurn('thread-1', 'turn-1', [
      {
        id: 'item-1',
        threadId: 'thread-1',
        turnId: 'turn-1',
        kind: 'agentMessage',
        status: 'completed',
        createdAtMs: 1,
        updatedAtMs: 2,
        payload: { type: 'agentMessage', text: 'done' },
      },
    ])

    const snapshot = useThreadSessionStore.getState()
    const threads = selectThreadsSorted(snapshot)
    const activeThread = selectActiveThread(snapshot)
    const activeTurns = selectActiveTurns(snapshot)
    const activeRunningTurn = selectActiveRunningTurn(snapshot)
    const activeItemsByTurn = selectActiveItemsByTurn(snapshot)
    const transcript = selectActiveTranscriptModel(snapshot)

    expect(threads.map((row) => row.id)).toEqual(['thread-1', 'thread-2'])
    expect(activeThread?.id).toBe('thread-1')
    expect(activeTurns.map((row) => row.id)).toEqual(['turn-1', 'turn-2'])
    expect(activeRunningTurn?.id).toBe('turn-2')
    expect(activeItemsByTurn['thread-1:turn-1']).toHaveLength(1)
    expect(transcript.threadId).toBe('thread-1')
    expect(transcript.turns.map((row) => row.id)).toEqual(['turn-1', 'turn-2'])
  })
})
