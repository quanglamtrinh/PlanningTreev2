import { beforeEach, describe, expect, it } from 'vitest'

import type { SessionItem, SessionTurn } from '../../src/features/session_v2/contracts'
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
    expect(items[0].payload.type).toBe('agentMessage')
    expect(items[0].payload.text).toBe('Hello from Codex')
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
})
