import { beforeEach, describe, expect, it } from 'vitest'

import type { SessionEventEnvelope, SessionItem, SessionTurn } from '../../src/features/session_v2/contracts'
import { useThreadSessionStore } from '../../src/features/session_v2/store/threadSessionStore'

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
})
